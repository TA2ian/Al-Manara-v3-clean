-- Al-Manara v2 — initial persistence schema
-- PostgreSQL 17 compatible. Domain state is authoritative in persisted entities.

create extension if not exists pgcrypto;

create type currency_code as enum ('USD', 'NEW.SYP');
create type network_code as enum ('BEP20', 'TRC20', 'TON', 'ARB', 'ETH', 'SOL');
create type order_status as enum ('DRAFT', 'PENDING_PAYMENT', 'PAYMENT_SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'COMPLETED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'CLARIFICATION_REQUIRED');
create type wallet_status as enum ('PENDING', 'VERIFIED', 'REJECTED', 'DISABLED');
create type verification_status as enum ('PENDING', 'APPROVED', 'REJECTED');
create type receipt_source as enum ('customer', 'admin_verified');
create type receipt_comparison_status as enum ('MATCH', 'MISMATCH', 'INCONCLUSIVE');
create type admin_actor_type as enum ('primary', 'backup');
create type exchange_rate_status as enum ('ACTIVE', 'PROPOSED', 'REJECTED');
create type payment_method_status as enum ('ENABLED', 'DISABLED');

create table users (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null unique,
  verified_name text,
  verified_shamcash_account text,
  payment_identity_verified_at timestamptz,
  is_disabled boolean not null default false,
  disabled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint users_verified_identity_pair check ((verified_name is null and verified_shamcash_account is null and payment_identity_verified_at is null) or (verified_name is not null and length(btrim(verified_name)) between 1 and 200 and verified_shamcash_account is not null and length(btrim(verified_shamcash_account)) between 1 and 100 and payment_identity_verified_at is not null))
);

create table network_configs (
  code network_code primary key,
  display_name text not null,
  enabled boolean not null default false,
  address_regex text not null,
  address_validator text not null,
  requires_memo boolean not null default false,
  explorer_url_template text,
  service_fee_percent numeric(9,6) not null,
  min_amount numeric(24,9) not null,
  max_amount numeric(24,9) not null,
  icon_or_emoji text not null,
  config_version bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint network_fee_nonnegative check (service_fee_percent >= 0 and service_fee_percent < 100),
  constraint network_amount_bounds check (min_amount > 0 and max_amount >= min_amount)
);
create unique index network_configs_enabled_code_idx on network_configs(code) where enabled;
insert into network_configs (code, display_name, enabled, address_regex, address_validator, requires_memo, service_fee_percent, min_amount, max_amount, icon_or_emoji) values
('BEP20','BEP20',true,'^0x[0-9A-Fa-f]{40}$','evm_address',false,10.000000,0.001,1000000,'🔶'),
('TRC20','TRC20',true,'^T[1-9A-HJ-NP-Za-km-z]{33}$','tron_base58check',false,5.000000,0.001,1000000,'🔴'),
('TON','TON',false,'.*','ton_address',true,0.000000,0.001,1000000,'💎'),
('ARB','ARB',false,'^0x[0-9A-Fa-f]{40}$','evm_address',false,0.000000,0.001,1000000,'🔷'),
('ETH','ETH',false,'^0x[0-9A-Fa-f]{40}$','evm_address',false,0.000000,0.001,1000000,'🔷'),
('SOL','SOL',false,'.*','sol_address',false,0.000000,0.001,1000000,'🟣');

create table wallets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete restrict,
  network_code network_code not null references network_configs(code) on delete restrict,
  address text not null,
  normalized_address text not null,
  status wallet_status not null default 'PENDING',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  verified_at timestamptz,
  disabled_at timestamptz,
  constraint wallets_address_nonempty check (length(btrim(address)) > 0),
  constraint wallets_normalized_nonempty check (length(btrim(normalized_address)) > 0)
);
create unique index wallets_user_network_address_uq on wallets(user_id, network_code, normalized_address);
create index wallets_user_status_idx on wallets(user_id, status);

create table wallet_verifications (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references wallets(id) on delete restrict,
  user_id uuid not null references users(id) on delete restrict,
  status verification_status not null default 'PENDING',
  input_source text not null,
  submitted_address text,
  extracted_address text,
  extracted_network network_code,
  rejection_reason text,
  reviewed_by_telegram_user_id bigint,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);
create index wallet_verifications_wallet_idx on wallet_verifications(wallet_id, created_at desc);

