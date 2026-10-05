drop function if exists finalize_receipt_submission(uuid, text, text, text);

create function finalize_receipt_submission(
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

    update receipt_submissions as rs
       set processing_status = p_processing_status,
           linkage_status = coalesce(p_linkage_status, rs.linkage_status),
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
