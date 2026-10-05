-- Al-Manara v2 — persistence contract hardening
-- Applies after 0001_initial_schema.sql.

alter table admin_payment_accounts
  add column currency currency_code;

update admin_payment_accounts
set currency = 'USD'
where currency is null;

alter table admin_payment_accounts
  alter column currency set not null;

alter table admin_payment_accounts
  drop constraint if exists admin_payment_accounts_payment_method_id_key;

create unique index admin_payment_accounts_method_currency_uq
  on admin_payment_accounts(payment_method_id, currency);

create or replace function enforce_receipt_attempt_limit()
returns trigger
language plpgsql
as $$
declare
  existing_attempts integer;
begin
  -- Serialize attempt allocation per order so concurrent receipt submissions
  -- cannot observe the same attempt count and claim the same attempt number.
  perform pg_advisory_xact_lock(hashtextextended(new.internal_order_id::text, 0));

  select count(*) into existing_attempts
  from receipt_submissions
  where internal_order_id = new.internal_order_id;

  if existing_attempts >= 3 then
    raise exception 'receipt attempt limit exceeded for order %', new.internal_order_id;
  end if;

  if new.attempt_number <> existing_attempts + 1 then
    raise exception 'receipt attempt number must be sequential';
  end if;

  return new;
end;
$$;

create trigger receipt_submissions_attempt_limit
before insert on receipt_submissions
for each row execute function enforce_receipt_attempt_limit();

create table admin_totp_credentials (
  telegram_user_id bigint primary key references admin_users(telegram_user_id) on delete restrict,
  secret_ciphertext text not null,
  encryption_key_version text not null,
  enabled boolean not null default true,
  last_accepted_time_step bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table admin_step_up_confirmations (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null references admin_users(telegram_user_id) on delete restrict,
  actor_type admin_actor_type not null,
  target_type text not null,
  target_id text not null,
  action text not null,
  expected_version bigint,
  totp_time_step bigint not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  idempotency_key text not null unique,
  constraint step_up_expiry_valid check (expires_at > created_at)
);
create index admin_step_up_target_idx
  on admin_step_up_confirmations(target_type, target_id, action, created_at desc);

create unique index exchange_rates_active_pair_uq
  on exchange_rates(currency_pair)
  where status = 'ACTIVE';

create unique index order_financial_snapshots_order_uq
  on order_financial_snapshots(internal_order_id);

DO $$
DECLARE
  enabled_count integer;
BEGIN
  SELECT count(*) INTO enabled_count FROM network_configs WHERE enabled;
  IF enabled_count <> 2 THEN
    RAISE EXCEPTION 'launch requires exactly two enabled networks';
  END IF;
  IF EXISTS (
    SELECT 1 FROM network_configs
    WHERE enabled AND code NOT IN ('BEP20', 'TRC20')
  ) THEN
    RAISE EXCEPTION 'only BEP20 and TRC20 may be enabled at launch';
  END IF;
END;
$$;