create table payment_methods (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  display_name text not null,
  status payment_method_status not null default 'DISABLED',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
insert into payment_methods (code, display_name, status) values ('SHAM_CASH','شام كاش','ENABLED');

create table admin_payment_accounts (
  id uuid primary key default gen_random_uuid(),
  payment_method_id uuid not null unique references payment_methods(id) on delete restrict,
  account_name text not null,
  account_number text not null,
  qr_image_storage_key text,
  qr_image_file_id text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint admin_payment_account_fields check (length(btrim(account_name)) > 0 and length(btrim(account_number)) > 0)
);

create table exchange_rates (
  id uuid primary key default gen_random_uuid(),
  currency_pair text not null default 'USD/NEW.SYP',
  rate numeric(24,9) not null,
  status exchange_rate_status not null,
  sanity_threshold_percent numeric(9,6) not null default 20.000000,
  proposed_from_rate numeric(24,9),
  proposed_at timestamptz,
  activated_at timestamptz,
  created_by_telegram_user_id bigint,
  created_at timestamptz not null default now(),
  constraint exchange_rate_positive check (rate > 0),
  constraint exchange_rate_threshold_valid check (sanity_threshold_percent >= 0 and sanity_threshold_percent <= 100)
);
create index exchange_rates_pair_status_idx on exchange_rates(currency_pair,status,created_at desc);

create table settings (
  id boolean primary key default true,
  active_exchange_rate_id uuid references exchange_rates(id) on delete restrict,
  rounding_policy_version text not null default 'ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001',
  absolute_tolerance numeric(24,9) not null default 0.04,
  admin_session_timeout_seconds integer not null default 900,
  max_file_size_bytes bigint not null default 5242880,
  public_order_code_prefix text not null default 'ORD',
  backup_admin_mode text not null default 'EMERGENCY_ONLY',
  updated_at timestamptz not null default now(),
  constraint settings_tolerance_nonnegative check (absolute_tolerance >= 0),
  constraint settings_file_limit_positive check (max_file_size_bytes > 0),
  constraint settings_timeout_positive check (admin_session_timeout_seconds > 0),
  constraint settings_backup_mode check (backup_admin_mode in ('EMERGENCY_ONLY'))
);
insert into settings default values;

create table orders (
  internal_order_id uuid primary key default gen_random_uuid(),
  public_order_code text not null unique,
  user_id uuid not null references users(id) on delete restrict,
  wallet_id uuid not null references wallets(id) on delete restrict,
  network_code network_code not null references network_configs(code) on delete restrict,
  payment_method_id uuid not null references payment_methods(id) on delete restrict,
  status order_status not null default 'DRAFT',
  version bigint not null default 1,
  receipt_source receipt_source,
  shamcash_operation_number text,
  manual_usdt_transfer_reference text,
  rejection_reason text,
  clarification_reason text,
  expires_at timestamptz,
  approved_at timestamptz,
  completed_at timestamptz,
  cancelled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orders_public_code_nonempty check (length(btrim(public_order_code)) between 4 and 64),
  constraint orders_operation_nonempty check (shamcash_operation_number is null or length(btrim(shamcash_operation_number)) between 1 and 200),
  constraint orders_version_positive check (version > 0)
);
create index orders_user_status_idx on orders(user_id,status,created_at desc);
create index orders_status_expiry_idx on orders(status,expires_at) where status='PENDING_PAYMENT';
create index orders_review_queue_idx on orders(status,created_at) where status in ('PAYMENT_SUBMITTED','UNDER_REVIEW','CLARIFICATION_REQUIRED');
create unique index orders_shamcash_operation_number_uq on orders(shamcash_operation_number) where shamcash_operation_number is not null;

create table order_financial_snapshots (
  internal_order_id uuid primary key references orders(internal_order_id) on delete restrict,
  requested_amount numeric(24,9) not null,
  fee_percent numeric(9,6) not null,
  fee_amount numeric(24,9) not null,
  net_usdt_amount numeric(24,9) not null,
  payment_currency currency_code not null,
  exchange_rate numeric(24,9),
  local_amount numeric(24,9) not null,
  rounding_policy_version text not null,
  network_config_version bigint not null,
  created_at timestamptz not null default now(),
  constraint financial_requested_positive check (requested_amount > 0),
  constraint financial_fee_valid check (fee_percent >= 0 and fee_percent < 100),
  constraint financial_amounts_valid check (fee_amount >= 0 and net_usdt_amount > 0),
  constraint financial_fee_formula check (fee_amount=round(requested_amount*fee_percent/100,9)),
  constraint financial_net_formula check (net_usdt_amount=round(requested_amount-fee_amount,9)),
  constraint financial_rate_required_for_syp check ((payment_currency='USD' and exchange_rate is null) or (payment_currency='NEW.SYP' and exchange_rate is not null and exchange_rate>0)),
  constraint financial_local_formula check ((payment_currency='USD' and local_amount=round(requested_amount,9)) or (payment_currency='NEW.SYP' and local_amount=round(requested_amount*exchange_rate,9)))
);

create table receipt_submissions (
  id uuid primary key default gen_random_uuid(),
  internal_order_id uuid not null references orders(internal_order_id) on delete restrict,
  source receipt_source not null,
  attempt_number integer not null,
  idempotency_key text not null unique,
  shamcash_operation_number text,
  linkage_status text not null default 'PENDING',
  processing_status text not null default 'PENDING',
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint receipt_attempt_positive check (attempt_number>0),
  constraint receipt_linkage_status_valid check (linkage_status in ('PENDING','LINKED','BLOCKED','ADMIN_ESCALATION')),
  constraint receipt_processing_status_valid check (processing_status in ('PENDING','PROCESSING','SUCCEEDED','FAILED','ESCALATED'))
);
create unique index receipt_submissions_order_attempt_uq on receipt_submissions(internal_order_id,attempt_number);
create index receipt_submissions_order_idx on receipt_submissions(internal_order_id,created_at desc);

create table receipt_evidence (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null unique references receipt_submissions(id) on delete restrict,
  storage_key text not null unique,
  mime_type text not null,
  byte_size bigint not null,
  sha256_hex text not null,
  width integer,
  height integer,
  original_filename text,
  created_at timestamptz not null default now(),
  retention_until timestamptz,
  deleted_at timestamptz,
  constraint receipt_evidence_mime check (mime_type in ('image/jpeg','image/png','image/webp')),
  constraint receipt_evidence_size check (byte_size>0 and byte_size<=5242880),
  constraint receipt_evidence_sha check (sha256_hex ~ '^[0-9a-fA-F]{64}$')
);

create table receipt_verification_results (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null unique references receipt_submissions(id) on delete restrict,
  operation_type text,
  operation_number text,
  operation_date timestamptz,
  sender_name text,
  sender_account text,
  recipient_name text,
  recipient_account text,
  amount numeric(24,9),
  currency currency_code,
  note text,
  fingerprint_text text,
  extraction_confidence numeric(6,5),
  comparison_status receipt_comparison_status not null,
  is_linked_to_order boolean not null default false,
  field_results jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  raw_extraction_text text,
  created_at timestamptz not null default now(),
  constraint receipt_confidence_valid check (extraction_confidence is null or extraction_confidence between 0 and 1)
);
create index receipt_verification_results_operation_idx on receipt_verification_results(operation_number);

create table admin_users (
  telegram_user_id bigint primary key,
  actor_type admin_actor_type not null,
  enabled boolean not null default false,
  emergency_only boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint admin_backup_mode_consistency check ((actor_type='backup' and emergency_only=true) or (actor_type='primary' and emergency_only=false))
);

create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_telegram_user_id bigint,
  actor_type admin_actor_type,
  action text not null,
  target_type text not null,
  target_id text,
  old_value jsonb,
  new_value jsonb,
  confirmation_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint audit_actor_type_pair check (actor_telegram_user_id is null or actor_type is not null)
);
create index audit_logs_target_idx on audit_logs(target_type,target_id,created_at desc);
create index audit_logs_actor_idx on audit_logs(actor_telegram_user_id,created_at desc);

