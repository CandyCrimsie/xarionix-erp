from pydantic import ValidationError
from sqlalchemy import select

from core.map_domain import MapOperationError, lock_map_company
from models.map_workspace import MapPreference
from schemas.map_workspace import MapSettings, PreferenceResponse
from services.map_layers import list_layers


async def normalized_settings(session, company_id, raw):
    notice = None
    try:
        settings = MapSettings.model_validate(raw)
    except ValidationError:
        # Unknown/corrupt settings are not permission to reveal the whole map.
        settings = MapSettings(show_buildings=False, show_infrastructure=False, show_personal=False,
            include_unassigned=False, connection_mode="hidden")
        notice = "Формат сохранённых фильтров устарел. Используйте «Сбросить фильтры» для явного восстановления."
    available = {layer.id for layer in await list_layers(session, company_id=company_id) if layer.mode != "group"}
    current = [id_ for id_ in dict.fromkeys(settings.visible_layer_ids) if id_ in available]
    if current != settings.visible_layer_ids:
        notice = notice or "Удалённые слои исключены из настроек. Остальные фильтры сохранены."
    settings.visible_layer_ids = current
    return settings, notice


async def get_preferences(session, *, company_id, user_id):
    record = await session.get(MapPreference, (company_id, user_id))
    settings, notice = await normalized_settings(session, company_id, record.settings if record else {})
    return PreferenceResponse(version=record.version if record else 0, settings=settings, notice=notice)


async def save_preferences(session, *, company_id, user_id, data):
    try:
        await lock_map_company(session, company_id)
        record = await session.scalar(select(MapPreference).where(MapPreference.company_id == company_id,
            MapPreference.user_id == user_id).with_for_update().execution_options(populate_existing=True))
        if (record.version if record else 0) != data.expected_version:
            raise MapOperationError("stale_preferences", "Настройки изменены в другой вкладке. Перечитайте их перед сохранением.")
        settings, notice = await normalized_settings(session, company_id, data.settings.model_dump())
        if record is None:
            record = MapPreference(company_id=company_id, user_id=user_id, settings=settings.model_dump(), version=1)
            session.add(record)
        else:
            record.settings = settings.model_dump()
            record.version += 1
        await session.flush()
        result = PreferenceResponse(version=record.version, settings=settings, notice=notice)
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
