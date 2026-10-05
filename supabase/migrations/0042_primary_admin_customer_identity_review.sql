-- Identity verification reveals sensitive payment identity and is reviewed only
-- by the configured primary administrator. Keep this check in the database so
-- Telegram callback data can never elevate a backup administrator.

create or replace function assert_primary_identity_reviewer(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns void
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_actor_type <> 'primary' then
        raise exception 'only the primary administrator may review customer identity';
    end if;
    perform assert_enabled_admin(p_admin_telegram_user_id, p_actor_type);
end;
$$;

create or replace function list_pending_customer_identity_submissions(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type
)
returns table (
    submission_id uuid,
    customer_telegram_user_id bigint,
    full_name text,
    shamcash_account text,
    qr_image_file_id text,
    submitted_at timestamptz
)
language sql
security invoker
set search_path = public
as $$
    select cis.id, u.telegram_user_id, cis.full_name, cis.shamcash_account,
           cis.qr_image_file_id, cis.submitted_at
      from customer_identity_submissions cis
      join users u on u.id = cis.user_id
     where cis.status = 'PENDING'
       and assert_primary_identity_reviewer(p_admin_telegram_user_id, p_actor_type) is null
     order by cis.submitted_at asc;
$$;

create or replace function approve_customer_identity_submission(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_submission_id uuid
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_submission customer_identity_submissions%rowtype;
begin
    perform assert_primary_identity_reviewer(p_admin_telegram_user_id, p_actor_type);
    select * into v_submission from customer_identity_submissions
     where id = p_submission_id and status = 'PENDING' for update;
    if not found then raise exception 'identity submission is not pending'; end if;
    update users set verified_name = v_submission.full_name,
        verified_shamcash_account = v_submission.shamcash_account,
        payment_identity_verified_at = now(), updated_at = now()
     where id = v_submission.user_id;
    update customer_identity_submissions set status = 'APPROVED', reviewed_at = now(),
        reviewed_by_telegram_user_id = p_admin_telegram_user_id where id = p_submission_id;
    insert into audit_logs (actor_telegram_user_id, actor_type, action, target_type, target_id, old_value, new_value)
    values (p_admin_telegram_user_id, p_actor_type, 'customer_identity.approved',
        'customer_identity_submission', p_submission_id::text,
        jsonb_build_object('status', 'PENDING'), jsonb_build_object('status', 'APPROVED'));
    return true;
end;
$$;

create or replace function reject_customer_identity_submission(
    p_admin_telegram_user_id bigint, p_actor_type admin_actor_type,
    p_submission_id uuid, p_rejection_reason text
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
begin
    perform assert_primary_identity_reviewer(p_admin_telegram_user_id, p_actor_type);
    if length(btrim(coalesce(p_rejection_reason, ''))) not between 1 and 500 then
        raise exception 'rejection reason is required';
    end if;
    update customer_identity_submissions set status = 'REJECTED',
        rejection_reason = btrim(p_rejection_reason), reviewed_at = now(),
        reviewed_by_telegram_user_id = p_admin_telegram_user_id
     where id = p_submission_id and status = 'PENDING';
    if not found then raise exception 'identity submission is not pending'; end if;
    insert into audit_logs (actor_telegram_user_id, actor_type, action, target_type, target_id, old_value, new_value)
    values (p_admin_telegram_user_id, p_actor_type, 'customer_identity.rejected',
        'customer_identity_submission', p_submission_id::text,
        jsonb_build_object('status', 'PENDING'), jsonb_build_object('status', 'REJECTED'));
    return true;
end;
$$;

revoke execute on function assert_primary_identity_reviewer(bigint, admin_actor_type) from public, anon, authenticated;
grant execute on function assert_primary_identity_reviewer(bigint, admin_actor_type) to service_role;