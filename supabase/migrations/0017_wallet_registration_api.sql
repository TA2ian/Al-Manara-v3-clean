-- Customer wallet registration boundary.
-- New wallets are created as PENDING and require the existing verification flow
-- before they become eligible for order creation.

create or replace function register_pending_wallet_for_telegram_user(
    p_telegram_user_id bigint,
    p_address text,
    p_network_code network_code,
    p_qr_image_file_id text,
    p_label text
)
returns table (
    wallet_id uuid,
    telegram_user_id bigint,
    network_code network_code,
    address text,
    status wallet_status
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_user_id uuid;
    v_address text;
    v_label text;
    v_file_id text;
    v_wallet_id uuid;
begin
    v_address := btrim(p_address);
    v_label := btrim(p_label);
    v_file_id := btrim(p_qr_image_file_id);

    if v_address = '' or v_label = '' or length(v_label) > 64 or v_file_id = '' then
        raise exception 'invalid wallet registration payload';
    end if;

    select id into v_user_id
      from users
     where telegram_user_id = p_telegram_user_id
       and not is_disabled;

    if not found then
        raise exception 'customer is unavailable';
    end if;

    if not exists (
        select 1 from network_configs
         where code = p_network_code and enabled
    ) then
        raise exception 'wallet network is unavailable';
    end if;

    if exists (
        select 1 from wallets
         where user_id = v_user_id
           and network_code = p_network_code
           and normalized_address = v_address
           and status <> 'DISABLED'
    ) then
        raise exception 'wallet already registered';
    end if;

    insert into wallets (
        user_id, network_code, address, normalized_address,
        status, label, qr_image_file_id
    )
    values (
        v_user_id, p_network_code, v_address, v_address,
        'PENDING', v_label, v_file_id
    )
    returning id into v_wallet_id;

    return query
    select v_wallet_id, p_telegram_user_id, p_network_code, v_address, 'PENDING'::wallet_status;
end;
$$;
