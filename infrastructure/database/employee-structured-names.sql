-- Additive update: preserve historical full_name verbatim, without parsing it.
BEGIN;
ALTER TABLE company_invitations
    ADD COLUMN IF NOT EXISTS first_name varchar(100),
    ADD COLUMN IF NOT EXISTS last_name varchar(100),
    ADD COLUMN IF NOT EXISTS middle_name varchar(100);
ALTER TABLE company_memberships
    ADD COLUMN IF NOT EXISTS first_name varchar(100),
    ADD COLUMN IF NOT EXISTS last_name varchar(100),
    ADD COLUMN IF NOT EXISTS middle_name varchar(100);
COMMIT;
