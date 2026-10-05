-- Emergency admin transfer RPC.
-- Transfers primary admin privileges to a new Telegram user ID.
-- This RPC runs as SECURITY DEFINER (superuser context) so it can be
-- invoked from the bot without requiring the caller to be an admin.

CREATE OR REPLACE FUNCTION emergency_transfer_admin(
    p_new_admin_telegram_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_old_admin_id UUID;
    v_new_user_id UUID;
BEGIN
    -- Validate input
    IF p_new_admin_telegram_id IS NULL OR p_new_admin_telegram_id <= 0 THEN
        RETURN FALSE;
    END IF;

    -- Find the current primary admin
    SELECT id INTO v_old_admin_id
    FROM admin_sessions
    WHERE actor_type = 'primary'
      AND is_active = TRUE
    LIMIT 1;

    IF v_old_admin_id IS NULL THEN
        -- No active admin found; try admin_actors table
        UPDATE admin_actors
        SET telegram_user_id = p_new_admin_telegram_id,
            updated_at = NOW()
        WHERE actor_type = 'primary';

        IF NOT FOUND THEN
            -- Insert new primary admin
            INSERT INTO admin_actors (telegram_user_id, actor_type, is_active, created_at, updated_at)
            VALUES (p_new_admin_telegram_id, 'primary', TRUE, NOW(), NOW());
        END IF;

        RETURN TRUE;
    END IF;

    -- Deactivate old admin session
    UPDATE admin_sessions
    SET is_active = FALSE,
        ended_at = NOW()
    WHERE actor_type = 'primary'
      AND is_active = TRUE;

    -- Transfer the admin actor record to the new telegram ID
    UPDATE admin_actors
    SET telegram_user_id = p_new_admin_telegram_id,
        updated_at = NOW()
    WHERE actor_type = 'primary';

    IF NOT FOUND THEN
        INSERT INTO admin_actors (telegram_user_id, actor_type, is_active, created_at, updated_at)
        VALUES (p_new_admin_telegram_id, 'primary', TRUE, NOW(), NOW());
    END IF;

    -- Log the transfer in audit_log
    INSERT INTO audit_log (action, actor_type, actor_id, details, created_at)
    VALUES (
        'emergency_admin_transfer',
        'system',
        NULL,
        jsonb_build_object(
            'old_admin_id', v_old_admin_id,
            'new_admin_telegram_id', p_new_admin_telegram_id,
            'reason', 'emergency_transfer'
        ),
        NOW()
    );

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RETURN FALSE;
END;
$$;

-- Restrict execution to service_role only (the bot's backend connection)
REVOKE ALL ON FUNCTION emergency_transfer_admin(BIGINT) FROM PUBLIC;
REVOKE ALL ON FUNCTION emergency_transfer_admin(BIGINT) FROM anon;
REVOKE ALL ON FUNCTION emergency_transfer_admin(BIGINT) FROM authenticated;
GRANT EXECUTE ON FUNCTION emergency_transfer_admin(BIGINT) TO service_role;
