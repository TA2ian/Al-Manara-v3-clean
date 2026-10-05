-- Customer-safe order history. Authorization is enforced inside the RPC because
-- Telegram identity is the only caller input used to select orders.
create or replace function list_customer_orders(
    p_telegram_user_id bigint,
    p_page integer default 0,
    p_page_size integer default 5
)
returns table (
    public_order_code text,
    status order_status,
    version bigint,
    network_code network_code,
    requested_amount numeric,
    payment_currency currency_code,
    local_amount numeric,
    created_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_offset integer;
begin
    if p_telegram_user_id <= 0 then
        raise exception 'customer telegram user id must be positive';
    end if;
    if p_page < 0 then
        raise exception 'page must be non-negative';
    end if;
    if p_page_size < 1 or p_page_size > 50 then
        raise exception 'page size must be between 1 and 50';
    end if;

    v_offset := p_page * p_page_size;

    return query
    with customer_orders as (
        select
            o.public_order_code,
            o.status,
            o.version,
            o.network_code,
            fs.requested_amount,
            fs.payment_currency,
            fs.local_amount,
            o.created_at
        from orders o
        join users u on u.id = o.user_id
        left join order_financial_snapshots fs
            on fs.internal_order_id = o.internal_order_id
        where u.telegram_user_id = p_telegram_user_id
          and not u.is_disabled
        order by o.created_at desc, o.internal_order_id desc
        offset v_offset
        limit p_page_size
    )
    select * from customer_orders;
end;
$$;

create or replace function count_customer_orders(
    p_telegram_user_id bigint
)
returns table (total_count bigint)
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_telegram_user_id <= 0 then
        raise exception 'customer telegram user id must be positive';
    end if;

    return query
    select count(*)
    from orders o
    join users u on u.id = o.user_id
    where u.telegram_user_id = p_telegram_user_id
      and not u.is_disabled;
end;
$$;

revoke execute on function list_customer_orders(bigint, integer, integer)
from public, anon, authenticated;
grant execute on function list_customer_orders(bigint, integer, integer)
to service_role;
revoke execute on function count_customer_orders(bigint)
from public, anon, authenticated;
grant execute on function count_customer_orders(bigint)
to service_role;