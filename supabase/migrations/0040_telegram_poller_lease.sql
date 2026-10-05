-- A database-backed lease keeps only one host polling customer updates for this
-- Telegram bot. Time is evaluated by PostgreSQL so hosts cannot disagree about
-- expiry because of local clock skew.
create table telegram_poller_leases (
    lease_name text primary key,
    owner_id uuid not null,
    expires_at timestamptz not null,
    updated_at timestamptz not null default statement_timestamp(),
    constraint telegram_poller_leases_expiry_check check (expires_at > updated_at)
);

create or replace function acquire_telegram_poller_lease(
    p_owner_id uuid,
    p_lease_seconds integer default 30
)
returns table (acquired boolean)
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_lease_seconds < 10 or p_lease_seconds > 300 then
        raise exception 'lease duration must be between 10 and 300 seconds';
    end if;

    insert into telegram_poller_leases (
        lease_name, owner_id, expires_at, updated_at
    )
    values (
        'customer-telegram-poller',
        p_owner_id,
        statement_timestamp() + make_interval(secs => p_lease_seconds),
        statement_timestamp()
    )
    on conflict (lease_name) do update
    set
        owner_id = excluded.owner_id,
        expires_at = excluded.expires_at,
        updated_at = excluded.updated_at
    where telegram_poller_leases.expires_at <= statement_timestamp()
       or telegram_poller_leases.owner_id = excluded.owner_id;

    return query
    select exists (
        select 1
        from telegram_poller_leases
        where lease_name = 'customer-telegram-poller'
          and owner_id = p_owner_id
          and expires_at > statement_timestamp()
    );
end;
$$;

create or replace function renew_telegram_poller_lease(
    p_owner_id uuid,
    p_lease_seconds integer default 30
)
returns table (renewed boolean)
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_lease_seconds < 10 or p_lease_seconds > 300 then
        raise exception 'lease duration must be between 10 and 300 seconds';
    end if;

    update telegram_poller_leases
    set
        expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
        updated_at = statement_timestamp()
    where lease_name = 'customer-telegram-poller'
      and owner_id = p_owner_id
      and expires_at > statement_timestamp();

    return query select found;
end;
$$;

create or replace function release_telegram_poller_lease(p_owner_id uuid)
returns table (released boolean)
language plpgsql
security definer
set search_path = public
as $$
begin
    delete from telegram_poller_leases
    where lease_name = 'customer-telegram-poller'
      and owner_id = p_owner_id;

    return query select found;
end;
$$;

revoke all on table telegram_poller_leases from public, anon, authenticated;
revoke execute on function acquire_telegram_poller_lease(uuid, integer)
from public, anon, authenticated;
revoke execute on function renew_telegram_poller_lease(uuid, integer)
from public, anon, authenticated;
revoke execute on function release_telegram_poller_lease(uuid)
from public, anon, authenticated;
grant execute on function acquire_telegram_poller_lease(uuid, integer) to service_role;
grant execute on function renew_telegram_poller_lease(uuid, integer) to service_role;
grant execute on function release_telegram_poller_lease(uuid) to service_role;