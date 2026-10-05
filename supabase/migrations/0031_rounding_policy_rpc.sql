-- The financial snapshot must record the active rounding policy from persisted settings.
-- This backend-only RPC prevents the application from drifting from DB configuration.

create or replace function get_current_rounding_policy()
returns table (version text)
language plpgsql
security invoker
set search_path = public
as $$
begin
    return query
    select s.rounding_policy_version
      from settings s
     where s.id = true;
end;
$$;

DO $$
BEGIN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION get_current_rounding_policy() FROM public, anon, authenticated';
    EXECUTE 'GRANT EXECUTE ON FUNCTION get_current_rounding_policy() TO service_role';
END
$$;
