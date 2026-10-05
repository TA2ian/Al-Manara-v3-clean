-- A successfully verified receipt must advance the order into the human-review queue.
-- Keep this atomic with receipt finalization so a successful receipt cannot leave the
-- order stranded in PENDING_PAYMENT.

create or replace function finalize_receipt_submission(
    p_submission_id uuid,
    p_processing_status text,
    p_linkage_status text default null,
    p_failure_reason text default null
)
returns table (
    submission_id uuid,
    internal_order_id uuid,
    attempt_number integer,
    telegram_file_id text,
    mime_type text,
    submitted_at timestamptz,
    processing_status text,
    linkage_status text,
    failure_reason text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_order_id uuid;
    v_attempt_number integer;
    v_current_status text;
    v_linkage_status text;
    v_order_version bigint;
    v_public_order_code text;
begin
    if p_processing_status not in ('SUCCEEDED', 'FAILED', 'ESCALATED') then
        raise exception 'invalid receipt processing status';
    end if;

    if p_linkage_status is not null
       and p_linkage_status not in ('PENDING', 'LINKED', 'BLOCKED', 'ADMIN_ESCALATION') then
        raise exception 'invalid receipt linkage status';
    end if;

    if p_processing_status in ('FAILED', 'ESCALATED')
       and length(btrim(coalesce(p_failure_reason, ''))) = 0 then
        raise exception 'failure reason is required';
    end if;

    select r.internal_order_id, r.attempt_number, r.processing_status, r.linkage_status
      into v_order_id, v_attempt_number, v_current_status, v_linkage_status
      from receipt_submissions r
     where r.id = p_submission_id
     for update;

    if not found then raise exception 'receipt submission not found'; end if;
    if v_current_status <> 'PROCESSING' then
        raise exception 'receipt submission is not processing';
    end if;

    if p_processing_status = 'ESCALATED' and v_attempt_number <> 3 then
        raise exception 'only the third receipt attempt may escalate';
    end if;

    if p_processing_status = 'SUCCEEDED' then
        select o.status::text, o.version, o.public_order_code
          into v_current_status, v_order_version, v_public_order_code
          from orders o
         where o.internal_order_id = v_order_id
         for update;

        if not found then raise exception 'receipt order not found'; end if;
        if v_current_status <> 'PENDING_PAYMENT' then
            raise exception 'verified receipt requires order in PENDING_PAYMENT';
        end if;

        update orders as o
           set status = 'PAYMENT_SUBMITTED',
               version = o.version + 1,
               updated_at = now()
         where o.internal_order_id = v_order_id
           and o.version = v_order_version;

        if not found then raise exception 'order changed while submitting receipt'; end if;

        insert into audit_logs (
            actor_telegram_user_id, actor_type, action, target_type, target_id,
            old_value, new_value, metadata
        ) values (
            null, null, 'order.status_changed', 'order', v_order_id::text,
            jsonb_build_object('status', 'PENDING_PAYMENT', 'version', v_order_version),
            jsonb_build_object('status', 'PAYMENT_SUBMITTED', 'version', v_order_version + 1),
            jsonb_build_object('source', 'receipt_verification', 'submission_id', p_submission_id, 'public_order_code', v_public_order_code)
        );

        update orders as o
           set status = 'UNDER_REVIEW',
               version = o.version + 1,
               updated_at = now()
         where o.internal_order_id = v_order_id
           and o.version = v_order_version + 1;

        if not found then raise exception 'order changed while entering review queue'; end if;

        insert into audit_logs (
            actor_telegram_user_id, actor_type, action, target_type, target_id,
            old_value, new_value, metadata
        ) values (
            null, null, 'order.status_changed', 'order', v_order_id::text,
            jsonb_build_object('status', 'PAYMENT_SUBMITTED', 'version', v_order_version + 1),
            jsonb_build_object('status', 'UNDER_REVIEW', 'version', v_order_version + 2),
            jsonb_build_object('source', 'receipt_verification', 'submission_id', p_submission_id, 'public_order_code', v_public_order_code)
        );
    end if;

    update receipt_submissions as rs
       set processing_status = p_processing_status,
           linkage_status = case
               when p_processing_status = 'SUCCEEDED' then 'LINKED'
               else coalesce(p_linkage_status, rs.linkage_status)
           end,
           failure_reason = case
               when p_processing_status in ('FAILED', 'ESCALATED') then btrim(p_failure_reason)
               else null
           end,
           completed_at = now()
     where rs.id = p_submission_id;

    return query
    select r.id, r.internal_order_id, r.attempt_number,
           r.telegram_file_id, r.mime_type, r.submitted_at,
           r.processing_status, r.linkage_status, r.failure_reason
      from receipt_submissions r
     where r.id = p_submission_id;
end;
$$;
