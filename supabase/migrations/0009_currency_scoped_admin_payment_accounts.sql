-- Admin payment accounts are currency-scoped.
-- ShamCash can legitimately have separate receiving accounts for USD and NEW.SYP.
-- The payment method itself remains canonical (SHAM_CASH); the receiving account
-- must be selected by payment currency and snapshotted into the order.

drop index if exists admin_payment_accounts_payment_method_id_key;

create unique index if not exists admin_payment_accounts_method_currency_uq
    on admin_payment_accounts(payment_method_id, currency);
