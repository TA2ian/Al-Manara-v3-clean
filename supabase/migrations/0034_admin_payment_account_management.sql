-- Administrative management API for currency-scoped ShamCash receiving accounts.
-- Authorization is authoritative in the database and is checked before every mutation/read.
-- These functions are backend-only; the application passes the Telegram admin identity,
-- while the database verifies that identity against admin_users.

create or replace function assert_enabled_admin(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns void
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_registered_actor_type admin_actor_type;
begin
    if p_telegram_user_id is null or p_telegram_user_id <= 0 then
        raise exception 'admin identity is required';
    end if;

    select au.actor_type
      into v_registered_actor_type
      from admin_users au
     where au.telegram_user_id = p_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;

    if not found then
        raise exception 'admin is not enabled';
    end if;

    if v_registered_actor_type <> p_actor_type then
        raise exception 'admin actor type mismatch';
    end if;
end;
$$;

create or replace function list_admin_payment_accounts(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns table (
    id uuid,
    payment_method_code text,
    payment_method_status payment_method_status,
    currency currency_code,
    account_name text,
    account_number text,
    qr_image_file_id text,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
begin
    perform assert_enabled_admin(p_telegram_user_id, p_actor_type);

    return query
    select apa.id,
           pm.code,
           pm.status,
           apa.currency,
           apa.account_name,
           apa.account_number,
           apa.qr_image_file_id,
           apa.is_active,
           apa.updated_at
      from admin_payment_accounts apa
      join payment_methods pm on pm.id = apa.payment_method_id
     where pm.code = 'SHAM_CASH'
     order by apa.currency, apa.updated_at desc;
end;
$$;

create or replace function upsert_admin_payment_account(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_currency currency_code,
    p_account_name text,
    p_account_number text,
    p_qr_image_file_id text
)
returns table (
    id uuid,
    currency currency_code,
    account_name text,
    account_number text,
    qr_image_file_id text,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_payment_method_id uuid;
    v_id uuid;
begin
    perform assert_enabled_admin(p_telegram_user_id, p_actor_type);

    if p_currency is null then
        raise exception 'payment currency is required';
    end if;
    if length(btrim(coalesce(p_account_name, ''))) not between 2 and 100 then
        raise exception 'payment account name length is invalid';
    end if;
    if length(btrim(coalesce(p_account_number, ''))) not between 5 and 150 then
        raise exception 'payment account number length is invalid';
    end if;
    if length(btrim(coalesce(p_qr_image_file_id, ''))) = 0 then
        raise exception 'qr image file id is required';
    end if;

    select pm.id
      into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH'
       and pm.status = 'ENABLED';

    if not found then
        raise exception 'SHAM_CASH payment method is disabled';
    end if;

    insert into admin_payment_accounts (
        payment_method_id,
        currency,
        account_name,
        account_number,
        qr_image_file_id,
        is_active
    ) values (
        v_payment_method_id,
        p_currency,
        btrim(p_account_name),
        btrim(p_account_number),
        btrim(p_qr_image_file_id),
        true
    )
    on conflict (payment_method_id, currency)
    do update set
        account_name = excluded.account_name,
        account_number = excluded.account_number,
        qr_image_file_id = excluded.qr_image_file_id,
        is_active = true,
        updated_at = now()
    returning admin_payment_accounts.id into v_id;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_type,
        action,
        target_type,
        target_id,
        old_value,
        new_value,
        metadata
    ) values (
        p_telegram_user_id,
        p_actor_type,
        'admin_payment_account.updated',
        'admin_payment_account',
        v_id::text,
        null,
        jsonb_build_object(
            'currency', p_currency,
            'account_name', btrim(p_account_name),
            'account_number', btrim(p_account_number),
            'qr_image_file_id', btrim(p_qr_image_file_id),
            'is_active', true
        ),
        '{}'::jsonb
    );

    return query
    select apa.id, apa.currency, apa.account_name, apa.account_number,
           apa.qr_image_file_id, apa.is_active, apa.updated_at
      from admin_payment_accounts apa
     where apa.id = v_id;
end;
$$;

create or replace function set_admin_payment_account_active(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_currency currency_code,
    p_is_active boolean
)
returns table (
    id uuid,
    currency currency_code,
    is_active boolean,
    updated_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_payment_method_id uuid;
    v_id uuid;
begin
    perform assert_enabled_admin(p_telegram_user_id, p_actor_type);

    select pm.id
      into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH';

    if not found then
        raise exception 'SHAM_CASH payment method not found';
    end if;

    update admin_payment_accounts apa
       set is_active = p_is_active,
           updated_at = now()
     where apa.payment_method_id = v_payment_method_id
       and apa.currency = p_currency
    returning apa.id into v_id;

    if not found then
        raise exception 'admin payment account not found';
    end if;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_type,
        action,
        target_type,
        target_id,
        old_value,
        new_value,
        metadata
    ) values (
        p_telegram_user_id,
        p_actor_type,
        'admin_payment_account.status_changed',
        'admin_payment_account',
        v_id::text,
        null,
        jsonb_build_object('currency', p_currency, 'is_active', p_is_active),
        '{}'::jsonb
    );

    return query
    select apa.id, apa.currency, apa.is_active, apa.updated_at
      from admin_payment_accounts apa
     where apa.id = v_id;
end;
$$;

revoke execute on function assert_enabled_admin(bigint, admin_actor_type) from public, anon, authenticated;
revoke execute on function list_admin_payment_accounts(bigint, admin_actor_type) from public, anon, authenticated;
revoke execute on function upsert_admin_payment_account(bigint, admin_actor_type, currency_code, text, text, text) from public, anon, authenticated;
revoke execute on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean) from public, anon, authenticated;
grant execute on function list_admin_payment_accounts(bigint, admin_actor_type) to service_role;
grant execute on function upsert_admin_payment_account(bigint, admin_actor_type, currency_code, text, text, text) to service_role;
grant execute on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean) to service_role;
