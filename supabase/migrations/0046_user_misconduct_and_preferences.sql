-- Add columns for Misconduct and Language Preferences
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS misconduct_strikes integer not null default 0,
ADD COLUMN IF NOT EXISTS suspended_until timestamptz,
ADD COLUMN IF NOT EXISTS language_code text not null default 'ar';

-- RPC to record user misconduct and apply tiered penalties
CREATE OR REPLACE FUNCTION record_user_misconduct(target_telegram_user_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    current_strikes integer;
    new_strikes integer;
BEGIN
    -- Lock user row for update
    SELECT misconduct_strikes INTO current_strikes FROM users WHERE telegram_user_id = target_telegram_user_id FOR UPDATE;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'user_not_found';
    END IF;

    new_strikes := current_strikes + 1;

    IF new_strikes = 1 THEN
        -- 1st Strike: 4 hours suspension
        UPDATE users 
        SET misconduct_strikes = new_strikes, 
            suspended_until = now() + interval '4 hours',
            updated_at = now()
        WHERE telegram_user_id = target_telegram_user_id;
    ELSIF new_strikes = 2 THEN
        -- 2nd Strike: 24 hours suspension
        UPDATE users 
        SET misconduct_strikes = new_strikes, 
            suspended_until = now() + interval '24 hours',
            updated_at = now()
        WHERE telegram_user_id = target_telegram_user_id;
    ELSE
        -- 3rd Strike or more: Permanent Ban
        UPDATE users 
        SET misconduct_strikes = new_strikes, 
            is_disabled = true, 
            disabled_at = now(),
            updated_at = now()
        WHERE telegram_user_id = target_telegram_user_id;
    END IF;
END;
$$;

-- Revoke execute from public/anon for safety (aligned with v3 security)
REVOKE EXECUTE ON FUNCTION record_user_misconduct(bigint) FROM public;
REVOKE EXECUTE ON FUNCTION record_user_misconduct(bigint) FROM anon;
REVOKE EXECUTE ON FUNCTION record_user_misconduct(bigint) FROM authenticated;
