-- Read-only RPCs used by the application persistence boundary.
-- Concurrency and authorization remain authoritative in transition_order_if_version.

create or replace function get_order_for_transition(p_order_id uuid)
returns table (
    internal_order_id uuid,
    public_order_code text,
    status order_status,
    version bigint
)
language sql
security invoker
set search_path = public
as $$
    select o.internal_order_id, o.public_order_code, o.status, o.version
      from orders o
     where o.internal_order_id = p_order_id;
$$;

create or replace function authorize_admin_order_review(
    p_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_actor_type admin_actor_type;
    v_emergency_only boolean;
begin
    if p_telegram_user_id <= 0 then
        return false;
    end if;

    select a.actor_type, a.emergency_only
      into v_actor_type, v_emergency_only
      from admin_users a
     where a.telegram_user_id = p_telegram_user_id
       and a.enabled = true;

    if not found then
        return false;
    end if;

    if v_actor_type is distinct from p_actor_type then
        return false;
    end if;

    -- Backup actors are emergency-only. The application may expose the same
    -- review command, but the database remains the final authorization gate.
    return p_actor_type = 'primary' or (p_actor_type = 'backup' and v_emergency_only);
end;
$$;
