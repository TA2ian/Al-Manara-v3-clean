-- Allow customer/system audit actors without misclassifying them as admin actors.
-- Admin audit rows still require a concrete actor id whenever actor_type is set.

alter table audit_logs
  drop constraint if exists audit_actor_type_pair;

alter table audit_logs
  add constraint audit_actor_type_pair
  check (actor_type is null or actor_telegram_user_id is not null);
