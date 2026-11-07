"""Trusted local operator tool; never an HTTP self-link endpoint."""

import argparse
import asyncio
import getpass
from uuid import UUID

from core.config import config
from database.session import session_factory
from models.company import Company
from models.platform_bindings import (
    PlatformBindingAudit,
    PlatformCompanyBinding,
    PlatformUserBinding,
)
from models.users import User
from sqlalchemy.exc import SQLAlchemyError


async def apply(args):
    if not config.PLATFORM_OIDC_ENABLED:
        raise ValueError("Enable and validate PLATFORM_OIDC configuration first")
    async with session_factory() as session, session.begin():
        row: PlatformUserBinding | PlatformCompanyBinding | None
        if args.kind == "user":
            row = await session.get(
                PlatformUserBinding,
                (config.PLATFORM_CORE_API, args.core_id),
                with_for_update=True,
            )
        else:
            row = await session.get(
                PlatformCompanyBinding,
                (config.PLATFORM_CORE_API, args.core_id),
                with_for_update=True,
            )
        if args.revoke:
            if not row:
                raise ValueError("Binding not found")
            row.is_active = False
            erp_id = (
                row.user_id if isinstance(row, PlatformUserBinding) else row.company_id
            )
        else:
            if row:
                raise ValueError(
                    "Binding already exists; identity replacement is not permitted"
                )
            if not args.erp_id or args.erp_id <= 0:
                raise ValueError("An existing positive ERP ID is required")
            record: User | Company | None
            if args.kind == "user":
                record = await session.get(User, args.erp_id)
            else:
                record = await session.get(Company, args.erp_id)
            if not record or not record.is_active:
                raise ValueError("Existing active ERP record required")
            if args.kind == "user":
                if not args.subject or len(args.subject) > 255:
                    raise ValueError("Explicit verified Keycloak subject required")
                if (
                    isinstance(record, User)
                    and record.is_system_admin
                    and not args.allow_system_admin
                ):
                    raise ValueError(
                        "System administrator binding requires --allow-system-admin"
                    )
                row = PlatformUserBinding(
                    core_api=config.PLATFORM_CORE_API,
                    core_user_id=args.core_id,
                    issuer=config.PLATFORM_OIDC_ISSUER,
                    subject=args.subject,
                    user_id=args.erp_id,
                )
            else:
                row = PlatformCompanyBinding(
                    core_api=config.PLATFORM_CORE_API,
                    core_company_id=args.core_id,
                    company_id=args.erp_id,
                )
            session.add(row)
            erp_id = args.erp_id
        session.add(
            PlatformBindingAudit(
                operator=getpass.getuser()[:255],
                action=("revoke_" if args.revoke else "bind_") + args.kind,
                core_api=config.PLATFORM_CORE_API,
                core_id=args.core_id,
                erp_id=erp_id,
            )
        )
    print(
        "Привязка отозвана."
        if args.revoke
        else "Привязка создана. Данные и права не изменены."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Явное связывание существующих Core/ERP записей"
    )
    parser.add_argument("kind", choices=["user", "company"])
    parser.add_argument("--core-id", type=UUID, required=True)
    parser.add_argument("--erp-id", type=int)
    parser.add_argument("--subject")
    parser.add_argument("--allow-system-admin", action="store_true")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(apply(args))
    except (SQLAlchemyError, ValueError, OSError):
        # Never echo SQL connection strings or DB driver exception parameters.
        parser.exit(
            1, "Привязка не сохранена. Проверьте IDs, уникальность и доступ к БД.\n"
        )


if __name__ == "__main__":
    main()
