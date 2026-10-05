-- 0032_unverified_customer_tier.sql
-- Allow unverified customers to purchase between 10 and 50 USDT with strict rate limits:
-- 1 order per day, 3 orders per week, 10 orders per month.

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
security definer
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
    v_day_orders bigint;
    v_week_orders bigint;
    v_month_orders bigint;
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

    select id, verified_name, verified_shamcash_account, payment_identity_verified_at
      into v_user_id, v_identity_name, v_identity_account, v_identity_verified_at
      from users
     where telegram_user_id = p_user_id
       and not is_disabled;
    if not found then raise exception 'customer not found or disabled'; end if;

    -- Unverified Customer Tier checks
    if v_identity_verified_at is null then
        if p_requested_amount < 10 or p_requested_amount > 50 then
            raise exception 'unverified customers can only order between 10 and 50 USDT';
        end if;

        select
            count(*) filter (where created_at >= now() - interval '24 hours' and status not in ('CANCELLED', 'REJECTED')),
            count(*) filter (where created_at >= now() - interval '7 days' and status not in ('CANCELLED', 'REJECTED')),
            count(*) filter (where created_at >= now() - interval '30 days' and status not in ('CANCELLED', 'REJECTED'))
          into v_day_orders, v_week_orders, v_month_orders
          from orders
         where user_id = v_user_id;

        if coalesce(v_day_orders, 0) >= 1 then
            raise exception 'unverified customers limit: max 1 order per day';
        end if;
        if coalesce(v_week_orders, 0) >= 3 then
            raise exception 'unverified customers limit: max 3 orders per week';
        end if;
        if coalesce(v_month_orders, 0) >= 10 then
            raise exception 'unverified customers limit: max 10 orders per month';
        end if;
    else
        -- Verified Customer identity matching
        if btrim(v_identity_name) <> btrim(p_customer_verified_name_snapshot)
           or btrim(v_identity_account) <> btrim(p_customer_shamcash_account_snapshot) then
            raise exception 'customer identity snapshot mismatch';
        end if;
    end if;

    -- Wallet validation
    select w.user_id, w.network_code, w.status, w.address
      into v_wallet_user_id, v_wallet_network, v_wallet_status, v_wallet_address
      from wallets w
     where w.id = p_wallet_id
     for share;
    if not found then raise exception 'wallet not found'; end if;
    if v_wallet_user_id <> v_user_id then raise exception 'wallet does not belong to customer'; end if;
    if v_wallet_network <> p_network_code::network_code then raise exception 'wallet network mismatch'; end if;
    if btrim(v_wallet_address) <> btrim(p_wallet_address) then raise exception 'wallet address mismatch'; end if;

    -- Network validation
    select enabled, min_amount, max_amount
      into v_network_enabled, v_min_amount, v_max_amount
      from network_configs
     where code = p_network_code::network_code
     for share;
    if not found or not v_network_enabled then raise exception 'network is unavailable'; end if;
    if p_requested_amount < v_min_amount or p_requested_amount > v_max_amount then raise exception 'amount is outside network limits'; end if;

    -- Admin Payment Account validation
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
        internal_order_id,
        public_order_code,
        user_id,
        wallet_id,
        network_code,
        payment_method_id,
        status,
        version,
        expires_at
    ) values (
        p_internal_order_id,
        p_public_order_code,
        v_user_id,
        p_wallet_id,
        p_network_code::network_code,
        v_payment_method_id,
        'PENDING_PAYMENT',
        1,
        p_quote_expires_at
    ) returning status, version into v_status, v_version;

    insert into order_financial_snapshots (
        internal_order_id,
        requested_amount,
        fee_percent,
        fee_amount,
        net_usdt_amount,
        payment_currency,
        exchange_rate,
        local_amount,
        rounding_policy_version,
        network_config_version
    ) values (
        p_internal_order_id,
        p_requested_amount,
        p_fee_percent,
        p_fee_amount,
        p_net_usdt_amount,
        p_payment_currency::currency_code,
        p_exchange_rate,
        p_local_amount,
        p_rounding_policy_version,
        1
    );

    insert into audit_logs (
        actor_type,
        actor_id,
        action,
        resource_type,
        resource_id,
        old_state,
        new_state
    ) values (
        'CUSTOMER',
        v_user_id,
        'CREATE_PURCHASE_ORDER',
        'ORDER',
        p_internal_order_id,
        null,
        jsonb_build_object(
            'status', v_status,
            'version', v_version,
            'public_order_code', p_public_order_code,
            'requested_amount', p_requested_amount,
            'payment_currency', p_payment_currency,
            'local_amount', p_local_amount
        )
    );

    insert into idempotency_keys (telegram_user_id, operation, idempotency_key, response_json)
    values (
        p_user_id,
        p_operation,
        p_idempotency_key,
        jsonb_build_object(
            'internal_order_id', p_internal_order_id,
            'public_order_code', p_public_order_code,
            'status', v_status,
            'version', v_version
        )
    );

    return query
    select p_internal_order_id, p_public_order_code, v_status, v_version, false;
end;
$$;
