begin;

select plan(12);

select has_table('public', 'users', 'users table exists');
select has_table('public', 'network_configs', 'network_configs table exists');
select has_table('public', 'wallets', 'wallets table exists');
select has_table('public', 'orders', 'orders table exists');
select has_table('public', 'order_financial_snapshots', 'financial snapshots table exists');
select has_table('public', 'receipt_submissions', 'receipt submissions table exists');
select has_table('public', 'receipt_evidence', 'receipt evidence table exists');
select has_table('public', 'receipt_verification_results', 'receipt verification results table exists');
select has_table('public', 'admin_users', 'admin users table exists');
select has_table('public', 'audit_logs', 'audit logs table exists');

select is(
  (select count(*)::integer from public.network_configs where enabled),
  2,
  'exactly two networks are enabled at launch'
);

select is(
  (select string_agg(code::text, ',' order by code) from public.network_configs where enabled),
  'BEP20,TRC20',
  'only BEP20 and TRC20 are enabled at launch'
);

select * from finish();
rollback;
