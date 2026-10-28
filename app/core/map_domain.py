"""Shared map invariants; no authorization decisions based on icon or distance."""
from sqlalchemy import or_, text


class MapOperationError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 409, **details):
        self.status = status
        self.detail = {"code": code, "message": message, **details}
        super().__init__(message)


def visible_to(model, company_id: int, user_id: int):
    return (
        model.company_id == company_id,
        or_(model.visibility == "company", model.owner_user_id == user_id),
    )


async def lock_map_company(session, company_id: int):
    # All graph writes in a company use this lock before building/marker row
    # locks. Building coordinate edits only lock buildings: no reverse order.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 25172))"), {"key": f"map-company:{company_id}"})


def check_version(entity, expected: int | None):
    if expected is not None and entity.version != expected:
        raise MapOperationError("stale_version", "Объект уже изменён. Откройте его заново.")


def require_write(entity, user_id: int, can_manage: bool):
    if entity.visibility == "private":
        if entity.owner_user_id != user_id:
            raise MapOperationError("not_found", "Объект не найден", status=404)
    elif not can_manage:
        raise MapOperationError("permission_denied", "Недостаточно прав для изменения общего объекта", status=403)
