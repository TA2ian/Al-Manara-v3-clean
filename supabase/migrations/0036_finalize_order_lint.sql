-- Final cleanup for the remaining unqualified order.version expression.
DO $$
declare
    v_function oid := to_regprocedure('public.complete_order_fulfillment(uuid,bigint,bigint,admin_actor_type,text)');
    v_definition text;
begin
    if v_function is null then
        raise exception 'complete_order_fulfillment is missing';
    end if;

    select pg_get_functiondef(v_function) into v_definition;
    v_definition := regexp_replace(
        v_definition,
        'version[[:space:]]*=[[:space:]]*version[[:space:]]*[+][[:space:]]*1',
        'version = o.version + 1',
        1,
        0,
        'i'
    );
    execute v_definition;
end
$$;
