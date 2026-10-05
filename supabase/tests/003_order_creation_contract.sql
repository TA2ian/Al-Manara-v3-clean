begin;

select plan(20);

select ok(
    exists (
        select 1 from pg_proc
        where proname = 'create_purchase_order_atomic'
          and pg_get_function_result(oid) like '%replayed%'
    ),
    'atomic order creation function exposes replay state'
);

select ok(
    exists (
        select 1
        from pg_constraint
        where conrelid = 'public.idempotency_keys'::regclass
          and contype = 'p'
    ),
    'order idempotency key has a primary key'
);

insert into users (telegram_user_id, verified_name, verified_shamcash_account, payment_identity_verified_at)
values (990000001, 'Contract Customer', 'SC-CONTRACT-001', now());

insert into wallets (user_id, network_code, address, normalized_address, status, label, qr_image_file_id, verified_at)
select id, 'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1', 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1', 'VERIFIED', 'Contract Wallet', 'QR-CONTRACT-001', now()
from users where telegram_user_id = 990000001;

insert into admin_payment_accounts (payment_method_id, currency, account_name, account_number, qr_image_file_id, is_active)
select id, 'USD', 'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001', true
from payment_methods where code = 'SHAM_CASH';

insert into admin_payment_accounts (payment_method_id, currency, account_name, account_number, qr_image_file_id, is_active)
select id, 'NEW.SYP', 'SYP Contract Account', 'SYP-ACCOUNT-001', 'SYP-QR-001', true
from payment_methods where code = 'SHAM_CASH';

select lives_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000001', 'ORD-CONTRACT-USD', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1',
        10, 5, 0.5, 9.5, 'USD', null, 10, 'ROUND_HALF_UP:USD=0.01',
        'Contract Customer', 'SC-CONTRACT-001', 'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001',
        now(), now() + interval '10 minutes', 'contract-idem-usd', 'create_purchase_order'
    )$$, 'USD order creation succeeds');

select is((select status::text from orders where internal_order_id = '10000000-0000-0000-0000-000000000001'), 'PENDING_PAYMENT', 'new order starts in PENDING_PAYMENT');
select is((select version from orders where internal_order_id = '10000000-0000-0000-0000-000000000001'), 1::bigint, 'new order starts at version 1');
select is((select payment_currency::text from order_financial_snapshots where internal_order_id = '10000000-0000-0000-0000-000000000001'), 'USD', 'USD financial snapshot preserves currency');
select is((select local_amount from order_financial_snapshots where internal_order_id = '10000000-0000-0000-0000-000000000001'), 10::numeric, 'USD local amount is not converted');
select ok((select expires_at > created_at from orders where internal_order_id = '10000000-0000-0000-0000-000000000001'), 'quote expiry is persisted after order creation');

select lives_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000002', 'ORD-CONTRACT-USD-REPLAY-IGNORED', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1',
        10, 5, 0.5, 9.5, 'USD', null, 10, 'ROUND_HALF_UP:USD=0.01',
        'Contract Customer', 'SC-CONTRACT-001', 'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001',
        now(), now() + interval '10 minutes', 'contract-idem-usd', 'create_purchase_order'
    )$$, 'reusing an idempotency key is replay-safe');
select is((select count(*)::integer from orders where user_id = (select id from users where telegram_user_id = 990000001)), 1, 'idempotency replay does not create a second order');
select is((select public_order_code from orders where internal_order_id = '10000000-0000-0000-0000-000000000001'), 'ORD-CONTRACT-USD', 'idempotency replay keeps the original public order code');

select lives_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000003', 'ORD-CONTRACT-SYP', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1',
        10, 5, 0.5, 9.5, 'NEW.SYP', 10000, 100000, 'ROUND_HALF_UP:NEW.SYP=0.01',
        'Contract Customer', 'SC-CONTRACT-001', 'SYP Contract Account', 'SYP-ACCOUNT-001', 'SYP-QR-001',
        now(), now() + interval '10 minutes', 'contract-idem-syp', 'create_purchase_order'
    )$$, 'NEW.SYP order creation succeeds');
select is((select payment_currency::text from order_financial_snapshots where internal_order_id = '10000000-0000-0000-0000-000000000003'), 'NEW.SYP', 'NEW.SYP financial snapshot preserves currency');
select is((select exchange_rate from order_financial_snapshots where internal_order_id = '10000000-0000-0000-0000-000000000003'), 10000::numeric, 'NEW.SYP snapshot preserves exchange rate');
select is((select local_amount from order_financial_snapshots where internal_order_id = '10000000-0000-0000-0000-000000000003'), 100000::numeric, 'NEW.SYP local amount is calculated from the snapshot rate');
select is((select account_name from admin_payment_accounts apa join payment_methods pm on pm.id = apa.payment_method_id where pm.code = 'SHAM_CASH' and apa.currency = 'NEW.SYP' and apa.is_active), 'SYP Contract Account', 'NEW.SYP order selects the currency-specific admin account');

select throws_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000004', 'ORD-CONTRACT-BAD-WALLET', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'BEP20', '0x0000000000000000000000000000000000000001', 10, 5, 0.5, 9.5,
        'USD', null, 10, 'ROUND_HALF_UP:USD=0.01', 'Contract Customer', 'SC-CONTRACT-001',
        'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001', now(), now() + interval '10 minutes',
        'contract-idem-bad-wallet', 'create_purchase_order'
    )$$, 'P0001', 'wallet network mismatch', 'wallet network mismatch is rejected');

select throws_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000005', 'ORD-CONTRACT-BAD-AMOUNT', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1', 0.0001, 5, 0.000005, 0.000095,
        'USD', null, 0.0001, 'ROUND_HALF_UP:USD=0.01', 'Contract Customer', 'SC-CONTRACT-001',
        'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001', now(), now() + interval '10 minutes',
        'contract-idem-bad-amount', 'create_purchase_order'
    )$$, 'P0001', 'amount is outside network limits', 'amount outside network bounds is rejected');

select throws_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000006', 'ORD-CONTRACT-BAD-IDENTITY', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1', 10, 5, 0.5, 9.5,
        'USD', null, 10, 'ROUND_HALF_UP:USD=0.01', 'Wrong Name', 'SC-CONTRACT-001',
        'USD Contract Account', 'USD-ACCOUNT-001', 'USD-QR-001', now(), now() + interval '10 minutes',
        'contract-idem-bad-identity', 'create_purchase_order'
    )$$, 'P0001', 'customer identity snapshot mismatch', 'customer identity snapshot mismatch is rejected');

select throws_ok($$
    select * from create_purchase_order_atomic(
        '10000000-0000-0000-0000-000000000007', 'ORD-CONTRACT-BAD-ADMIN', 990000001,
        (select id from wallets where normalized_address = 'tqj7f9wr7qfj9nqk4sj2mr7vf4px6ny8z1'),
        'TRC20', 'TQJ7f9wR7QfJ9nQk4sJ2mR7Vf4pX6nY8Z1', 10, 5, 0.5, 9.5,
        'USD', null, 10, 'ROUND_HALF_UP:USD=0.01', 'Contract Customer', 'SC-CONTRACT-001',
        'Wrong USD Account', 'USD-ACCOUNT-001', 'USD-QR-001', now(), now() + interval '10 minutes',
        'contract-idem-bad-admin', 'create_purchase_order'
    )$$, 'P0001', 'admin payment account snapshot mismatch', 'admin payment account snapshot mismatch is rejected');

select * from finish();
rollback;
