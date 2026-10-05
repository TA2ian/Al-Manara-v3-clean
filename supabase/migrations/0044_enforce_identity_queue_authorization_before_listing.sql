-- A WHERE predicate is not an authorization boundary: PostgreSQL may skip it
-- when the pending queue is empty. Authorize before reading any queue state.

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
language plpgsql
security invoker
set search_path = public
as $$
begin
    perform assert_primary_identity_reviewer(p_admin_telegram_user_id, p_actor_type);

    return query
    select cis.id, u.telegram_user_id, cis.full_name, cis.shamcash_account,
           cis.qr_image_file_id, cis.submitted_at
      from customer_identity_submissions cis
      join users u on u.id = cis.user_id
     where cis.status = 'PENDING'
     order by cis.submitted_at asc;
end;
$$;