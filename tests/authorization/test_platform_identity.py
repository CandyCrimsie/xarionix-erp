"""SSO boundary regressions use real signatures and the real ERP authorization/API."""

import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from core.config import config
from cryptography.hazmat.primitives.asymmetric import rsa
from main import app
from models.platform_bindings import PlatformCompanyBinding, PlatformUserBinding
from models.users import User
from services.platform_identity import PlatformProvider
from sqlalchemy import func, select
from test_map_api import initialize_context, marker_payload


@pytest_asyncio.fixture
async def platform(monkeypatch, db_session, api_client, clean_test_redis):
    company, legacy, _ = await initialize_context(db_session, api_client)
    user = await db_session.scalar(select(User).where(User.username == "admin"))
    issuer = "https://identity.example.test/realms/xarionix"
    core = "https://core.example.test/api/v1"
    for name, value in {
        "PLATFORM_OIDC_ENABLED": True,
        "PLATFORM_CORE_API": core,
        "PLATFORM_OIDC_ISSUER": issuer,
        "PLATFORM_OIDC_CLIENT_ID": "xarionix-web",
    }.items():
        monkeypatch.setattr(config, name, value)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    uid, cid, sub = uuid4(), uuid4(), str(uuid4())
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {
        "kid": "first",
        "alg": "RS256",
        "use": "sig",
    }
    state = {"denied": False, "offline": False, "keys": [jwk]}

    def transport(request):
        path = request.url.path
        if state["offline"]:
            return httpx.Response(503)
        if path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": issuer,
                    "jwks_uri": issuer + "/certs",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if path.endswith("/certs"):
            return httpx.Response(200, json={"keys": state["keys"]})
        if state["denied"]:
            return httpx.Response(403)
        if path == "/api/v1/me":
            return httpx.Response(
                200,
                json={
                    "user_id": str(uid),
                    "issuer": issuer,
                    "subject": sub,
                    "principal_type": "human",
                    "status": "active",
                },
            )
        if path == f"/api/v1/companies/{cid}/me/permissions":
            return httpx.Response(200, json={"company_id": str(cid), "permissions": []})
        return httpx.Response(404)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport), follow_redirects=False
    )
    provider = PlatformProvider(client)
    monkeypatch.setattr(app.state, "platform_provider", provider, raising=False)
    db_session.add_all(
        [
            PlatformUserBinding(
                core_api=core,
                core_user_id=uid,
                issuer=issuer,
                subject=sub,
                user_id=user.id,
            ),
            PlatformCompanyBinding(
                core_api=core, core_company_id=cid, company_id=company
            ),
        ]
    )
    await db_session.commit()

    def token(**overrides):
        now = int(time.time())
        claims = {
            "iss": issuer,
            "sub": sub,
            "aud": ["xarionix-core", "xarionix-erp"],
            "azp": "xarionix-web",
            "typ": "Bearer",
            "iat": now,
            "exp": now + 120,
        }
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "first"})

    def headers(**overrides):
        return {
            "Authorization": "Bearer " + token(**overrides),
            "X-Core-Company-Id": str(cid),
            "X-Company-Id": str(company),
        }

    yield SimpleNamespace(
        company=company,
        legacy=legacy,
        user=user.id,
        uid=uid,
        cid=cid,
        core=core,
        headers=headers,
        token=token,
        state=state,
        provider=provider,
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_verified_context_keeps_ids_rights_and_map_writes(
    platform, api_client, db_session
):
    before = await db_session.scalar(select(func.count()).select_from(User))
    response = await api_client.get(
        "/api/v1/auth/platform-context", headers=platform.headers()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["core_user_id"] == str(platform.uid) and body["core_company_id"] == str(
        platform.cid
    )
    assert (
        body["company"]["id"] == platform.company
        and body["user"]["id"] == platform.user
    )
    assert "addresses.read" in body["permissions"]
    created = await api_client.post(
        "/api/v1/map/markers",
        headers=platform.headers(),
        json=marker_payload(visibility="private"),
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner_user_id"] == platform.user
    assert (
        await api_client.get("/api/v1/map/markers", headers=platform.headers())
    ).json()[0]["id"] == created.json()["id"]
    assert before == await db_session.scalar(select(func.count()).select_from(User))
    assert (
        await api_client.post("/api/v1/auth/logout", headers=platform.headers())
    ).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim",
    [
        {"aud": "xarionix-core"},
        {"iss": "https://other.example.test"},
        {"exp": 1},
        {"nbf": 9999999999},
        {"azp": "other-client"},
        {"typ": "ID"},
        {"xarionix_principal": "machine"},
    ],
)
async def test_invalid_or_core_only_tokens_never_fall_back(platform, api_client, claim):
    assert (
        await api_client.get(
            "/api/v1/auth/platform-context", headers=platform.headers(**claim)
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_live_revocation_and_fail_closed_provider(
    platform, api_client, db_session
):
    headers = platform.headers()
    assert (
        await api_client.get("/api/v1/auth/platform-context", headers=headers)
    ).status_code == 200
    platform.state["denied"] = True
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 403
    platform.state["denied"] = False
    platform.state["offline"] = True
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 503
    platform.state["offline"] = False
    row = await db_session.get(PlatformUserBinding, (platform.core, platform.uid))
    row.is_active = False
    await db_session.commit()
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_numeric_company_spoof_is_denied(platform, api_client):
    headers = platform.headers() | {"X-Company-Id": str(platform.company + 1)}
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 403
    headers = platform.headers() | {"X-Core-Company-Id": str(uuid4())}
    assert (
        await api_client.get("/api/v1/auth/platform-context", headers=headers)
    ).status_code == 403
    headers = platform.headers()
    del headers["X-Core-Company-Id"]
    assert (
        await api_client.get("/api/v1/auth/platform-context", headers=headers)
    ).status_code == 400


@pytest.mark.asyncio
async def test_binding_identity_mismatch_and_no_auto_link(
    platform, api_client, db_session
):
    row = await db_session.get(PlatformUserBinding, (platform.core, platform.uid))
    row.subject = "different-verified-human"
    await db_session.commit()
    response = await api_client.get(
        "/api/v1/auth/platform-context", headers=platform.headers()
    )
    assert (
        response.status_code == 403
        and response.json()["detail"] == "core_identity_unlinked"
    )


@pytest.mark.asyncio
async def test_wrong_signature_unknown_key_and_rotation(platform, api_client):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(platform.token(), options={"verify_signature": False})
    wrong = jwt.encode(claims, other, algorithm="RS256", headers={"kid": "first"})
    headers = platform.headers() | {"Authorization": "Bearer " + wrong}
    assert (
        await api_client.get("/api/v1/auth/platform-context", headers=headers)
    ).status_code == 401
    rotated = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(other.public_key())) | {
        "kid": "second",
        "alg": "RS256",
        "use": "sig",
    }
    platform.state["keys"] = [rotated]
    platform.provider.verifier.retry_after = 0
    new = jwt.encode(claims, other, algorithm="RS256", headers={"kid": "second"})
    assert (
        await api_client.get(
            "/api/v1/auth/platform-context",
            headers=platform.headers() | {"Authorization": "Bearer " + new},
        )
    ).status_code == 200
    # Missing JWKS after expiry never reuses an expired trust cache.
    platform.state["offline"] = True
    platform.provider.verifier.expires = platform.provider.verifier.retry_after = 0
    assert (
        await api_client.get(
            "/api/v1/auth/platform-context", headers=platform.headers()
        )
    ).status_code == 401


def test_platform_configuration_is_explicit_and_tls_validated():
    from core.config import Config

    values = config.model_dump()
    values.update(
        PLATFORM_OIDC_ENABLED=True,
        PLATFORM_CORE_API="https://core.example.test/api/v1",
        PLATFORM_OIDC_ISSUER="https://identity.example.test/realms/xarionix",
        PLATFORM_OIDC_CLIENT_ID="web",
    )
    assert Config(**values).PLATFORM_OIDC_ENABLED
    for patch in (
        {"PLATFORM_CORE_API": "http://core.example.test/api/v1"},
        {"PLATFORM_OIDC_ISSUER": "https://user:password@example.test/realms/x"},
        {"PLATFORM_OIDC_ISSUER": "https://example.test/realms/x?key=secret"},
        {"PLATFORM_OIDC_AUDIENCE": "xarionix-core"},
        {"PLATFORM_OIDC_CLIENT_ID": ""},
    ):
        with pytest.raises(ValueError):
            Config(**(values | patch))


@pytest.mark.asyncio
async def test_legacy_session_is_compatible_but_cannot_claim_core_context(
    platform, api_client
):
    headers = {
        "Authorization": "Bearer " + platform.legacy,
        "X-Company-Id": str(platform.company),
    }
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 200
    headers["X-Core-Company-Id"] = str(platform.cid)
    assert (
        await api_client.get("/api/v1/map/markers", headers=headers)
    ).status_code == 401


@pytest.mark.asyncio
async def test_core_membership_does_not_bypass_erp_membership(
    platform, api_client, db_session
):
    from models.company_memberships import CompanyMembership

    member = await db_session.scalar(
        select(CompanyMembership).where(
            CompanyMembership.company_id == platform.company,
            CompanyMembership.user_id == platform.user,
        )
    )
    member.is_active = False
    await db_session.commit()
    assert (
        await api_client.get(
            "/api/v1/auth/platform-context", headers=platform.headers()
        )
    ).status_code == 403
