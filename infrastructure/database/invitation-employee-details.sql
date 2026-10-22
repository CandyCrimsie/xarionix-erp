-- Additive development update, before starting the updated API.
-- Existing invitations and memberships retain NULL employee details.
BEGIN;
ALTER TABLE company_invitations
    ADD COLUMN IF NOT EXISTS full_name varchar(255),
    ADD COLUMN IF NOT EXISTS email varchar(254),
    ADD COLUMN IF NOT EXISTS phone_number varchar(16),
    ADD COLUMN IF NOT EXISTS date_of_birth date;
ALTER TABLE company_memberships
    ADD COLUMN IF NOT EXISTS full_name varchar(255),
    ADD COLUMN IF NOT EXISTS email varchar(254),
    ADD COLUMN IF NOT EXISTS phone_number varchar(16),
    ADD COLUMN IF NOT EXISTS date_of_birth date;
COMMIT;
