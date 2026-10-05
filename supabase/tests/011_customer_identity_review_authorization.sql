begin;

select plan(3);

select ok(
  to_regprocedure('public.list_pending_customer_identity_submissions(bigint,admin_actor_type)') is not null,
  'identity queue listing RPC exists'
);

-- These calls intentionally run with no pending identity records. Authorization
-- must still be evaluated before the select can return an empty queue.
select throws_ok(
  $$select * from list_pending_customer_identity_submissions(0, 'primary'::admin_actor_type)$$,
  'P0001',
  'admin identity is required',
  'an invalid primary identity cannot inspect an empty queue'
);
select throws_ok(
  $$select * from list_pending_customer_identity_submissions(1, 'backup'::admin_actor_type)$$,
  'P0001',
  'only the primary administrator may review customer identity',
  'a backup administrator cannot inspect an empty queue'
);

select * from finish();
rollback;