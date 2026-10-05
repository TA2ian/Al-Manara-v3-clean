-- Defense in depth: COMPLETED must only be produced by the fulfillment workflow.
-- The deferred constraint lets complete_order_fulfillment finish its atomic work
-- (audit + durable idempotency result) before the invariant is evaluated.

create or replace function enforce_fulfillment_completion_guard()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
    if old.status is distinct from 'COMPLETED'::order_status
       and new.status = 'COMPLETED'::order_status then
        if not exists (
            select 1
              from order_fulfillment_idempotency f
             where f.internal_order_id = new.internal_order_id
               and f.operation = 'complete'
               and (f.result->>'status') = 'COMPLETED'
               and (f.result->>'version')::bigint = new.version
        ) then
            raise exception 'COMPLETED orders require fulfillment completion';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists orders_fulfillment_completion_guard on orders;

create constraint trigger orders_fulfillment_completion_guard
after update of status on orders
deferrable initially deferred
for each row
execute function enforce_fulfillment_completion_guard();
