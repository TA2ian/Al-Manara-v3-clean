create table if not exists idempotency_keys (
    telegram_user_id bigint not null,
    operation text not null,
    idempotency_key text not null,
    response_json jsonb not null,
    created_at timestamptz not null default now(),
    primary key (telegram_user_id, operation, idempotency_key)
);

create or replace function create_purchase_order_atomic(
    p_internal_order_id uuid,
    p_public_order_code text,
    p_user_id bigint,
    p_wallet_id uuid,
    p_network_code text,
    p_wallet_address text,
    p_requested_amount numeric,
    p_fee_percent numeric,
    p_fee_amount numeric,
    p_net_usdt_amount numeric,
    p_payment_currency text,
    p_exchange_rate numeric,
    p_local_amount numeric,
    p_rounding_policy_version text,
    p_customer_verified_name_snapshot text,
    p_customer_shamcash_account_snapshot text,
    p_admin_payment_account_name_snapshot text,
    p_admin_payment_account_number_snapshot text,
    p_admin_payment_qr_file_id_snapshot text,
    p_quote_issued_at timestamptz,
    p_quote_expires_at timestamptz,
    p_idempotency_key text,
    p_operation text default 'create_purchase_order'
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_user_id uuid;
    v_wallet_user_id uuid;
    v_wallet_network network_code;
    v_wallet_status wallet_status;
    v_wallet_address text;
    v_network_enabled boolean;
    v_min_amount numeric;
    v_max_amount numeric;
    v_identity_name text;
    v_identity_account text;
    v_identity_verified_at timestamptz;
    v_payment_method_id uuid;
    v_admin_name text;
    v_admin_number text;
    v_admin_qr text;
    v_status order_status;
    v_version bigint;
begin
    if p_internal_order_id is null then raise exception 'internal order id is required'; end if;
    if p_public_order_code is null or length(btrim(p_public_order_code)) < 4 then raise exception 'public order code is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_quote_issued_at is null or p_quote_expires_at is null or p_quote_expires_at <= p_quote_issued_at then raise exception 'invalid quote window'; end if;
    if p_payment_currency not in ('USD', 'NEW.SYP') then raise exception 'unsupported payment currency'; end if;

    select response_json
      into v_existing
      from idempotency_keys
     where telegram_user_id = p_user_id
       and operation = p_operation
       and idempotency_key = p_idempotency_key
     for update;

    if found then
        return query
        select
            (v_existing ->> 'internal_order_id')::uuid,
            v_existing ->> 'public_order_code',
            (v_existing ->> 'status')::order_status,
            (v_existing ->> 'version')::bigint,
            true;
        return;
    end if;

    select id into v_user_id
      from users
     where telegram_user_id = p_user_id
       and not is_disabled;
    if not found then raise exception 'customer not found or disabled'; end if;

    select w.user_id, w.network_code, w.status, w.address
      into v_wallet_user_id, v_wallet_network, v_wallet_status, v_wallet_address
      from wallets w
     where w.id = p_wallet_id
     for share;
    if not found then raise exception 'wallet not found'; end if;
    if v_wallet_user_id <> v_user_id then raise exception 'wallet does not belong to customer'; end if;
    if v_wallet_status <> 'VERIFIED' then raise exception 'wallet is not verified'; end if;
    if v_wallet_network <> p_network_code::network_code then raise exception 'wallet network mismatch'; end if;
    if btrim(v_wallet_address) <> btrim(p_wallet_address) then raise exception 'wallet address mismatch'; end if;

    select enabled, min_amount, max_amount
      into v_network_enabled, v_min_amount, v_max_amount
      from network_configs
     where code = p_network_code::network_code
     for share;
    if not found or not v_network_enabled then raise exception 'network is unavailable'; end if;
    if p_requested_amount < v_min_amount or p_requested_amount > v_max_amount then raise exception 'amount is outside network limits'; end if;

    select verified_name, verified_shamcash_account, payment_identity_verified_at
      into v_identity_name, v_identity_account, v_identity_verified_at
      from users
     where id = v_user_id
     for share;
    if v_identity_name is null or v_identity_account is null or v_identity_verified_at is null then
        raise exception 'customer payment identity is not verified';
    end if;
    if btrim(v_identity_name) <> btrim(p_customer_verified_name_snapshot)
       or btrim(v_identity_account) <> btrim(p_customer_shamcash_account_snapshot) then
        raise exception 'customer identity snapshot mismatch';
    end if;

    select pm.id into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH'
       and pm.status = 'ENABLED';
    if not found then raise exception 'ShamCash payment method is unavailable'; end if;

    select apa.account_name, apa.account_number, apa.qr_image_file_id
      into v_admin_name, v_admin_number, v_admin_qr
      from admin_payment_accounts apa
     where apa.payment_method_id = v_payment_method_id
       and apa.currency = p_payment_currency::currency_code
       and apa.is_active
     for share;
    if not found then raise exception 'admin payment account is unavailable'; end if;

    if btrim(v_admin_name) <> btrim(p_admin_payment_account_name_snapshot)
       or btrim(v_admin_number) <> btrim(p_admin_payment_account_number_snapshot)
       or coalesce(btrim(v_admin_qr), '') <> coalesce(btrim(p_admin_payment_qr_file_id_snapshot), '') then
        raise exception 'admin payment account snapshot mismatch';
    end if;

    insert into orders (
        internal_order_id, public_order_code, user_id, wallet_id, network_code,
        payment_method_id, status, version, expires_at
    ) values (
        p_internal_order_id, btrim(p_public_order_code), v_user_id, p_wallet_id,
        p_network_code::network_code, v_payment_method_id, 'DRAFT', 1, p_quote_expires_at
    ) returning orders.status, orders.version into v_status, v_version;

    insert into order_financial_snapshots (
        internal_order_id, requested_amount, fee_percent, fee_amount, net_usdt_amount,
        payment_currency, exchange_rate, local_amount, rounding_policy_version,
        network_config_version
    ) values (
        p_internal_order_id, p_requested_amount, p_fee_percent, p_fee_amount, p_net_usdt_amount,
        p_payment_currency::currency_code, p_exchange_rate, p_local_amount,
        p_rounding_policy_version,
        (select nc.config_version from network_configs nc where nc.code = p_network_code::network_code)
    );

    insert into audit_logs (
        actor_telegram_user_id, action, target_type, target_id, new_value, metadata
    ) values (
        p_user_id, 'order.created', 'order', p_internal_order_id::text,
        jsonb_build_object('public_order_code', p_public_order_code, 'status', v_status, 'version', v_version),
        jsonb_build_object('operation', p_operation)
    );

    insert into idempotency_keys (telegram_user_id, operation, idempotency_key, response_json)
    values (
        p_user_id, p_operation, p_idempotency_key,
        jsonb_build_object(
            'internal_order_id', p_internal_order_id,
            'public_order_code', p_public_order_code,
            'status', v_status,
            'version', v_version
        )
    );

    return query
    select p_internal_order_id, p_public_order_code, v_status, v_version, false;
exception
    when unique_violation then
        if exists (select 1 from orders o where o.public_order_code = p_public_order_code) then
            raise exception 'public order code collision';
        end if;
        if exists (select 1 from idempotency_keys ik where ik.telegram_user_id = p_user_id and ik.operation = p_operation and ik.idempotency_key = p_idempotency_key) then
            raise exception 'idempotency key collision';
        end if;
        raise;
end;
$$;
