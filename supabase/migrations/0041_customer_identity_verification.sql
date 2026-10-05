-- Customer payment identity is collected separately from the approved
-- projection on users. Only an enabled administrator can approve it.

create table customer_identity_submissions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete restrict,
    full_name text not null,
    shamcash_account text not null,
    telegram_contact_phone text not null,
    qr_image_file_id text not null,
    status text not null default 'PENDING',
    rejection_reason text,
    submitted_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by_telegram_user_id bigint references admin_users(telegram_user_id) on delete restrict,
    constraint customer_identity_submission_name_valid
        check (length(btrim(full_name)) between 1 and 200),
    constraint customer_identity_submission_account_valid
        check (length(btrim(shamcash_account)) between 1 and 100),
    constraint customer_identity_submission_phone_valid
        check (length(btrim(telegram_contact_phone)) between 6 and 32),
    constraint customer_identity_submission_qr_valid
        check (length(btrim(qr_image_file_id)) between 1 and 512),
    constraint customer_identity_submission_status_valid
        check (status in ('PENDING', 'APPROVED', 'REJECTED')),
    constraint customer_identity_submission_review_valid
        check (
            (status = 'PENDING' and reviewed_at is null and reviewed_by_telegram_user_id is null and rejection_reason is null)
            or (status = 'APPROVED' and reviewed_at is not null and reviewed_by_telegram_user_id is not null and rejection_reason is null)
            or (status = 'REJECTED' and reviewed_at is not null and reviewed_by_telegram_user_id is not null and length(btrim(rejection_reason)) between 1 and 500)
        )
);

create unique index customer_identity_submissions_one_pending_per_user_uq
    on customer_identity_submissions(user_id)
    where status = 'PENDING';

create index customer_identity_submissions_pending_queue_idx
    on customer_identity_submissions(status, submitted_at)
    where status = 'PENDING';

create or replace function submit_customer_identity(
    p_telegram_user_id bigint,
    p_full_name text,
    p_shamcash_account text,
    p_telegram_contact_phone text,
    p_qr_image_file_id text
)
returns table (submission_id uuid, status text)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_user_id uuid;
    v_submission_id uuid;
begin
    if p_telegram_user_id is null or p_telegram_user_id <= 0 then
        raise exception 'telegram user id must be positive';
    end if;
    if length(btrim(coalesce(p_full_name, ''))) not between 1 and 200 then
        raise exception 'full name is invalid';
    end if;
    if length(btrim(coalesce(p_shamcash_account, ''))) not between 1 and 100 then
        raise exception 'Sham Cash account is invalid';
    end if;
    if length(btrim(coalesce(p_telegram_contact_phone, ''))) not between 6 and 32 then
        raise exception 'Telegram contact phone is invalid';
    end if;
    if length(btrim(coalesce(p_qr_image_file_id, ''))) not between 1 and 512 then
        raise exception 'QR image is required';
    end if;

    insert into users (telegram_user_id)
    values (p_telegram_user_id)
    on conflict (telegram_user_id) do nothing;

    select id into v_user_id
      from users
     where telegram_user_id = p_telegram_user_id
       and not is_disabled
     for share;
    if not found then
        raise exception 'customer is unavailable';
    end if;

    if exists (
        select 1 from customer_identity_submissions
         where user_id = v_user_id and status = 'PENDING'
    ) then
        raise exception 'a customer identity submission is already pending';
    end if;

    insert into customer_identity_submissions (
        user_id, full_name, shamcash_account, telegram_contact_phone, qr_image_file_id
    ) values (
        v_user_id, btrim(p_full_name), btrim(p_shamcash_account),
        btrim(p_telegram_contact_phone), btrim(p_qr_image_file_id)
    )
    returning id into v_submission_id;

    insert into audit_logs (action, target_type, target_id, new_value, metadata)
    values (
        'customer_identity.submitted', 'customer_identity_submission', v_submission_id::text,
        jsonb_build_object('status', 'PENDING'),
        jsonb_build_object('customer_telegram_user_id', p_telegram_user_id)
    );

    return query select v_submission_id, 'PENDING'::text;
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
       and assert_enabled_admin(p_admin_telegram_user_id, p_actor_type) is null
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
    perform assert_enabled_admin(p_admin_telegram_user_id, p_actor_type);
    select * into v_submission
      from customer_identity_submissions
     where id = p_submission_id and status = 'PENDING'
     for update;
    if not found then
        raise exception 'identity submission is not pending';
    end if;

    update users
       set verified_name = v_submission.full_name,
           verified_shamcash_account = v_submission.shamcash_account,
           payment_identity_verified_at = now(),
           updated_at = now()
     where id = v_submission.user_id;

    update customer_identity_submissions
       set status = 'APPROVED',
           reviewed_at = now(),
           reviewed_by_telegram_user_id = p_admin_telegram_user_id
     where id = p_submission_id;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id, old_value, new_value
    ) values (
        p_admin_telegram_user_id, p_actor_type, 'customer_identity.approved',
        'customer_identity_submission', p_submission_id::text,
        jsonb_build_object('status', 'PENDING'), jsonb_build_object('status', 'APPROVED')
    );
    return true;
end;
$$;

create or replace function reject_customer_identity_submission(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_submission_id uuid,
    p_rejection_reason text
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
begin
    perform assert_enabled_admin(p_admin_telegram_user_id, p_actor_type);
    if length(btrim(coalesce(p_rejection_reason, ''))) not between 1 and 500 then
        raise exception 'rejection reason is required';
    end if;

    update customer_identity_submissions
       set status = 'REJECTED',
           rejection_reason = btrim(p_rejection_reason),
           reviewed_at = now(),
           reviewed_by_telegram_user_id = p_admin_telegram_user_id
     where id = p_submission_id
       and status = 'PENDING';
    if not found then
        raise exception 'identity submission is not pending';
    end if;

    insert into audit_logs (
        actor_telegram_user_id, actor_type, action, target_type, target_id, old_value, new_value
    ) values (
        p_admin_telegram_user_id, p_actor_type, 'customer_identity.rejected',
        'customer_identity_submission', p_submission_id::text,
        jsonb_build_object('status', 'PENDING'), jsonb_build_object('status', 'REJECTED')
    );
    return true;
end;
$$;

revoke all on table customer_identity_submissions from public, anon, authenticated;
revoke execute on function submit_customer_identity(bigint, text, text, text, text) from public, anon, authenticated;
revoke execute on function list_pending_customer_identity_submissions(bigint, admin_actor_type) from public, anon, authenticated;
revoke execute on function approve_customer_identity_submission(bigint, admin_actor_type, uuid) from public, anon, authenticated;
revoke execute on function reject_customer_identity_submission(bigint, admin_actor_type, uuid, text) from public, anon, authenticated;
grant execute on function submit_customer_identity(bigint, text, text, text, text) to service_role;
grant execute on function list_pending_customer_identity_submissions(bigint, admin_actor_type) to service_role;
grant execute on function approve_customer_identity_submission(bigint, admin_actor_type, uuid) to service_role;
grant execute on function reject_customer_identity_submission(bigint, admin_actor_type, uuid, text) to service_role;