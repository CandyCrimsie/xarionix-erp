"""Repeatable EXPLAIN on isolated PostgreSQL, not the user's development data."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql

from models.map_markers import MapMarker
from models.map_connections import MapConnection
from repositories.map_markers import marker_position_columns, marker_records_query
from core.map_domain import visible_to
from services.map_connections import connection_list_query
from test_map_api import marker_building_context


@pytest.mark.asyncio
async def test_map_query_plans_on_one_thousand_points(db_session, api_client):
    company, _, _, building = await marker_building_context(db_session, api_client)
    markers = [MapMarker(company_id=company, name=f"Шкаф {i}", point_type="cabinet", visibility="company",
        building_link_role="none", latitude=55.5 + (i % 100) * .001, longitude=38 + (i // 100) * .01) for i in range(1000)]
    db_session.add_all(markers)
    await db_session.flush()
    db_session.add_all([MapConnection(company_id=company, name=f"Трасса {i}", visibility="company",
        source_marker_id=markers[i].id, target_marker_id=markers[i + 500].id,
        medium="fiber", status="active", fiber_count=24,
        vertices=[[38.03, 55.54], [38.04, 55.55]]) for i in range(500)])
    await db_session.flush()
    await db_session.execute(text("ANALYZE map_markers, map_connections"))
    lat, lng = marker_position_columns()
    query = marker_records_query().where(*visible_to(MapMarker, company, 1), lng >= 38.025, lng <= 38.045, lat >= 55.53, lat <= 55.57).order_by(MapMarker.id).limit(5001)
    queries = {
        "markers-viewport": query,
        "connections-viewport": connection_list_query(company_id=company, user_id=1, bounds={"west":38.025,"east":38.045,"south":55.53,"north":55.57}),
        "connections-endpoint": connection_list_query(company_id=company, user_id=1, endpoint_kind="marker", endpoint_id=markers[0].id),
    }
    for label, statement in queries.items():
        sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        rows = await db_session.scalars(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql))
        plan = "\n".join(rows)
        print(f"\n--- {label}: 1000 points / 500 routes ---\n{plan}")
        assert "Execution Time:" in plan and "Buffers:" in plan
    assert len((await db_session.scalars(select(MapMarker.id).where(MapMarker.company_id == company))).all()) == 1000
