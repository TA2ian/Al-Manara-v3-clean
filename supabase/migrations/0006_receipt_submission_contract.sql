alter table receipt_submissions
    add column if not exists telegram_file_id text,
    add column if not exists mime_type text,
    add column if not exists submitted_at timestamptz,
    add column if not exists failure_reason text;

alter table receipt_submissions
    drop constraint if exists receipt_submissions_attempt_positive;

alter table receipt_submissions
    add constraint receipt_submissions_attempt_positive check (attempt_number between 1 and 3);

alter table receipt_submissions
    add constraint receipt_submissions_mime_type_check
    check (mime_type is null or mime_type in ('image/jpeg', 'image/png', 'image/webp'));

alter table receipt_submissions
    add constraint receipt_submissions_file_id_check
    check (telegram_file_id is null or length(btrim(telegram_file_id)) > 0);

create unique index if not exists receipt_submissions_processing_uq
    on receipt_submissions(internal_order_id)
    where processing_status = 'PROCESSING';

create or replace function reserve_receipt_submission(
    p_order_id uuid,
    p_idempotency_key text,
    p_telegram_file_id text,
    p_mime_type text,
    p_submitted_at timestamptz default now()
)
returns table (
    submission_id uuid,
    internal_order_id uuid,
    attempt_number integer,
    telegram_file_id text,
    mime_type text,
    submitted_at timestamptz,
    processing_status text,
    replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_existing receipt_submissions%rowtype;
    v_status order_status;
    v_attempt integer;
    v_submission_id uuid;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_telegram_file_id is null or length(btrim(p_telegram_file_id)) = 0 then raise exception 'receipt file id is required'; end if;
    if p_mime_type not in ('image/jpeg', 'image/png', 'image/webp') then raise exception 'unsupported receipt image type'; end if;
    if p_submitted_at is null then raise exception 'submission time is required'; end if;

    -- Serialize reservations for one order before calculating its next attempt.
    perform pg_advisory_xact_lock(hashtextextended(p_order_id::text, 0));

    select * into v_existing
      from receipt_submissions
     where idempotency_key = btrim(p_idempotency_key)
     for update;

    if found then
        if v_existing.internal_order_id <> p_order_id then
            raise exception 'idempotency key belongs to another order';
        end if;
        return query
        select v_existing.id, v_existing.internal_order_id, v_existing.attempt_number,
               v_existing.telegram_file_id, v_existing.mime_type, v_existing.submitted_at,
               v_existing.processing_status, true;
        return;
    end if;

    select o.status into v_status
      from orders o
     where o.internal_order_id = p_order_id
     for update;
    if not found then raise exception 'order not found'; end if;
    if v_status <> 'PENDING_PAYMENT' then raise exception 'order does not accept receipts in current state'; end if;

    if exists (
        select 1 from receipt_submissions rs
         where rs.internal_order_id = p_order_id
           and rs.processing_status = 'PROCESSING'
    ) then
        raise exception 'receipt is already being processed';
    end if;

    select coalesce(max(rs.attempt_number), 0) + 1
      into v_attempt
      from receipt_submissions rs
     where rs.internal_order_id = p_order_id;

    if v_attempt > 3 then raise exception 'receipt attempt limit reached'; end if;

    v_submission_id := gen_random_uuid();

    insert into receipt_submissions (
        id, internal_order_id, source, attempt_number, idempotency_key,
        telegram_file_id, mime_type, submitted_at, linkage_status, processing_status
    ) values (
        v_submission_id, p_order_id, 'customer', v_attempt,
        btrim(p_idempotency_key), btrim(p_telegram_file_id), p_mime_type,
        p_submitted_at, 'PENDING', 'PROCESSING'
    );

    return query
    select r.id, r.internal_order_id, r.attempt_number, r.telegram_file_id,
           r.mime_type, r.submitted_at, r.processing_status, false
      from receipt_submissions r
     where r.id = v_submission_id;
end;
$$;
