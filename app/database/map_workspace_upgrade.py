"""Additive workspace metadata migration; never rewrites old network rows.

From app/: python -m database.map_workspace_upgrade --dry-run | --apply
"""
import argparse
import asyncio
import json

from sqlalchemy import text

TABLES = ("map_layers", "map_layer_members", "map_preferences", "map_passports")


async def inspect_workspace_schema(connection):
    present = [table for table in TABLES if await connection.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table})]
    return {"upgrade_required": len(present) != len(TABLES), "present": present, "missing": [table for table in TABLES if table not in present]}


async def upgrade_workspace_schema(connection):
    # Bound waiting for the migration lock too, not just subsequent DDL locks.
    await connection.execute(text("SET LOCAL lock_timeout='5s'"))
    await connection.execute(text("SELECT pg_advisory_xact_lock(2517301)"))
    report = await inspect_workspace_schema(connection)
    if report["upgrade_required"]:
        from models.map_workspace import MapLayer, MapLayerMember, MapPreference, MapPassport
        for model in (MapLayer, MapLayerMember, MapPreference, MapPassport):
            await connection.run_sync(lambda sync, table=model.__table__: table.create(sync, checkfirst=True))
    return report


async def run(apply):
    import models  # noqa: F401
    from database.engine import engine
    async with engine.begin() as connection:
        report = await (upgrade_workspace_schema(connection) if apply else inspect_workspace_schema(connection))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
