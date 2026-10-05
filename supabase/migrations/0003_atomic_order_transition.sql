create or replace function transition_order_if_version(
    p_order_id uuid,
    p_target_status order_status,
    p_expected_version bigint,
    p_actor_telegram_user_id bigint default null,
    p_actor_type admin_actor_type default null,
    p_event_payload jsonb default '{}'::jsonb
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_current_status order_status;
    v_current_version bigint;
    v_new_version bigint;
begin
    if p_expected_version <= 0 then
        raise exception 'expected version must be positive';
    end if;

    if p_actor_type is null and p_actor_telegram_user_id is not null then
        raise exception 'actor type is required when actor id is supplied';
    end if;

    if p_actor_type is not null and p_actor_telegram_user_id is null then
        raise exception 'actor id is required for admin audit actor';
    end if;

    select o.status, o.version
      into v_current_status, v_current_version
      from orders o
     where o.internal_order_id = p_order_id
     for update;

    if not found then
        raise exception 'order not found';
    end if;

    if v_current_version <> p_expected_version then
        raise exception using
            errcode = 'P0001',
            message = 'stale order version',
            detail = format('expected=%s current=%s', p_expected_version, v_current_version);
    end if;

    if p_target_status = v_current_status then
        return query
        select o.internal_order_id, o.public_order_code, o.status, o.version
          from orders o
         where o.internal_order_id = p_order_id;
        return;
    end if;

    if not (
        (v_current_status = 'DRAFT' and p_target_status in ('PENDING_PAYMENT', 'CANCELLED')) or
        (v_current_status = 'PENDING_PAYMENT' and p_target_status in ('PAYMENT_SUBMITTED', 'EXPIRED', 'CANCELLED')) or
        (v_current_status = 'PAYMENT_SUBMITTED' and p_target_status = 'UNDER_REVIEW') or
        (v_current_status = 'UNDER_REVIEW' and p_target_status in ('APPROVED', 'REJECTED', 'CLARIFICATION_REQUIRED')) or
        (v_current_status = 'CLARIFICATION_REQUIRED' and p_target_status in ('PAYMENT_SUBMITTED', 'UNDER_REVIEW', 'CANCELLED')) or
        (v_current_status = 'APPROVED' and p_target_status = 'COMPLETED')
    ) then
        raise exception 'invalid order transition: % -> %', v_current_status, p_target_status;
    end if;

    v_new_version := v_current_version + 1;

    update orders as o
       set status = p_target_status,
           version = v_new_version,
           approved_at = case when p_target_status = 'APPROVED' then coalesce(o.approved_at, now()) else o.approved_at end,
           completed_at = case when p_target_status = 'COMPLETED' then coalesce(o.completed_at, now()) else o.completed_at end,
           cancelled_at = case when p_target_status = 'CANCELLED' then coalesce(o.cancelled_at, now()) else o.cancelled_at end,
           updated_at = now()
     where o.internal_order_id = p_order_id
       and o.version = p_expected_version;

    if not found then
        raise exception 'order changed during transition';
    end if;

    insert into audit_logs (
        actor_telegram_user_id,
        actor_type,
        action,
        target_type,
        target_id,
        old_value,
        new_value,
        metadata
    ) values (
        p_actor_telegram_user_id,
        p_actor_type,
        'order.status_changed',
        'order',
        p_order_id::text,
        jsonb_build_object('status', v_current_status, 'version', p_expected_version),
        jsonb_build_object('status', p_target_status, 'version', v_new_version),
        coalesce(p_event_payload, '{}'::jsonb) || jsonb_build_object('public_order_code', (select o.public_order_code from orders o where o.internal_order_id = p_order_id))
    );

    return query
    select o.internal_order_id, o.public_order_code, o.status, o.version
      from orders o
     where o.internal_order_id = p_order_id;
end;
$$;
