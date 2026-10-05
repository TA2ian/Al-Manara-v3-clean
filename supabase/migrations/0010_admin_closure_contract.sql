-- Administrative closure without fulfillment.
-- This is deliberately separate from normal customer order transitions so the
-- privileged operation can enforce session ownership, reason, and fulfillment
-- claim absence atomically.

alter type order_status add value if not exists 'CLOSED_WITHOUT_FULFILLMENT';

create table if not exists admin_sessions (
    id uuid primary key default gen_random_uuid(),
    admin_telegram_user_id bigint not null references admin_users(telegram_user_id) on delete restrict,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz,
    constraint admin_session_expiry check (expires_at > created_at)
);
create index if not exists admin_sessions_admin_active_idx
    on admin_sessions(admin_telegram_user_id, expires_at)
    where revoked_at is null;

create table if not exists order_fulfillment_claims (
    internal_order_id uuid primary key references orders(internal_order_id) on delete cascade,
    admin_telegram_user_id bigint not null references admin_users(telegram_user_id) on delete restrict,
    claimed_at timestamptz not null default now()
);
create index if not exists order_fulfillment_claims_admin_idx
    on order_fulfillment_claims(admin_telegram_user_id);

create or replace function close_order_without_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_session_id uuid,
    p_reason text,
    p_idempotency_key text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing jsonb;
    v_status order_status;
    v_version bigint;
    v_actor_type admin_actor_type;
    v_reason text := btrim(coalesce(p_reason, ''));
begin
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if length(v_reason) < 3 or length(v_reason) > 1000 then raise exception 'closure reason is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;

    select ik.response_json into v_existing
      from idempotency_keys ik
     where ik.telegram_user_id = p_admin_telegram_user_id
       and ik.operation = 'close_order_without_fulfillment'
       and ik.idempotency_key = p_idempotency_key
     for update;
    if found then
        return query select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            true;
        return;
    end if;

    select au.actor_type into v_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;

    if not exists (
        select 1 from admin_sessions s
         where s.id = p_session_id
           and s.admin_telegram_user_id = p_admin_telegram_user_id
           and s.revoked_at is null
           and s.expires_at > now()
    ) then
        raise exception 'admin session is invalid or expired';
    end if;

    select o.status, o.version into v_status, v_version
      from orders o where o.internal_order_id = p_order_id for update;
    if not found then raise exception 'order not found'; end if;
    if v_version <> p_expected_version then
        raise exception using errcode='P0001', message='stale order version', detail=format('expected=%s current=%s', p_expected_version, v_version);
    end if;
    if v_status <> 'APPROVED' then raise exception 'order is not eligible for administrative closure'; end if;

    if exists (select 1 from order_fulfillment_claims fc where fc.internal_order_id = p_order_id) then
        raise exception 'order has an active fulfillment claim';
    end if;

    update orders as o
       set status = 'CLOSED_WITHOUT_FULFILLMENT',
           version = o.version + 1,
           updated_at = now()
     where o.internal_order_id = p_order_id
       and o.version = p_expected_version;

    if not found then raise exception 'order changed concurrently'; end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'order.closed_without_fulfillment', 'order', p_order_id::text,
        jsonb_build_object('status', v_status, 'version', p_expected_version),
        jsonb_build_object('status', 'CLOSED_WITHOUT_FULFILLMENT', 'version', p_expected_version + 1, 'reason', v_reason),
        jsonb_build_object('session_id', p_session_id, 'reason', v_reason)
    );

    insert into idempotency_keys (telegram_user_id, operation, idempotency_key, response_json)
    values (
        p_admin_telegram_user_id, 'close_order_without_fulfillment', p_idempotency_key,
        jsonb_build_object('internal_order_id', p_order_id, 'public_order_code', (select o.public_order_code from orders o where o.internal_order_id=p_order_id), 'status', 'CLOSED_WITHOUT_FULFILLMENT', 'version', p_expected_version + 1)
    );

    return query select o.internal_order_id, o.public_order_code, o.status, o.version, false
      from orders o where o.internal_order_id = p_order_id;
end;
$$;
