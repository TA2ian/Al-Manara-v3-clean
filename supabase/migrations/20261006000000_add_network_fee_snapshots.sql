-- Canonical dual-fee policy.  The percentage is Al-Manara's service fee;
-- the fixed amount is the network transfer cost.  Both are immutable once an
-- order financial snapshot has been written.

alter table network_configs
    add column if not exists fixed_network_fee_usdt numeric(24,9) not null default 0;

alter table network_configs
    add constraint network_fixed_fee_nonnegative
    check (fixed_network_fee_usdt >= 0) not valid;
alter table network_configs
    validate constraint network_fixed_fee_nonnegative;

alter table order_financial_snapshots
    add column if not exists network_fixed_fee_usdt numeric(24,9) not null default 0,
    add column if not exists total_fee_usdt numeric(24,9) not null default 0;

-- Quotes are server-issued, opaque records.  The Telegram FSM may carry only
-- the quote UUID; it never remains the authority for financial values.
create table if not exists purchase_quotes (
    id uuid primary key default gen_random_uuid(),
    telegram_user_id bigint not null,
    wallet_id uuid not null references wallets(id) on delete restrict,
    network_code network_code not null,
    payload jsonb not null,
    issued_at timestamptz not null default now(),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    order_id uuid unique references orders(internal_order_id) on delete restrict,
    constraint purchase_quotes_window check (expires_at > issued_at),
    constraint purchase_quotes_payload_object check (jsonb_typeof(payload) = 'object')
);
create index if not exists purchase_quotes_active_lookup_idx
    on purchase_quotes (telegram_user_id, id)
    where consumed_at is null;
alter table purchase_quotes enable row level security;
revoke all on table purchase_quotes from public, anon, authenticated;

create or replace function enforce_order_financial_snapshot_fees()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_network network_code;
    v_service_percent numeric;
    v_fixed_fee numeric;
    v_service_fee numeric;
    v_total_fee numeric;
begin
    select o.network_code, nc.service_fee_percent, nc.fixed_network_fee_usdt
      into v_network, v_service_percent, v_fixed_fee
      from orders o
      join network_configs nc on nc.code = o.network_code
     where o.internal_order_id = new.internal_order_id
     for share of o, nc;

    if not found then
        raise exception 'order network fee policy is unavailable';
    end if;
    if new.fee_percent <> v_service_percent then
        raise exception 'service fee policy snapshot mismatch';
    end if;

    v_service_fee := round(new.requested_amount * new.fee_percent / 100, 9);
    v_total_fee := round(v_service_fee + v_fixed_fee, 9);
    if new.fee_amount <> v_service_fee
       or new.net_usdt_amount <> round(new.requested_amount - v_total_fee, 9)
       or new.net_usdt_amount <= 0 then
        raise exception 'invalid immutable financial snapshot';
    end if;

    new.network_fixed_fee_usdt := v_fixed_fee;
    new.total_fee_usdt := v_total_fee;
    return new;
end;
$$;

drop trigger if exists order_financial_snapshots_fee_guard on order_financial_snapshots;
create trigger order_financial_snapshots_fee_guard
before insert on order_financial_snapshots
for each row execute function enforce_order_financial_snapshot_fees();

drop function if exists get_current_fee_policy(network_code, timestamptz);
create function get_current_fee_policy(
    p_network_code network_code,
    p_now timestamptz
)
returns table (
    percent numeric,
    fixed_network_fee_usdt numeric,
    version text,
    effective_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_network_code is null or p_now is null then
        raise exception 'network code and evaluation time are required';
    end if;
    return query
    select nc.service_fee_percent, nc.fixed_network_fee_usdt,
           'network_config:' || nc.config_version::text, nc.updated_at
      from network_configs nc
     where nc.code = p_network_code and nc.enabled;
end;
$$;

revoke all on function enforce_order_financial_snapshot_fees() from public;
revoke all on function get_current_fee_policy(network_code, timestamptz) from public, anon, authenticated;
grant execute on function get_current_fee_policy(network_code, timestamptz) to service_role;
