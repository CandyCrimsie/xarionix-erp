"""Additive, transactional route upgrade. No destructive reset or Alembic.

From app/: python -m database.map_routes_upgrade --dry-run|--apply
"""
import argparse
import asyncio
import json

from sqlalchemy import text

from core.map_markers import POINT_TYPE_CHECK
from core.map_routes import INSTALLATION_CHECK


async def inspect_route_schema(connection):
    exists = await connection.scalar(text("SELECT to_regclass('map_connections') IS NOT NULL"))
    if not exists:
        return {"upgrade_required": False, "fresh_database": True}
    column = await connection.scalar(text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='map_connections' AND column_name='installation_methods')"))
    constraint = await connection.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='map_markers'::regclass AND conname='ck_map_markers_point_type'"))
    table = await connection.scalar(text("SELECT to_regclass('map_route_objects') IS NOT NULL"))
    constraints = await connection.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='map_connections'::regclass AND conname IN ('ck_map_connections_installation','uq_map_connections_company_id')"))
    return {"upgrade_required": not (column and table and constraints == 2 and constraint and all(value in constraint for value in ("fiber_box", "odf", "transition"))),
        "installation_column": column, "route_objects_table": table,
        "connections": await connection.scalar(text("SELECT count(*) FROM map_connections"))}


async def upgrade_route_schema(connection):
    await connection.execute(text("SELECT pg_advisory_xact_lock(2517203)"))
    report = await inspect_route_schema(connection)
    if not report["upgrade_required"]:
        return report
    # Fail atomically if busy: retry after the long-running writer, not an
    # indefinite startup lock or a partially applied schema.
    await connection.execute(text("SET LOCAL lock_timeout='5s'"))
    await connection.execute(text("ALTER TABLE map_markers DROP CONSTRAINT IF EXISTS ck_map_markers_point_type"))
    await connection.execute(text(f"ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_point_type CHECK ({POINT_TYPE_CHECK}) NOT VALID"))
    await connection.execute(text("ALTER TABLE map_markers VALIDATE CONSTRAINT ck_map_markers_point_type"))
    await connection.execute(text("ALTER TABLE map_connections ADD COLUMN IF NOT EXISTS installation_methods jsonb NOT NULL DEFAULT '[]'::jsonb"))
    # [] is the explicit legacy encoding of all-unknown, including writes by an
    # older client. Reads expand it to one unknown per segment.
    await connection.execute(text(f"ALTER TABLE map_connections DROP CONSTRAINT IF EXISTS ck_map_connections_installation"))
    await connection.execute(text(f"ALTER TABLE map_connections ADD CONSTRAINT ck_map_connections_installation CHECK ({INSTALLATION_CHECK}) NOT VALID"))
    await connection.execute(text("ALTER TABLE map_connections VALIDATE CONSTRAINT ck_map_connections_installation"))
    unique = await connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='map_connections'::regclass AND conname='uq_map_connections_company_id')"))
    if not unique:
        await connection.execute(text("ALTER TABLE map_connections ADD CONSTRAINT uq_map_connections_company_id UNIQUE(company_id,id)"))
    from models.map_route_objects import MapRouteObject
    await connection.run_sync(lambda sync: MapRouteObject.__table__.create(sync, checkfirst=True))
    return report


async def run(apply):
    import models  # noqa: F401
    from database.engine import engine
    async with engine.begin() as connection:
        report = await (upgrade_route_schema(connection) if apply else inspect_route_schema(connection))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
