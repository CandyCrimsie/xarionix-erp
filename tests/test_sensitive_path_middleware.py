import pytest

from core.security.sensitive_path import (
    RedactInvitationTokenPathMiddleware,
)


@pytest.mark.asyncio
async def test_invitation_token_is_available_to_router_but_redacted_before_response():
    original_path = (
        "/api/v1/invitations/raw-secret-token"
        "/accept-existing"
    )

    scope = {
        "type": "http",
        "path": original_path,
        "raw_path": original_path.encode("ascii"),
    }

    routed_paths: list[str] = []
    sent_paths: list[str] = []


    async def inner_app(
        inner_scope,
        receive,
        send,
    ):
        routed_paths.append(inner_scope["path"])

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        })

        await send({
            "type": "http.response.body",
            "body": b"",
        })


    async def receive():
        return {
            "type": "http.request",
            "body": b"",
        }


    async def send(message):
        if message["type"] == "http.response.start":
            sent_paths.append(scope["path"])


    middleware = (
        RedactInvitationTokenPathMiddleware(
            inner_app
        )
    )

    await middleware(scope, receive, send)

    assert routed_paths == [original_path]
    assert sent_paths == [
        (
            "/api/v1/invitations/_redacted_"
            "/accept-existing"
        )
    ]


@pytest.mark.asyncio
async def test_non_invitation_path_is_not_changed():
    original_path = "/api/v1/me/companies"

    scope = {
        "type": "http",
        "path": original_path,
        "raw_path": original_path.encode("ascii"),
    }


    async def inner_app(
        inner_scope,
        receive,
        send,
    ):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        })


    async def receive():
        return {
            "type": "http.request",
            "body": b"",
        }


    async def send(message):
        pass


    middleware = (
        RedactInvitationTokenPathMiddleware(
            inner_app
        )
    )

    await middleware(scope, receive, send)

    assert scope["path"] == original_path
