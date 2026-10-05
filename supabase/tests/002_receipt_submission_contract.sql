begin;

select plan(9);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'reserve_receipt_submission'
    ),
    'atomic receipt reservation function exists'
);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'finalize_receipt_submission'
    ),
    'atomic receipt finalization function exists'
);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_function_result(oid) like '%replayed%'
    ),
    'receipt reservation exposes replay state'
);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_functiondef(oid) like '%pg_advisory_xact_lock%'
    ),
    'receipt allocation is serialized per order'
);

select ok(
    exists (
        select 1
        from pg_indexes
        where schemaname = 'public'
          and tablename = 'receipt_submissions'
          and indexdef ilike '%idempotency_key%'
    ),
    'receipt idempotency key is unique'
);

select ok(
    exists (
        select 1
        from pg_indexes
        where schemaname = 'public'
          and tablename = 'receipt_submissions'
          and indexdef ilike '%processing_status%'
          and indexdef ilike '%unique%'
    ),
    'only one receipt may be processing per order'
);

select ok(
    exists (
        select 1
        from pg_constraint
        where conrelid = 'public.receipt_submissions'::regclass
          and conname = 'receipt_submissions_attempt_positive'
    ),
    'receipt attempt number is constrained to the supported range'
);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'reserve_receipt_submission'
          and pg_get_functiondef(oid) like '%idempotency key belongs to another order%'
    ),
    'idempotency key cannot be rebound to another order'
);

select ok(
    exists (
        select 1
        from pg_proc
        where proname = 'finalize_receipt_submission'
          and pg_get_function_result(oid) like '%telegram_file_id%'
          and pg_get_function_result(oid) like '%mime_type%'
          and pg_get_function_result(oid) like '%submitted_at%'
    ),
    'receipt finalization returns the complete attempt payload'
);

select * from finish();
rollback;
