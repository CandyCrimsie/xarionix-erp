"""Stage 25.17.2 additive upgrade. Run from app/: python -m database.map_upgrade --dry-run|--apply."""
import argparse
import asyncio
import json

from sqlalchemy import text


async def inspect_legacy_markers(connection):
    if not await connection.scalar(text("SELECT to_regclass('map_markers') IS NOT NULL")):
        return {"markers": 0, "conflicts": [], "upgrade_required": False}
    upgraded = await connection.scalar(text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='map_markers' AND column_name='building_link_role')"))
    if upgraded:
        return {"markers": await connection.scalar(text("SELECT count(*) FROM map_markers")), "conflicts": [], "upgrade_required": False}
    conflicts = (await connection.execute(text("""
        SELECT company_id, building_id, array_agg(id ORDER BY id) AS marker_ids
        FROM map_markers WHERE sync_building_coordinates AND building_id IS NOT NULL
        GROUP BY company_id, building_id HAVING count(*) > 1 ORDER BY company_id, building_id
    """))).mappings().all()
    unpositioned = (await connection.execute(text("""
        SELECT m.id AS marker_id, m.company_id, m.building_id
        FROM map_markers m LEFT JOIN buildings b ON b.id=m.building_id
        WHERE m.sync_building_coordinates AND m.building_id IS NOT NULL
          AND (b.id IS NULL OR b.latitude IS NULL OR b.longitude IS NULL)
        ORDER BY m.id
    """))).mappings().all()
    return {"markers": await connection.scalar(text("SELECT count(*) FROM map_markers")), "conflicts": [dict(row) for row in conflicts],
        "unpositioned_buildings": [dict(row) for row in unpositioned], "upgrade_required": True}


async def upgrade_map_schema(connection):
    await connection.execute(text("SELECT pg_advisory_xact_lock(2517202)"))
    report = await inspect_legacy_markers(connection)
    if not report["upgrade_required"]:
        return report
    # A persistent backup preserves every old position/style and records all
    # ambiguous synchronized groups. No last-ID-wins conversion is performed.
    statements = [
        "CREATE TABLE IF NOT EXISTS map_marker_legacy_backup AS TABLE map_markers",
        "ALTER TABLE map_markers ADD COLUMN visibility varchar(16) NOT NULL DEFAULT 'company'",
        "ALTER TABLE map_markers ADD COLUMN owner_user_id bigint REFERENCES users(id) ON DELETE RESTRICT",
        "ALTER TABLE map_markers ADD COLUMN point_type varchar(24) NOT NULL DEFAULT 'note'",
        "ALTER TABLE map_markers ADD COLUMN building_link_role varchar(16) NOT NULL DEFAULT 'none'",
        "ALTER TABLE map_markers ADD COLUMN version integer NOT NULL DEFAULT 1",
        "ALTER TABLE map_markers ALTER COLUMN latitude DROP NOT NULL, ALTER COLUMN longitude DROP NOT NULL",
        "UPDATE map_markers SET building_link_role = 'reference' WHERE building_id IS NOT NULL",
        """UPDATE map_markers m SET building_link_role='represents', point_type='building', latitude=NULL, longitude=NULL
           WHERE sync_building_coordinates AND building_id IS NOT NULL AND
             EXISTS (SELECT 1 FROM buildings h WHERE h.id=m.building_id AND h.latitude IS NOT NULL AND h.longitude IS NOT NULL) AND
             (SELECT count(*) FROM map_marker_legacy_backup b WHERE b.company_id=m.company_id AND b.building_id=m.building_id AND b.sync_building_coordinates)=1""",
        "UPDATE map_markers SET sync_building_coordinates=false",
        "ALTER TABLE map_markers ADD CONSTRAINT uq_map_markers_company_id UNIQUE(company_id, id)",
        "CREATE UNIQUE INDEX uq_map_markers_represents ON map_markers(company_id, building_id) WHERE building_link_role='represents'",
        "CREATE INDEX ix_map_markers_visibility_owner ON map_markers(company_id, visibility, owner_user_id, id)",
        "ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_visibility CHECK (visibility IN ('company','private') AND ((visibility='company' AND owner_user_id IS NULL) OR (visibility='private' AND owner_user_id IS NOT NULL)))",
        "ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_building_link CHECK (building_link_role IN ('none','reference','located_at','represents') AND ((building_link_role='none' AND building_id IS NULL) OR (building_link_role<>'none' AND building_id IS NOT NULL)))",
        "ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_represents CHECK (building_link_role<>'represents' OR (visibility='company' AND point_type='building' AND latitude IS NULL AND longitude IS NULL))",
        "ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_coordinate_pair CHECK ((latitude IS NULL)=(longitude IS NULL))",
        "ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_point_type CHECK (point_type IN ('building','network_node','cabinet','splice','pole','chamber','equipment','note'))",
    ]
    for statement in statements:
        await connection.execute(text(statement))
    return report


async def run(apply):
    import models  # noqa: F401
    from database.base import Base
    from database.engine import engine
    async with engine.begin() as connection:
        report = await (upgrade_map_schema(connection) if apply else inspect_legacy_markers(connection))
        if apply:
            from database.map_routes_upgrade import upgrade_route_schema
            await upgrade_route_schema(connection)
            await connection.run_sync(Base.metadata.create_all)
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--dry-run", action="store_true")
    options.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
