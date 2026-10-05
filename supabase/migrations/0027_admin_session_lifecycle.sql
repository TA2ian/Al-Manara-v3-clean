-- Explicit administrative session lifecycle. Session creation/revocation is
-- authoritative in the database and is never inferred from Telegram context.
create or replace function create_admin_session(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns table (session_id uuid, expires_at timestamptz)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_timeout integer;
    v_session_id uuid;
    v_expires timestamptz;
begin
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if not exists (
        select 1 from admin_users au
         where au.telegram_user_id = p_admin_telegram_user_id
           and au.enabled
           and au.actor_type = p_actor_type
           and (au.actor_type = 'primary' or au.emergency_only)
    ) then raise exception 'admin is not enabled'; end if;

    select admin_session_timeout_seconds into v_timeout from settings where id = true;
    if v_timeout is null or v_timeout <= 0 then raise exception 'admin session timeout is invalid'; end if;

    insert into admin_sessions(admin_telegram_user_id, expires_at)
    values (p_admin_telegram_user_id, now() + make_interval(secs => v_timeout))
    returning id, admin_sessions.expires_at into v_session_id, v_expires;

    insert into audit_logs(actor_telegram_user_id, actor_type, action, target_type, target_id, new_value)
    values (p_admin_telegram_user_id, p_actor_type, 'admin.session.created', 'admin_session', v_session_id::text,
            jsonb_build_object('expires_at', v_expires));

    return query select v_session_id, v_expires;
end;
$$;

create or replace function revoke_admin_session(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_session_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_changed boolean;
begin
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if not exists (
        select 1 from admin_users au
         where au.telegram_user_id = p_admin_telegram_user_id
           and au.enabled
           and au.actor_type = p_actor_type
           and (au.actor_type = 'primary' or au.emergency_only)
    ) then raise exception 'admin is not enabled'; end if;

    update admin_sessions
       set revoked_at = now()
     where id = p_session_id
       and admin_telegram_user_id = p_admin_telegram_user_id
       and revoked_at is null;
    v_changed := found;

    if v_changed then
        insert into audit_logs(actor_telegram_user_id, actor_type, action, target_type, target_id)
        values (p_admin_telegram_user_id, p_actor_type, 'admin.session.revoked', 'admin_session', p_session_id::text);
    end if;
    return v_changed;
end;
$$;
