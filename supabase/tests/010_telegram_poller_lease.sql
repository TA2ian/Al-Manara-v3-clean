begin;

select plan(18);

select ok(
  to_regprocedure('public.acquire_telegram_poller_lease(uuid,integer)') is not null,
  'lease acquisition RPC exists'
);
select ok(
  to_regprocedure('public.renew_telegram_poller_lease(uuid,integer)') is not null,
  'lease renewal RPC exists'
);
select ok(
  to_regprocedure('public.release_telegram_poller_lease(uuid)') is not null,
  'lease release RPC exists'
);
select is(
  (select acquired from acquire_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004001', 30
  )),
  true,
  'first host acquires the lease'
);
select is(
  (select acquired from acquire_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004002', 30
  )),
  false,
  'second host cannot acquire a healthy lease'
);
select is(
  (select renewed from renew_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004002', 30
  )),
  false,
  'a non-owner cannot renew the lease'
);
select is(
  (select released from release_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004002'
  )),
  false,
  'a non-owner cannot release the lease'
);

update telegram_poller_leases
set
  updated_at = statement_timestamp() - interval '2 seconds',
  expires_at = statement_timestamp() - interval '1 second'
where lease_name = 'customer-telegram-poller';

select is(
  (select acquired from acquire_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004002', 30
  )),
  true,
  'a new host acquires the lease after unclean-stop expiry'
);
select is(
  (select renewed from renew_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004001', 30
  )),
  false,
  'the former owner cannot renew after the lease is taken over'
);
select is(
  (select released from release_telegram_poller_lease(
    '00000000-0000-0000-0000-000000004002'
  )),
  true,
  'the active owner releases the lease cleanly'
);
select is(
  (select count(*)::integer from telegram_poller_leases),
  0,
  'clean release removes the lease row'
);
select ok(
  (select prosecdef from pg_proc
   where oid = 'public.acquire_telegram_poller_lease(uuid,integer)'::regprocedure),
  'lease acquisition executes with database-owned privileges'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.acquire_telegram_poller_lease(uuid,integer)',
    'EXECUTE'
  ),
  'anonymous callers cannot acquire the lease'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.acquire_telegram_poller_lease(uuid,integer)',
    'EXECUTE'
  ),
  'service role can acquire the lease'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.renew_telegram_poller_lease(uuid,integer)',
    'EXECUTE'
  ),
  'anonymous callers cannot renew the lease'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.renew_telegram_poller_lease(uuid,integer)',
    'EXECUTE'
  ),
  'service role can renew the lease'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.release_telegram_poller_lease(uuid)',
    'EXECUTE'
  ),
  'anonymous callers cannot release the lease'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.release_telegram_poller_lease(uuid)',
    'EXECUTE'
  ),
  'service role can release the lease'
);

select * from finish();
rollback;