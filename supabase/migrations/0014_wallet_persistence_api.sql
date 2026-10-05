-- Persistence boundary for wallet reads and lifecycle operations.
-- Telegram IDs are application actor identities; users.id remains the internal UUID.

create or replace function get_wallet_for_telegram_user(
    p_wallet_id uuid,
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
     where w.id = p_wallet_id
       and u.telegram_user_id = p_telegram_user_id;
$$;

create or replace function find_verified_wallet_by_address(p_address text)
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
     where w.status = 'VERIFIED'
       and lower(btrim(w.address)) = lower(btrim(p_address));
$$;

create or replace function disable_wallet_for_telegram_user(
    p_wallet_id uuid,
    p_telegram_user_id bigint
)
returns table (disabled boolean)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_user_id uuid;
begin
    select id into v_user_id
      from users
     where telegram_user_id = p_telegram_user_id
       and not is_disabled;

    if not found then
        return query select false;
        return;
    end if;

    return query
    select disable_wallet_if_allowed(p_wallet_id, v_user_id);
end;
$$;
