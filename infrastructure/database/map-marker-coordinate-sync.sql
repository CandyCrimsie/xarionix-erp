-- Additive development schema update. Run once before the updated API starts.
-- Existing annotations intentionally remain independent; no point is moved.
BEGIN;
ALTER TABLE map_markers
    ADD COLUMN IF NOT EXISTS sync_building_coordinates boolean NOT NULL DEFAULT false;
COMMIT;
