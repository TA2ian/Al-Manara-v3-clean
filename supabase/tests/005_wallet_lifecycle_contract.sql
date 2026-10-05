begin;

select plan(19);

select ok(to_regclass('public.wallets') is not null, 'wallet table exists');
select ok(exists (select 1 from information_schema.columns where table_schema='public' and table_name='wallets' and column_name='label'), 'wallet label is persisted');
select ok(exists (select 1 from information_schema.columns where table_schema='public' and table_name='wallets' and column_name='qr_image_file_id'), 'wallet QR file id is persisted');
select ok(to_regprocedure('public.disable_wallet_if_allowed(uuid,uuid)') is not null, 'wallet disable operation exists');
select ok(not exists (select 1 from pg_proc where proname='delete_wallet_if_allowed'), 'physical wallet deletion function is absent');
select ok(not exists (select 1 from pg_trigger where tgrelid='public.wallets'::regclass and tgname='wallets_active_order_delete_guard' and not tgisinternal), 'physical deletion guard is removed from the lifecycle');
select ok(exists (select 1 from pg_trigger where tgrelid='public.orders'::regclass and tgname='orders_wallet_guard' and not tgisinternal), 'orders enforce verified wallet usage');

insert into users (id, telegram_user_id) values ('00000000-0000-0000-0000-000000009901', 9900000001);
insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
values
('00000000-0000-0000-0000-000000009902', '00000000-0000-0000-0000-000000009901', 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'VERIFIED', 'Primary', 'QR-9902', now()),
('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000009901', 'TRC20', 'T11111111111111111111111111111111', 't11111111111111111111111111111111', 'VERIFIED', 'Secondary', 'QR-9903', now());

select throws_ok($$insert into wallets (user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at) values ('00000000-0000-0000-0000-000000009901', 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'VERIFIED', 'Duplicate', 'QR-DUP', now())$$, '23505', 'duplicate key value violates unique constraint "wallets_user_network_address_active_uq"', 'duplicate active wallet address is rejected');
select throws_ok($$update wallets set label='Changed' where id='00000000-0000-0000-0000-000000009902'$$, 'P0001', 'verified wallets are immutable', 'verified wallet identity fields cannot be changed');

insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status, version)
select '00000000-0000-0000-0000-000000009904', 'ORD-WALLET-9904', '00000000-0000-0000-0000-000000009901', '00000000-0000-0000-0000-000000009902', 'BEP20', id, 'APPROVED', 1 from payment_methods where code='SHAM_CASH';

select is(disable_wallet_if_allowed('00000000-0000-0000-0000-000000009902', '00000000-0000-0000-0000-000000009901'), true, 'verified wallet can be disabled even when referenced by an order');
select is((select status::text from wallets where id='00000000-0000-0000-0000-000000009902'), 'DISABLED', 'wallet status becomes DISABLED');
select ok((select disabled_at is not null from wallets where id='00000000-0000-0000-0000-000000009902'), 'disabling records disabled_at');
select ok((select status::text from orders where internal_order_id='00000000-0000-0000-0000-000000009904') = 'APPROVED', 'historical order remains valid after wallet disable');
select throws_ok($$insert into orders (internal_order_id, public_order_code, user_id, wallet_id, network_code, payment_method_id, status, version) select '00000000-0000-0000-0000-000000009906', 'ORD-WALLET-9906', '00000000-0000-0000-0000-000000009901', '00000000-0000-0000-0000-000000009902', 'BEP20', id, 'DRAFT', 1 from payment_methods where code='SHAM_CASH'$$, 'P0001', 'order wallet must be verified', 'disabled wallet cannot be used by a new order');
select is(disable_wallet_if_allowed('00000000-0000-0000-0000-000000009902', '00000000-0000-0000-0000-000000009901'), false, 'disabled wallet cannot be disabled again');
select throws_ok($$update wallets set status='VERIFIED' where id='00000000-0000-0000-0000-000000009902'$$, 'P0001', 'disabled wallets are immutable and cannot be reactivated', 'disabled wallet cannot be reactivated by direct update');

insert into wallets (id, user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
values ('00000000-0000-0000-0000-000000009905', '00000000-0000-0000-0000-000000009901', 'BEP20', '0x1111111111111111111111111111111111111111', '0x1111111111111111111111111111111111111111', 'PENDING', 'Replacement', 'QR-9905', null);
select ok(exists (select 1 from wallets where id='00000000-0000-0000-0000-000000009905'), 'replacement wallet may reuse a disabled historical address');
select is(disable_wallet_if_allowed('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000009901'), true, 'second verified wallet can also be disabled');
select is(disable_wallet_if_allowed('00000000-0000-0000-0000-000000009903', '00000000-0000-0000-0000-000000000001'), false, 'wallet ownership is enforced by disable operation');

select * from finish();
rollback;
