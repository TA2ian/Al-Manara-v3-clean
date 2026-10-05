-- Fulfillment is an operational step, not a generic order transition.
-- The lifecycle is UNDER_REVIEW -> APPROVED -> claim -> COMPLETED.
-- Administrative closure remains a separate APPROVED -> CLOSED_WITHOUT_FULFILLMENT path.

create table if not exists order_fulfillment_idempotency (
    idempotency_key text primary key,
    operation text not null,
    internal_order_id uuid not null references orders(internal_order_id) on delete restrict,
    admin_telegram_user_id bigint not null references admin_users(telegram_user_id) on delete restrict,
    expected_version bigint not null,
    result jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint fulfillment_idempotency_operation check (operation in ('claim','complete')),
    constraint fulfillment_idempotency_key_len check (length(btrim(idempotency_key)) between 1 and 128),
    constraint fulfillment_idempotency_version_positive check (expected_version > 0),
    constraint fulfillment_idempotency_admin_positive check (admin_telegram_user_id > 0)
);

create index if not exists order_fulfillment_idempotency_order_idx
    on order_fulfillment_idempotency(internal_order_id, operation, created_at desc);

create or replace function claim_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    admin_telegram_user_id bigint,
    claimed_at timestamptz,
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
    v_claimed_at timestamptz;
    v_order_code text;
    v_result jsonb;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
    end if;

    select au.actor_type into v_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;
    if v_actor_type <> p_actor_type then raise exception 'admin actor type mismatch'; end if;

    select f.result into v_existing
      from order_fulfillment_idempotency f
     where f.idempotency_key = btrim(p_idempotency_key)
       and f.operation = 'claim'
     for update;
    if found then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'admin_telegram_user_id')::bigint <> p_admin_telegram_user_id
        then
            raise exception 'idempotency key belongs to another fulfillment operation';
        end if;
        return query select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'admin_telegram_user_id')::bigint,
            (v_existing->>'claimed_at')::timestamptz,
            true;
        return;
    end if;

    select o.status, o.version, o.public_order_code into v_status, v_version, v_order_code
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_version <> p_expected_version then
        raise exception using errcode='P0001', message='stale order version', detail=format('expected=%s current=%s', p_expected_version, v_version);
    end if;
    if v_status <> 'APPROVED' then raise exception 'order is not eligible for fulfillment claim'; end if;

    if exists (select 1 from order_fulfillment_claims fc where fc.internal_order_id = p_order_id) then
        raise exception 'order already has an active fulfillment claim';
    end if;

    v_claimed_at := now();
    insert into order_fulfillment_claims (internal_order_id, admin_telegram_user_id, claimed_at)
    values (p_order_id, p_admin_telegram_user_id, v_claimed_at);

    -- Claim ownership advances the order version so a stale closure/completion
    -- request cannot operate on the pre-claim representation.
    update orders
       set version = version + 1,
           updated_at = now()
     where internal_order_id = p_order_id
       and version = p_expected_version;
    if not found then raise exception 'order changed concurrently'; end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'order.fulfillment_claimed', 'order', p_order_id::text,
        jsonb_build_object('status', v_status, 'version', p_expected_version),
        jsonb_build_object('status', v_status, 'version', p_expected_version + 1, 'admin_telegram_user_id', p_admin_telegram_user_id),
        jsonb_build_object('operation', 'fulfillment_claim')
    );

    v_result := jsonb_build_object(
        'internal_order_id', p_order_id,
        'public_order_code', v_order_code,
        'status', v_status::text,
        'version', p_expected_version + 1,
        'admin_telegram_user_id', p_admin_telegram_user_id,
        'claimed_at', v_claimed_at
    );
    insert into order_fulfillment_idempotency (idempotency_key, operation, internal_order_id, admin_telegram_user_id, expected_version, result)
    values (btrim(p_idempotency_key), 'claim', p_order_id, p_admin_telegram_user_id, p_expected_version, v_result);

    return query select p_order_id, v_order_code, v_status, p_expected_version + 1, p_admin_telegram_user_id, v_claimed_at, false;
