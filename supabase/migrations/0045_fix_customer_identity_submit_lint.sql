-- Qualify the status column inside the pending-submission existence check.
-- Without the table alias PostgreSQL can resolve status against the PL/pgSQL
-- return-column variable, making the function ambiguous under Supabase lint.

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

    select u.id into v_user_id
      from users u
     where u.telegram_user_id = p_telegram_user_id
       and not u.is_disabled
     for share;
    if not found then
        raise exception 'customer is unavailable';
    end if;

    if exists (
        select 1
          from customer_identity_submissions cis
         where cis.user_id = v_user_id
           and cis.status = 'PENDING'
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

revoke execute on function submit_customer_identity(bigint, text, text, text, text) from public, anon, authenticated;
grant execute on function submit_customer_identity(bigint, text, text, text, text) to service_role;
