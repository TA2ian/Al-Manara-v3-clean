-- Finalize payment-account persistence and remove remaining PL/pgSQL
-- output-parameter/column ambiguities detected by database lint.
--
-- This migration deliberately follows the focused final order-lint migrations.
-- Its dynamic replacements are idempotent when a preceding migration has
-- already qualified one of the target expressions.
DO $$
begin
    if exists (
        select 1
          from pg_indexes
         where schemaname = 'public'
           and indexname = 'admin_payment_accounts_method_currency_uq'
    ) and not exists (
        select 1
          from pg_constraint
         where conname = 'admin_payment_accounts_method_currency_uq'
    ) then
        alter table admin_payment_accounts
            add constraint admin_payment_accounts_method_currency_uq
            unique using index admin_payment_accounts_method_currency_uq;
    end if;
end
$$;

-- Recreate the mutation function with ON CONSTRAINT so the return column
-- named currency cannot collide with the conflict target.
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

    insert into admin_payment_accounts as apa (
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
    on conflict on constraint admin_payment_accounts_method_currency_uq
    do update set
        account_name = excluded.account_name,
        account_number = excluded.account_number,
        qr_image_file_id = excluded.qr_image_file_id,
        is_active = true,
        updated_at = now()
    returning apa.id into v_id;

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

-- Fix the three previously-existing order functions without changing their
-- public signatures or behavior.
DO $$
declare
    v_function oid;
    v_definition text;
begin
    foreach v_function in array ARRAY[
        to_regprocedure('public.transition_order_idempotent(uuid,order_status,bigint,bigint,admin_actor_type,jsonb,text)'),
        to_regprocedure('public.claim_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)'),
        to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)')
    ]::oid[] loop
        if v_function is null then
            raise exception 'required order function is missing';
        end if;

        select pg_get_functiondef(v_function) into v_definition;
        v_definition := regexp_replace(v_definition, 'coalesce\(approved_at,', 'coalesce(o.approved_at,', 1, 0, 'i');
        v_definition := regexp_replace(v_definition, 'else approved_at', 'else o.approved_at', 1, 0, 'i');
        v_definition := regexp_replace(v_definition, 'set version = version \+ 1', 'set version = o.version + 1', 1, 0, 'i');
        v_definition := regexp_replace(v_definition, 'and version = p_expected_version', 'and o.version = p_expected_version', 1, 0, 'i');
        execute v_definition;
    end loop;
end
$$;