begin;

select plan(22);

select ok(
  to_regprocedure('public.list_customer_orders(bigint,integer,integer)') is not null,
  'customer order listing RPC exists'
);
select ok(
  to_regprocedure('public.count_customer_orders(bigint)') is not null,
  'customer order count RPC exists'
);

insert into users (id, telegram_user_id)
values
  ('00000000-0000-0000-0000-000000009901', 9901000001),
  ('00000000-0000-0000-0000-000000009902', 9901000002),
  ('00000000-0000-0000-0000-000000009903', 9901000003);
update users set is_disabled = true where telegram_user_id = 9901000003;

insert into wallets (
  id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id
)
values
  ('00000000-0000-0000-0000-000000009911', '00000000-0000-0000-0000-000000009901', 'BEP20', '0x9901', '0x9901', 'VERIFIED', 'Wallet 9901', 'QR-9901'),
  ('00000000-0000-0000-0000-000000009912', '00000000-0000-0000-0000-000000009902', 'BEP20', '0x9902', '0x9902', 'VERIFIED', 'Wallet 9902', 'QR-9902'),
  ('00000000-0000-0000-0000-000000009913', '00000000-0000-0000-0000-000000009903', 'BEP20', '0x9903', '0x9903', 'VERIFIED', 'Wallet 9903', 'QR-9903');

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status, created_at)
select
  '00000000-0000-0000-0000-000000009921',
  'ORD-9901-OLD',
  '00000000-0000-0000-0000-000000009901',
  '00000000-0000-0000-0000-000000009911',
  'BEP20',
  id,
  'PENDING_PAYMENT',
  now() - interval '1 hour'
from payment_methods where code = 'SHAM_CASH';
insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status, created_at)
select
  '00000000-0000-0000-0000-000000009922',
  'ORD-9901-NEW',
  '00000000-0000-0000-0000-000000009901',
  '00000000-0000-0000-0000-000000009911',
  'BEP20',
  id,
  'UNDER_REVIEW',
  now()
from payment_methods where code = 'SHAM_CASH';
insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status)
select
  '00000000-0000-0000-0000-000000009923',
  'ORD-OTHER',
  '00000000-0000-0000-0000-000000009902',
  '00000000-0000-0000-0000-000000009912',
  'BEP20',
  id,
  'PENDING_PAYMENT'
from payment_methods where code = 'SHAM_CASH';
insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status)
select
  '00000000-0000-0000-0000-000000009924',
  'ORD-DISABLED',
  '00000000-0000-0000-0000-000000009903',
  '00000000-0000-0000-0000-000000009913',
  'BEP20',
  id,
  'PENDING_PAYMENT'
from payment_methods where code = 'SHAM_CASH';

insert into order_financial_snapshots (
  internal_order_id, requested_amount, fee_percent, fee_amount, net_usdt_amount,
  payment_currency, exchange_rate, local_amount, rounding_policy_version, network_config_version
) values
  ('00000000-0000-0000-0000-000000009921', 10, 5, 0.5, 9.5, 'USD', null, 10, 'test', 1),
  ('00000000-0000-0000-0000-000000009922', 20, 5, 1, 19, 'NEW.SYP', 10000, 200000, 'test', 1);

select is(
  (select count(*)::integer from list_customer_orders(9901000001, 0, 5)),
  2,
  'customer sees only their own orders'
);
select is(
  (select count(*)::integer from list_customer_orders(9901000001, 0, 5)
    where public_order_code = 'ORD-OTHER'),
  0,
  'another customer public order code is never returned'
);
select is(
  (select public_order_code from list_customer_orders(9901000001, 0, 5) limit 1),
  'ORD-9901-NEW',
  'orders are newest first'
);
select is(
  (select local_amount from list_customer_orders(9901000001, 0, 5) limit 1),
  200000::numeric,
  'financial snapshot is returned'
);
select is(
  (select total_count from count_customer_orders(9901000001)),
  2::bigint,
  'total count is available independently of pagination'
);
select is(
  (select count(*)::integer from list_customer_orders(9901000001, 1, 1)),
  1,
  'pagination returns a later page'
);
select is(
  (select total_count from count_customer_orders(9901000001)),
  2::bigint,
  'out-of-range pages do not lose total count'
);
select is(
  (select count(*)::integer from list_customer_orders(9901000003, 0, 5)),
  0,
  'disabled customer sees no orders'
);
select ok(
  not exists (
    select 1
    from information_schema.parameters
    where specific_schema = 'public'
      and specific_name like 'list_customer_orders%'
      and parameter_mode = 'OUT'
      and parameter_name = 'internal_order_id'
  ),
  'RPC does not expose internal order identifiers'
);
select throws_ok(
  $$select * from list_customer_orders(9901000001, -1, 5)$$,
  'P0001',
  'page must be non-negative',
  'negative pages are rejected'
);
select ok(
  not (select prosecdef from pg_proc
       where oid = 'public.list_customer_orders(bigint,integer,integer)'::regprocedure),
  'customer listing RPC is security invoker'
);
select ok(
  not (select prosecdef from pg_proc
       where oid = 'public.count_customer_orders(bigint)'::regprocedure),
  'customer count RPC is security invoker'
);
select ok(
  position(
    'search_path=public'
    in coalesce(
      (select array_to_string(proconfig, ',') from pg_proc
       where oid = 'public.list_customer_orders(bigint,integer,integer)'::regprocedure),
      ''
    )
  ) > 0,
  'customer listing RPC fixes its search path'
);
select ok(
  position(
    'search_path=public'
    in coalesce(
      (select array_to_string(proconfig, ',') from pg_proc
       where oid = 'public.count_customer_orders(bigint)'::regprocedure),
      ''
    )
  ) > 0,
  'customer count RPC fixes its search path'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.list_customer_orders(bigint,integer,integer)',
    'EXECUTE'
  ),
  'anonymous callers cannot execute customer listing'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.list_customer_orders(bigint,integer,integer)',
    'EXECUTE'
  ),
  'authenticated callers cannot execute customer listing'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.list_customer_orders(bigint,integer,integer)',
    'EXECUTE'
  ),
  'service role can execute customer listing'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.count_customer_orders(bigint)',
    'EXECUTE'
  ),
  'anonymous callers cannot execute customer count'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.count_customer_orders(bigint)',
    'EXECUTE'
  ),
  'authenticated callers cannot execute customer count'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.count_customer_orders(bigint)',
    'EXECUTE'
  ),
  'service role can execute customer count'
);
select * from finish();
rollback;