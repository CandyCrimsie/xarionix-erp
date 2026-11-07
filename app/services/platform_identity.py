"""Fresh Core liveness + explicit ERP bindings; never grants ERP rights from Core roles."""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

import httpx
from core.config import config
from core.platform_oidc import InvalidToken, OIDCVerifier
from fastapi import HTTPException
from models.company import Company
from models.company_memberships import CompanyMembership
from models.platform_bindings import PlatformCompanyBinding, PlatformUserBinding
from models.users import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    core_user_id: UUID
    core_company_id: UUID
    company_id: int


class PlatformProvider:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.verifier = OIDCVerifier(
            SimpleNamespace(
                oidc_issuer=config.PLATFORM_OIDC_ISSUER,
                environment="development"
                if config.PLATFORM_DEVELOPMENT
                else "production",
                oidc_backchannel=None,
                oidc_algorithms=["RS256"],
                oidc_audience=config.PLATFORM_OIDC_AUDIENCE,
                oidc_leeway_seconds=0,
                oidc_cache_seconds=60,
                oidc_refresh_cooldown=10,
            ),
            client,
        )

    async def core(self, path: str, token: str) -> dict:
        try:
            async with self.client.stream(
                "GET",
                config.PLATFORM_CORE_API + path,
                headers={"Authorization": "Bearer " + token},
            ) as response:
                if response.status_code in {401, 403, 404}:
                    raise HTTPException(403, "platform_access_denied")
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes(8192):
                    body.extend(chunk)
                    if len(body) > 262144:
                        raise ValueError()
            result = json.loads(body)
            if not isinstance(result, dict):
                raise TypeError()
            return result
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(503, "platform_provider_unavailable") from None

    async def authenticate(self, token: str, core_company: UUID, session: AsyncSession):
        try:
            claims = await self.verifier.verify(token)
            if claims.get("azp") != config.PLATFORM_OIDC_CLIENT_ID or claims.get(
                "xarionix_principal"
            ) not in (None, "human"):
                raise InvalidToken()
        except InvalidToken:
            raise HTTPException(
                401,
                "Invalid platform access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        profile = await self.core("/me", token)
        try:
            core_user = UUID(profile["user_id"])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(403, "platform_identity_denied") from None
        if (
            profile.get("principal_type") != "human"
            or profile.get("status") != "active"
            or profile.get("issuer") != claims["iss"]
            or profile.get("subject") != claims["sub"]
        ):
            raise HTTPException(403, "platform_identity_denied")
        permission = await self.core(f"/companies/{core_company}/me/permissions", token)
        if permission.get("company_id") != str(core_company) or not isinstance(
            permission.get("permissions"), list
        ):
            raise HTTPException(403, "platform_company_denied")
        ub = await session.get(
            PlatformUserBinding, (config.PLATFORM_CORE_API, core_user)
        )
        cb = await session.get(
            PlatformCompanyBinding, (config.PLATFORM_CORE_API, core_company)
        )
        if (
            not ub
            or not ub.is_active
            or ub.issuer != claims["iss"]
            or ub.subject != claims["sub"]
        ):
            raise HTTPException(403, "core_identity_unlinked")
        if not cb or not cb.is_active:
            raise HTTPException(403, "core_company_unlinked")
        user = await session.get(User, ub.user_id)
        company = await session.get(Company, cb.company_id)
        member = await session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.company_id == cb.company_id,
                CompanyMembership.user_id == ub.user_id,
            )
        )
        if (
            not user
            or not user.is_active
            or not company
            or not company.is_active
            or not member
            or not member.is_active
        ):
            raise HTTPException(403, "platform_erp_access_denied")
        return user, PlatformIdentity(core_user, core_company, company.id)
