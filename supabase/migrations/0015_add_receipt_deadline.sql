alter table settings add column receipt_submission_deadline_minutes integer not null default 60 check (receipt_submission_deadline_minutes between 1 and 90);
