-- Customer-facing wallet listing boundary.
-- Only VERIFIED wallets are exposed for new order selection.

create or replace function list_verified_wallets_for_telegram_user(
    p_telegram_user_id bigint
)
returns table (
    wallet_id uuid,
    telegram_user_id bigint,
    network_code network_code,
    address text,
    status wallet_status
)
language sql
security invoker
set search_path = public
as $$
    select w.id, u.telegram_user_id, w.network_code, w.address, w.status
      from wallets w
      join users u on u.id = w.user_id
     where u.telegram_user_id = p_telegram_user_id
       and not u.is_disabled
       and w.status = 'VERIFIED'
     order by w.created_at desc, w.id desc;
$$;