create or replace function prevent_financial_snapshot_mutation() returns trigger language plpgsql as $$ begin raise exception 'order financial snapshots are immutable'; end; $$;
create trigger order_financial_snapshots_no_update before update or delete on order_financial_snapshots for each row execute function prevent_financial_snapshot_mutation();

create or replace function prevent_audit_mutation() returns trigger language plpgsql as $$ begin raise exception 'audit_logs is append-only'; end; $$;
create trigger audit_logs_no_update_delete before update or delete on audit_logs for each row execute function prevent_audit_mutation();

create or replace function validate_order_status_mutation() returns trigger language plpgsql as $$ begin if new.status is distinct from old.status then if new.version <> old.version + 1 then raise exception 'order status mutation requires version increment'; end if; end if; return new; end; $$;
create trigger orders_status_version_guard before update on orders for each row execute function validate_order_status_mutation();

create or replace function assert_launch_networks() returns void language plpgsql as $$ declare enabled_count integer; begin select count(*) into enabled_count from network_configs where enabled; if enabled_count <> 2 then raise exception 'launch requires exactly two enabled networks'; end if; if exists (select 1 from network_configs where enabled and code not in ('BEP20','TRC20')) then raise exception 'only BEP20 and TRC20 may be enabled at launch'; end if; end; $$;
select assert_launch_networks();
drop function assert_launch_networks();
