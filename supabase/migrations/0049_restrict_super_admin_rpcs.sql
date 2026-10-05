-- Migration: 0049_restrict_super_admin_rpcs.sql
-- Description: Security fix — restrict super admin RPCs to service_role only.
-- These RPCs were missing the REVOKE/GRANT statements that all other RPCs
-- received in migration 0028. Without this fix, any authenticated Supabase
-- user could call these RPCs directly via the PostgREST API.

-- Also adds SQL-level admin validation and audit logging for delete operations.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. REVOKE public access from all super admin RPCs
-- ═══════════════════════════════════════════════════════════════════════════════

REVOKE ALL ON FUNCTION admin_reset_order_status(BIGINT, UUID, TEXT, TEXT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_reset_order_status(BIGINT, UUID, TEXT, TEXT) TO service_role;

REVOKE ALL ON FUNCTION admin_edit_order_details(BIGINT, UUID, NUMERIC, TEXT, TEXT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_edit_order_details(BIGINT, UUID, NUMERIC, TEXT, TEXT) TO service_role;

REVOKE ALL ON FUNCTION admin_delete_order(BIGINT, UUID) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_delete_order(BIGINT, UUID) TO service_role;

REVOKE ALL ON FUNCTION admin_unsuspend_user(BIGINT, BIGINT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_unsuspend_user(BIGINT, BIGINT) TO service_role;

REVOKE ALL ON FUNCTION admin_force_verify_user(BIGINT, BIGINT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_force_verify_user(BIGINT, BIGINT) TO service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. Replace admin_delete_order with version that includes audit logging
--    and admin validation (defense-in-depth)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION admin_delete_order(
    p_admin_user_id BIGINT,
    p_internal_order_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_order_code TEXT;
    v_order_status TEXT;
    v_order_user_id BIGINT;
BEGIN
    -- Validate admin exists
    IF NOT EXISTS (
        SELECT 1 FROM admin_users
        WHERE telegram_user_id = p_admin_user_id AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'unauthorized: admin not found or inactive';
    END IF;

    -- Capture order details before deletion for audit
    SELECT public_order_code, status::TEXT, user_telegram_id
    INTO v_order_code, v_order_status, v_order_user_id
    FROM purchase_orders
    WHERE id = p_internal_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found';
    END IF;

    -- Write audit log BEFORE deletion
    INSERT INTO audit_logs (
        actor_telegram_user_id,
        action,
        target_type,
        target_id,
        metadata
    ) VALUES (
        p_admin_user_id,
        'admin_delete_order',
        'purchase_order',
        p_internal_order_id::TEXT,
        jsonb_build_object(
            'deleted_order_code', v_order_code,
            'deleted_order_status', v_order_status,
            'deleted_order_user_id', v_order_user_id
        )
    );

    -- Perform deletion
    DELETE FROM receipt_attempts WHERE order_id = p_internal_order_id;
    DELETE FROM purchase_orders WHERE id = p_internal_order_id;
    RETURN TRUE;
END;
$$;

-- Re-apply restriction after replacement
REVOKE ALL ON FUNCTION admin_delete_order(BIGINT, UUID) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_delete_order(BIGINT, UUID) TO service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. Replace admin_edit_order_details with input validation
-- ═══════════════════════════════════════════════════════════════════════════════

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
    -- Validate admin exists
    IF NOT EXISTS (
        SELECT 1 FROM admin_users
        WHERE telegram_user_id = p_admin_user_id AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'unauthorized: admin not found or inactive';
    END IF;

    -- Validate amount if provided
    IF p_new_amount IS NOT NULL THEN
        IF p_new_amount <= 0 THEN
            RAISE EXCEPTION 'amount must be positive';
        END IF;
        IF p_new_amount > 100000 THEN
            RAISE EXCEPTION 'amount exceeds maximum limit';
        END IF;
    END IF;

    -- Validate currency if provided
    IF p_new_currency IS NOT NULL THEN
        IF p_new_currency NOT IN ('USD', 'NEW.SYP') THEN
            RAISE EXCEPTION 'invalid currency code: %', p_new_currency;
        END IF;
    END IF;

    -- Validate network if provided
    IF p_new_network IS NOT NULL THEN
        IF p_new_network NOT IN ('BEP20', 'TRC20', 'TON', 'ARB', 'ETH', 'SOL') THEN
            RAISE EXCEPTION 'invalid network code: %', p_new_network;
        END IF;
    END IF;

    SELECT po.version INTO v_current_version
    FROM purchase_orders po
    WHERE po.id = p_internal_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found';
    END IF;

    UPDATE purchase_orders po
    SET
        requested_amount = COALESCE(p_new_amount, po.requested_amount),
        payment_currency = COALESCE(p_new_currency, po.payment_currency),
        network_code = COALESCE(p_new_network, po.network_code),
        version = v_current_version + 1,
        updated_at = NOW()
    WHERE po.id = p_internal_order_id;

    RETURN QUERY
    SELECT po.id, po.requested_amount, po.payment_currency, po.network_code, po.version
    FROM purchase_orders po
    WHERE po.id = p_internal_order_id;
END;
$$;

-- Re-apply restriction after replacement
REVOKE ALL ON FUNCTION admin_edit_order_details(BIGINT, UUID, NUMERIC, TEXT, TEXT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_edit_order_details(BIGINT, UUID, NUMERIC, TEXT, TEXT) TO service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. Add admin validation to admin_reset_order_status
-- ═══════════════════════════════════════════════════════════════════════════════

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
    -- Validate admin exists
    IF NOT EXISTS (
        SELECT 1 FROM admin_users
        WHERE telegram_user_id = p_admin_user_id AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'unauthorized: admin not found or inactive';
    END IF;

    SELECT po.version INTO v_current_version
    FROM purchase_orders po
    WHERE po.id = p_internal_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'order not found';
    END IF;

    UPDATE purchase_orders po
    SET 
        status = p_target_status::order_status_type,
        version = v_current_version + 1,
        updated_at = NOW()
    WHERE po.id = p_internal_order_id;

    RETURN QUERY
    SELECT po.id, po.status::TEXT, po.version
    FROM purchase_orders po
    WHERE po.id = p_internal_order_id;
END;
$$;

-- Re-apply restriction after replacement
REVOKE ALL ON FUNCTION admin_reset_order_status(BIGINT, UUID, TEXT, TEXT) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION admin_reset_order_status(BIGINT, UUID, TEXT, TEXT) TO service_role;
