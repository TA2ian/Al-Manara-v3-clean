-- Quote support RPCs expose only the current policy snapshots needed by the
-- application layer. They are backend-only and intentionally do not expose
-- mutable tables directly to PostgREST callers.

create or replace function get_current_fee_policy(
    p_network_code network_code,
    p_now timestamptz
)
returns table (
    percent numeric,
    version text,
    effective_at timestamptz
)
language plpgsql
security invoker
set search_path = public
as $$
begin
    if p_network_code is null or p_now is null then
        raise exception 'network code and evaluation time are required';
    end if;

    return query
    select
        nc.service_fee_percent,
        'network_config:' || nc.config_version::text,
        nc.updated_at
    from network_configs nc
    where nc.code = p_network_code
      and nc.enabled;
end;
$$;

create or replace function get_current_exchange_rate(
    p_currency text,
    p_now timestamptz
)
returns table (
    currency text,
    rate numeric,
    captured_at timestamptz,
    source text,
    version text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_rate_id uuid;
    v_rate numeric;
    v_created_at timestamptz;
    v_activated_at timestamptz;
    v_status exchange_rate_status;
begin
    if p_currency is null or p_now is null then
        raise exception 'currency and evaluation time are required';
    end if;
    if p_currency <> 'NEW.SYP' then
        return;
    end if;

    select s.active_exchange_rate_id
      into v_rate_id
      from settings s
     where s.id = true;

    if v_rate_id is null then
        return;
    end if;

    select er.rate, er.created_at, er.activated_at, er.status
      into v_rate, v_created_at, v_activated_at, v_status
      from exchange_rates er
     where er.id = v_rate_id
       and er.currency_pair = 'USD/NEW.SYP';

    if not found or v_status <> 'ACTIVE' then
        return;
    end if;

    if coalesce(v_activated_at, v_created_at) > p_now then
        return;
    end if;

    return query
    select
        p_currency,
        v_rate,
        coalesce(v_activated_at, v_created_at),
        'settings.active_exchange_rate_id',
        'exchange_rate:' || v_rate_id::text;
end;
$$;

DO $$
BEGIN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION get_current_fee_policy(network_code, timestamptz) FROM public, anon, authenticated';
    EXECUTE 'GRANT EXECUTE ON FUNCTION get_current_fee_policy(network_code, timestamptz) TO service_role';

    EXECUTE 'REVOKE EXECUTE ON FUNCTION get_current_exchange_rate(text, timestamptz) FROM public, anon, authenticated';
    EXECUTE 'GRANT EXECUTE ON FUNCTION get_current_exchange_rate(text, timestamptz) TO service_role';
END
$$;
