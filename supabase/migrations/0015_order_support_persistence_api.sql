-- Read-only persistence boundary for the data required to create an order.
-- Telegram IDs remain the application identity; users.id remains an internal UUID.

create or replace function get_customer_payment_identity(p_telegram_user_id bigint)
returns table (
    verified_name text,
    verified_shamcash_account text
)
language sql
security invoker
set search_path = public
as $$
    select u.verified_name, u.verified_shamcash_account
      from users u
     where u.telegram_user_id = p_telegram_user_id
       and not u.is_disabled
       and u.verified_name is not null
       and u.verified_shamcash_account is not null
       and u.payment_identity_verified_at is not null;
$$;

create or replace function get_admin_payment_account(p_currency currency_code)
returns table (
    account_name text,
    account_number text,
    qr_image_file_id text
)
language sql
security invoker
set search_path = public
as $$
    select apa.account_name, apa.account_number, apa.qr_image_file_id
      from admin_payment_accounts apa
      join payment_methods pm on pm.id = apa.payment_method_id
     where pm.code = 'SHAM_CASH'
       and pm.status = 'ENABLED'
       and apa.currency = p_currency
       and apa.is_active
     order by apa.updated_at desc
     limit 1;
$$;

create or replace function get_network_config(p_code network_code)
returns table (
    code network_code,
    display_name text,
    enabled boolean,
    address_regex text,
    requires_memo boolean,
    min_amount numeric,
    max_amount numeric
)
language sql
security invoker
set search_path = public
as $$
    select nc.code, nc.display_name, nc.enabled, nc.address_regex,
           nc.requires_memo, nc.min_amount, nc.max_amount
      from network_configs nc
     where nc.code = p_code;
$$;
