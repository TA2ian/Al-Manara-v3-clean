-- Migration: 0047_admin_super_tools.sql
-- Description: RPCs for super admin tools (order reset, order edit, order delete, user unsuspension, force identity verification)

-- 1. Reset Order Status
CREATE OR REPLACE FUNCTION admin_reset_order_status(
    p_admin_user_id BIGINT,
    p_internal_order_id UUID,
    p_target_status TEXT DEFAULT 'UNDER_REVIEW',
    p_reason TEXT DEFAULT 'Reopened by admin'
)
RETURNS TABLE (
    internal_order_id UUID,
    status TEXT,
    version INT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_version INT;
BEGIN
    SELECT version INTO v_current_version
    FROM purchase_orders
    WHERE id = p_internal_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found';
    END IF;

    UPDATE purchase_orders
    SET 
        status = p_target_status::order_status_type,
        version = v_current_version + 1,
        updated_at = NOW()
    WHERE id = p_internal_order_id;

    RETURN QUERY
    SELECT id, status::TEXT, version
    FROM purchase_orders
    WHERE id = p_internal_order_id;
END;
$$;


-- 2. Edit Order Details
CREATE OR REPLACE FUNCTION admin_edit_order_details(
    p_admin_user_id BIGINT,
    p_internal_order_id UUID,
    p_new_amount NUMERIC DEFAULT NULL,
    p_new_currency TEXT DEFAULT NULL,
    p_new_network TEXT DEFAULT NULL
)
RETURNS TABLE (
    internal_order_id UUID,
    requested_amount NUMERIC,
    payment_currency TEXT,
    network_code TEXT,
    version INT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_version INT;
BEGIN
    SELECT version INTO v_current_version
    FROM purchase_orders
    WHERE id = p_internal_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found';
    END IF;

    UPDATE purchase_orders
    SET
        requested_amount = COALESCE(p_new_amount, requested_amount),
        payment_currency = COALESCE(p_new_currency, payment_currency),
        network_code = COALESCE(p_new_network, network_code),
        version = v_current_version + 1,
        updated_at = NOW()
    WHERE id = p_internal_order_id;

    RETURN QUERY
    SELECT id, requested_amount, payment_currency, network_code, version
    FROM purchase_orders
    WHERE id = p_internal_order_id;
END;
$$;


-- 3. Delete Order
CREATE OR REPLACE FUNCTION admin_delete_order(
    p_admin_user_id BIGINT,
    p_internal_order_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM receipt_attempts WHERE order_id = p_internal_order_id;
    DELETE FROM purchase_orders WHERE id = p_internal_order_id;
    RETURN TRUE;
END;
$$;


-- 4. Unsuspend User
CREATE OR REPLACE FUNCTION admin_unsuspend_user(
    p_admin_user_id BIGINT,
    p_target_telegram_user_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE users
    SET 
        misconduct_strikes = 0,
        suspended_until = NULL,
        updated_at = NOW()
    WHERE telegram_user_id = p_target_telegram_user_id;

    RETURN FOUND;
END;
$$;


-- 5. Force Verify User Identity
CREATE OR REPLACE FUNCTION admin_force_verify_user(
    p_admin_user_id BIGINT,
    p_target_telegram_user_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE users
    SET 
        is_verified = TRUE,
        identity_status = 'VERIFIED',
        updated_at = NOW()
    WHERE telegram_user_id = p_target_telegram_user_id;

    RETURN FOUND;
END;
$$;
