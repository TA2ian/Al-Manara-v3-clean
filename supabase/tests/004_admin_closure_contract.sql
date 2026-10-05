begin;

select plan(8);

select ok(exists (select 1 from pg_type where typname='order_status' and 'CLOSED_WITHOUT_FULFILLMENT' = any(enum_range(null::order_status)::text[])), 'closure state exists');
select ok(to_regclass('public.admin_sessions') is not null, 'admin session table exists');
select ok(to_regclass('public.order_fulfillment_claims') is not null, 'fulfillment claim table exists');
select ok(to_regprocedure('public.close_order_without_fulfillment(uuid,bigint,bigint,uuid,text,text)') is not null, 'atomic closure function exists');

insert into admin_payment_accounts (payment_method_id, currency, account_name, account_number, qr_image_file_id, is_active)
select id, 'USD', 'Closure USD Account', 'CLOSURE-USD-001', 'CLOSURE-USD-QR', true
from payment_methods where code='SHAM_CASH';

insert into admin_payment_accounts (payment_method_id, currency, account_name, account_number, qr_image_file_id, is_active)
select id, 'NEW.SYP', 'Closure SYP Account', 'CLOSURE-SYP-001', 'CLOSURE-SYP-QR', true
from payment_methods where code='SHAM_CASH';

select is((select count(*)::integer from admin_payment_accounts where account_number like 'CLOSURE-%'), 2, 'same payment method supports currency-scoped accounts');
select ok(exists (select 1 from admin_payment_accounts a join payment_methods p on p.id=a.payment_method_id where p.code='SHAM_CASH' and a.currency='USD'), 'USD account is addressable by currency');
select ok(exists (select 1 from admin_payment_accounts a join payment_methods p on p.id=a.payment_method_id where p.code='SHAM_CASH' and a.currency='NEW.SYP'), 'NEW.SYP account is addressable by currency');
select ok(not exists (select 1 from orders where status='CLOSED_WITHOUT_FULFILLMENT'), 'closure test does not mutate an order');

select * from finish();
rollback;
