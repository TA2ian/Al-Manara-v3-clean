-- Remove the final output-parameter collision from fulfillment completion.
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
        'delete[[:space:]]+from[[:space:]]+order_fulfillment_claims[[:space:]]+where[[:space:]]+internal_order_id[[:space:]]*=[[:space:]]*p_order_id',
        'delete from order_fulfillment_claims where order_fulfillment_claims.internal_order_id = p_order_id',
        1,
        0,
        'i'
    );
    execute v_definition;
end
$$;
