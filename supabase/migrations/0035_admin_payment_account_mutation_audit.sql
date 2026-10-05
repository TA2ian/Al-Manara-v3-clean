-- Harden admin payment-account mutations so status changes return the complete
-- account snapshot and audit entries preserve the previous state.

-- PostgreSQL cannot change a function's OUT/RETURNS TABLE row type with
-- CREATE OR REPLACE. Drop the previous signature first, then recreate it.
drop function if exists set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean);

create function set_admin_payment_account_active(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_currency currency_code,
    p_is_active boolean
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
    v_old_is_active boolean;
begin
    perform assert_enabled_admin(p_telegram_user_id, p_actor_type);

    select pm.id
      into v_payment_method_id
      from payment_methods pm
     where pm.code = 'SHAM_CASH';

    if not found then
        raise exception 'SHAM_CASH payment method not found';
    end if;

    select apa.id, apa.is_active
      into v_id, v_old_is_active
      from admin_payment_accounts apa
     where apa.payment_method_id = v_payment_method_id
       and apa.currency = p_currency
     for update;

    if not found then
        raise exception 'admin payment account not found';
    end if;

    update admin_payment_accounts apa
       set is_active = p_is_active,
           updated_at = now()
     where apa.id = v_id;

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
        jsonb_build_object('currency', p_currency, 'is_active', v_old_is_active),
        jsonb_build_object('currency', p_currency, 'is_active', p_is_active),
        '{}'::jsonb
    );

    return query
    select apa.id,
           apa.currency,
           apa.account_name,
           apa.account_number,
           apa.qr_image_file_id,
           apa.is_active,
           apa.updated_at
      from admin_payment_accounts apa
     where apa.id = v_id;
end;
$$;

revoke execute on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean) from public, anon, authenticated;
grant execute on function set_admin_payment_account_active(bigint, admin_actor_type, currency_code, boolean) to service_role;
