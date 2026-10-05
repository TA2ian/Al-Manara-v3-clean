-- The service-role RPC client executes the reviewer guard as an invoker.
-- Grant its existing authorization dependency explicitly and make the role
-- comparison safe if the function is ever invoked outside the Telegram path.

create or replace function assert_primary_identity_reviewer(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns void
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_actor_type is distinct from 'primary' then
        raise exception 'only the primary administrator may review customer identity';
    end if;
    perform assert_enabled_admin(p_admin_telegram_user_id, p_actor_type);
end;
$$;

grant execute on function assert_enabled_admin(bigint, admin_actor_type) to service_role;