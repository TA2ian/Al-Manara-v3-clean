begin;

select plan(13);

select ok(to_regprocedure('public.get_customer_payment_identity(bigint)') is not null, 'customer identity RPC exists');
select ok(to_regprocedure('public.get_admin_payment_account(currency_code)') is not null, 'admin payment RPC exists');
select ok(to_regprocedure('public.get_network_config(network_code)') is not null, 'network config RPC exists');

insert into users (id, telegram_user_id, verified_name, verified_shamcash_account, payment_identity_verified_at)
values ('00000000-0000-0000-0000-000000009921', 9921000001, 'Customer 9921', 'SC-9921', now());
insert into users (id, telegram_user_id)
values ('00000000-0000-0000-0000-000000009922', 9921000002);

select is((select verified_name from get_customer_payment_identity(9921000001)), 'Customer 9921', 'verified customer identity is returned');
select is((select verified_shamcash_account from get_customer_payment_identity(9921000001)), 'SC-9921', 'verified ShamCash identity is returned');
select is((select count(*)::integer from get_customer_payment_identity(9921000002)), 0, 'unverified customer identity is not returned');

insert into admin_payment_accounts (payment_method_id, account_name, account_number, currency, qr_image_file_id)
select id, 'Admin 9921', 'ADMIN-9921', 'USD', 'QR-9921'
from payment_methods where code='SHAM_CASH';

select is((select account_name from get_admin_payment_account('USD')), 'Admin 9921', 'active ShamCash account is returned');
select is((select account_number from get_admin_payment_account('USD')), 'ADMIN-9921', 'admin account number is returned');
select is((select qr_image_file_id from get_admin_payment_account('USD')), 'QR-9921', 'admin QR file id is returned');

select is((select code::text from get_network_config('BEP20')), 'BEP20', 'network code is returned');
select is((select enabled from get_network_config('BEP20')), true, 'enabled network state is returned');
select is((select min_amount from get_network_config('BEP20')), 0.001::numeric, 'network minimum is returned');
select is((select max_amount from get_network_config('BEP20')), 1000000::numeric, 'network maximum is returned');

select * from finish();
rollback;
