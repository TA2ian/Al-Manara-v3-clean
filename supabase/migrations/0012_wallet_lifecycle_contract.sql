-- Customer wallet lifecycle contract.
-- Verified wallets are immutable. They can only be transitioned to DISABLED.
-- Physical deletion is intentionally not part of the customer wallet lifecycle.

alter table wallets
    add column if not exists label text,
    add column if not exists qr_image_file_id text;

alter table wallets
    drop constraint if exists wallets_label_valid;
alter table wallets
    add constraint wallets_label_valid
    check (label is not null and length(btrim(label)) between 1 and 64);

alter table wallets
    drop constraint if exists wallets_qr_file_id_valid;
alter table wallets
    add constraint wallets_qr_file_id_valid
    check (qr_image_file_id is not null and length(btrim(qr_image_file_id)) > 0);

-- A disabled wallet remains historical data. The same address may therefore be
-- registered again as a new wallet after the old one is disabled.
drop index if exists wallets_user_network_address_uq;
create unique index wallets_user_network_address_uq
    on wallets(user_id, network_code, normalized_address)
    where status <> 'DISABLED';

create or replace function prevent_verified_wallet_update() returns trigger
language plpgsql
as $$
begin
    if old.status = 'VERIFIED' then
        if new.user_id is distinct from old.user_id
           or new.network_code is distinct from old.network_code
           or new.address is distinct from old.address
           or new.normalized_address is distinct from old.normalized_address
           or new.label is distinct from old.label
           or new.qr_image_file_id is distinct from old.qr_image_file_id
           or new.verified_at is distinct from old.verified_at then
            raise exception 'verified wallets are immutable';
        end if;

        if new.status is distinct from old.status then
            if new.status <> 'DISABLED' or new.disabled_at is null then
                raise exception 'verified wallets can only be disabled';
            end if;
        end if;
    end if;

    if old.status = 'DISABLED' then
        if new.user_id is distinct from old.user_id
           or new.network_code is distinct from old.network_code
           or new.address is distinct from old.address
           or new.normalized_address is distinct from old.normalized_address
           or new.status is distinct from old.status
           or new.label is distinct from old.label
           or new.qr_image_file_id is distinct from old.qr_image_file_id
           or new.verified_at is distinct from old.verified_at
           or new.disabled_at is distinct from old.disabled_at then
            raise exception 'disabled wallets are immutable and cannot be reactivated';
        end if;
    end if;

    return new;
end;
$$;

drop trigger if exists wallets_verified_immutable on wallets;
create trigger wallets_verified_immutable
before update on wallets
for each row execute function prevent_verified_wallet_update();

create or replace function disable_wallet_if_allowed(
    p_wallet_id uuid,
    p_user_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_disabled_count integer;
begin
    update wallets
       set status = 'DISABLED',
           disabled_at = coalesce(disabled_at, now()),
           updated_at = now()
     where id = p_wallet_id
       and user_id = p_user_id
       and status = 'VERIFIED';

    get diagnostics v_disabled_count = row_count;
    return v_disabled_count > 0;
end;
$$;
