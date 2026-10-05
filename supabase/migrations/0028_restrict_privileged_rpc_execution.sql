-- Backend persistence RPCs are callable by the bot backend only.
-- Database authorization remains authoritative inside each function; this layer
-- prevents anonymous/authenticated PostgREST callers from invoking backend APIs.
--
-- Supabase migration execution may prepare statements containing multiple SQL
-- commands. Keep the ACL changes inside one executable PL/pgSQL block so each
-- REVOKE/GRANT is executed dynamically as an individual statement.
DO $$
BEGIN
  -- Order reads/support and creation.
  EXECUTE 'REVOKE EXECUTE ON FUNCTION get_order_for_transition(uuid) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION get_order_for_transition(uuid) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION get_customer_payment_identity(bigint) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION get_customer_payment_identity(bigint) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION get_admin_payment_account(currency_code) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION get_admin_payment_account(currency_code) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION get_network_config(network_code) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION get_network_config(network_code) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION create_purchase_order_atomic(uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION create_purchase_order_atomic(uuid, text, bigint, uuid, text, text, numeric, numeric, numeric, numeric, text, numeric, numeric, text, text, text, text, text, text, timestamptz, timestamptz, text, text) TO service_role';

  -- Wallet persistence.
  EXECUTE 'REVOKE EXECUTE ON FUNCTION get_wallet_for_telegram_user(uuid, bigint) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION get_wallet_for_telegram_user(uuid, bigint) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION find_verified_wallet_by_address(text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION find_verified_wallet_by_address(text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION list_verified_wallets_for_telegram_user(bigint) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION list_verified_wallets_for_telegram_user(bigint) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION register_pending_wallet_for_telegram_user(bigint, text, network_code, text, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION register_pending_wallet_for_telegram_user(bigint, text, network_code, text, text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION disable_wallet_for_telegram_user(uuid, bigint) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION disable_wallet_for_telegram_user(uuid, bigint) TO service_role';

  -- Receipt persistence.
  EXECUTE 'REVOKE EXECUTE ON FUNCTION reserve_receipt_submission(uuid, bigint, text, text, text, timestamptz) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION reserve_receipt_submission(uuid, bigint, text, text, text, timestamptz) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION finalize_receipt_submission(uuid, text, text, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION finalize_receipt_submission(uuid, text, text, text) TO service_role';

  -- Privileged administrative RPCs.
  EXECUTE 'REVOKE EXECUTE ON FUNCTION authorize_admin_order_review(bigint, admin_actor_type) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION authorize_admin_order_review(bigint, admin_actor_type) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION transition_order_if_version(uuid, order_status, bigint, bigint, admin_actor_type, jsonb) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION transition_order_if_version(uuid, order_status, bigint, bigint, admin_actor_type, jsonb) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION transition_order_idempotent(uuid, order_status, bigint, bigint, admin_actor_type, jsonb, text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION claim_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION complete_order_fulfillment(uuid, bigint, bigint, admin_actor_type, text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION close_order_without_fulfillment(uuid, bigint, bigint, uuid, text, text) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION close_order_without_fulfillment(uuid, bigint, bigint, uuid, text, text) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION list_admin_orders(bigint, admin_actor_type, text, integer, integer) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION list_admin_orders(bigint, admin_actor_type, text, integer, integer) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION create_admin_session(bigint, admin_actor_type) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION create_admin_session(bigint, admin_actor_type) TO service_role';

  EXECUTE 'REVOKE EXECUTE ON FUNCTION revoke_admin_session(bigint, admin_actor_type, uuid) FROM public, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION revoke_admin_session(bigint, admin_actor_type, uuid) TO service_role';
END
$$;
