-- Defense-in-depth order guard.
-- A wallet may remain referenced by historical orders after DISABLED, but a
-- new order (or wallet reassignment) must never use a non-VERIFIED wallet.

create or replace function enforce_order_wallet_guard()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_wallet_user_id uuid;
    v_wallet_network network_code;
    v_wallet_status wallet_status;
begin
    select w.user_id, w.network_code, w.status
      into v_wallet_user_id, v_wallet_network, v_wallet_status
      from wallets w
     where w.id = new.wallet_id
     for share;

    if not found then
        raise exception 'wallet not found';
    end if;

    if v_wallet_user_id <> new.user_id then
        raise exception 'order wallet does not belong to customer';
    end if;

    if v_wallet_network <> new.network_code then
        raise exception 'order wallet network mismatch';
    end if;

    if v_wallet_status <> 'VERIFIED' then
        raise exception 'order wallet must be verified';
    end if;

    return new;
end;
$$;

drop trigger if exists orders_wallet_guard on orders;
create trigger orders_wallet_guard
before insert or update of user_id, wallet_id, network_code on orders
for each row execute function enforce_order_wallet_guard();