end;
$$;

create or replace function complete_order_fulfillment(
    p_order_id uuid,
    p_expected_version bigint,
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_idempotency_key text
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint,
    completed_at timestamptz,
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
    v_claim_admin bigint;
    v_completed_at timestamptz;
    v_order_code text;
    v_result jsonb;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_expected_version <= 0 then raise exception 'expected version must be positive'; end if;
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 or length(btrim(p_idempotency_key)) > 128 then
        raise exception 'idempotency key must be between 1 and 128 characters';
    end if;

    select au.actor_type into v_actor_type
      from admin_users au
     where au.telegram_user_id = p_admin_telegram_user_id
       and au.enabled
       and (au.actor_type = 'primary' or au.emergency_only)
     for share;
    if not found then raise exception 'admin is not enabled'; end if;
    if v_actor_type <> p_actor_type then raise exception 'admin actor type mismatch'; end if;

    select f.result into v_existing
      from order_fulfillment_idempotency f
     where f.idempotency_key = btrim(p_idempotency_key)
       and f.operation = 'complete'
     for update;
    if found then
        if (v_existing->>'internal_order_id')::uuid <> p_order_id
           or (v_existing->>'admin_telegram_user_id')::bigint <> p_admin_telegram_user_id
        then
            raise exception 'idempotency key belongs to another fulfillment operation';
        end if;
        return query select
            (v_existing->>'internal_order_id')::uuid,
            v_existing->>'public_order_code',
            (v_existing->>'status')::order_status,
            (v_existing->>'version')::bigint,
            (v_existing->>'completed_at')::timestamptz,
            true;
        return;
    end if;

    select o.status, o.version, o.public_order_code into v_status, v_version, v_order_code
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_version <> p_expected_version then
        raise exception using errcode='P0001', message='stale order version', detail=format('expected=%s current=%s', p_expected_version, v_version);
    end if;
    if v_status <> 'APPROVED' then raise exception 'order is not eligible for fulfillment completion'; end if;

    select fc.admin_telegram_user_id into v_claim_admin
      from order_fulfillment_claims fc
     where fc.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'active fulfillment claim is required'; end if;
    if v_claim_admin <> p_admin_telegram_user_id then raise exception 'fulfillment claim belongs to another admin'; end if;

    v_completed_at := now();
    update orders
       set status = 'COMPLETED',
           version = version + 1,
           completed_at = v_completed_at,
           updated_at = now()
     where internal_order_id = p_order_id
       and version = p_expected_version;
    if not found then raise exception 'order changed concurrently'; end if;

    delete from order_fulfillment_claims where internal_order_id = p_order_id;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id,
        old_value, new_value, metadata
    ) values (
        p_admin_telegram_user_id, v_actor_type, 'order.fulfillment_completed', 'order', p_order_id::text,
        jsonb_build_object('status', v_status, 'version', p_expected_version),
        jsonb_build_object('status', 'COMPLETED', 'version', p_expected_version + 1),
        jsonb_build_object('operation', 'fulfillment_completion', 'claim_admin_telegram_user_id', v_claim_admin)
    );

    v_result := jsonb_build_object(
        'internal_order_id', p_order_id,
        'public_order_code', v_order_code,
        'status', 'COMPLETED',
        'version', p_expected_version + 1,
        'completed_at', v_completed_at,
        'admin_telegram_user_id', p_admin_telegram_user_id
    );
    insert into order_fulfillment_idempotency (idempotency_key, operation, internal_order_id, admin_telegram_user_id, expected_version, result)
    values (btrim(p_idempotency_key), 'complete', p_order_id, p_admin_telegram_user_id, p_expected_version, v_result);

    return query select p_order_id, v_order_code, 'COMPLETED'::order_status, p_expected_version + 1, v_completed_at, false;
end;
$$;
