-- Receipt submission authorization: the Telegram identity must own the target order.
-- Keep this check inside the security-invoker RPC so every application caller gets the same boundary.

drop function if exists reserve_receipt_submission(uuid, text, text, text, timestamptz);
drop function if exists reserve_receipt_submission(uuid, bigint, text, text, text, timestamptz);

create function reserve_receipt_submission(
    p_order_id uuid,
    p_telegram_user_id bigint,
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
    v_user_id uuid;
    v_user_disabled boolean;
begin
    if p_order_id is null then raise exception 'order id is required'; end if;
    if p_telegram_user_id is null or p_telegram_user_id <= 0 then raise exception 'telegram user id is required'; end if;
    if p_idempotency_key is null or length(btrim(p_idempotency_key)) = 0 then raise exception 'idempotency key is required'; end if;
    if p_telegram_file_id is null or length(btrim(p_telegram_file_id)) = 0 then raise exception 'receipt file id is required'; end if;
    if p_mime_type not in ('image/jpeg', 'image/png', 'image/webp') then raise exception 'unsupported receipt image type'; end if;
    if p_submitted_at is null then raise exception 'submission time is required'; end if;

    -- Resolve and authorize the order before idempotency replay, so a replay key cannot bypass ownership.
    select o.user_id, o.status, u.is_disabled
      into v_user_id, v_status, v_user_disabled
      from orders o
      join users u on u.id = o.user_id
     where o.internal_order_id = p_order_id
     for update of o;

    if not found then raise exception 'order not found'; end if;
    if v_user_id is null then raise exception 'order owner not found'; end if;
    if v_user_disabled then raise exception 'user is disabled'; end if;
    if not exists (
        select 1 from users u
         where u.id = v_user_id
           and u.telegram_user_id = p_telegram_user_id
    ) then
        raise exception 'order does not belong to telegram user';
    end if;
    if v_status <> 'PENDING_PAYMENT' then raise exception 'order does not accept receipts in current state'; end if;

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
