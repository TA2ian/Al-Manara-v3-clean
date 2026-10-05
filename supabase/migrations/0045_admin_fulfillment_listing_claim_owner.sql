-- Fulfillment listing needs claim ownership so Telegram can expose only the
-- action that the current administrator is actually allowed to perform.
-- Keep the existing list_admin_orders contract unchanged; this dedicated RPC
-- avoids changing a table-returning function's result shape in-place.
create or replace function list_admin_fulfillment_orders(
    p_admin_telegram_user_id bigint,
    p_actor_type admin_actor_type,
    p_page integer default 0,
    p_page_size integer default 5
)
returns table (
    internal_order_id uuid,
    public_order_code text,
    user_telegram_id bigint,
    wallet_id uuid,
    network_code network_code,
    status order_status,
    version bigint,
    requested_amount numeric,
    payment_currency currency_code,
    local_amount numeric,
    created_at timestamptz,
    total_count bigint,
    fulfillment_claimed_by bigint
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_offset integer;
begin
    if p_admin_telegram_user_id <= 0 then raise exception 'admin telegram user id must be positive'; end if;
    if p_actor_type is null then raise exception 'admin actor type is required'; end if;
    if p_page < 0 then raise exception 'page must be non-negative'; end if;
    if p_page_size < 1 or p_page_size > 50 then raise exception 'page size is invalid'; end if;

    if not exists (
        select 1 from admin_users au
         where au.telegram_user_id = p_admin_telegram_user_id
           and au.enabled
           and au.actor_type = p_actor_type
           and (au.actor_type = 'primary' or au.emergency_only)
    ) then
        raise exception 'admin is not enabled';
    end if;

    v_offset := p_page * p_page_size;

    return query
    with filtered as (
        select
            o.internal_order_id,
            o.public_order_code,
            u.telegram_user_id as user_telegram_id,
            o.wallet_id,
            o.network_code,
            o.status,
            o.version,
            fs.requested_amount,
            fs.payment_currency,
            fs.local_amount,
            o.created_at,
            count(*) over () as total_count,
            fc.admin_telegram_user_id as fulfillment_claimed_by
        from orders o
        join users u on u.id = o.user_id
        left join order_financial_snapshots fs on fs.internal_order_id = o.internal_order_id
        left join order_fulfillment_claims fc on fc.internal_order_id = o.internal_order_id
        where o.status = 'APPROVED'
        order by o.created_at desc, o.internal_order_id desc
        offset v_offset
        limit p_page_size
    )
    select * from filtered;
end;
$$;
