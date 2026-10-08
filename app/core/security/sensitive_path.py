from collections.abc import (
    Awaitable,
    Callable,
)

from typing import Any


ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp = Callable[
    [dict[str, Any], ASGIReceive, ASGISend],
    Awaitable[None],
]


class RedactInvitationTokenPathMiddleware:
    """
    Hide public invitation tokens from HTTP access logs.

    Routing sees the original path. The ASGI scope is redacted
    immediately before response.start reaches the server, which
    is when Uvicorn writes its access-log record.
    """

    _PATH_PREFIX = "/api/v1/invitations/"
    _REDACTED_SEGMENT = "_redacted_"


    def __init__(self, app: ASGIApp):
        self.app = app


    async def __call__(
        self,
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path")

        if (
            not isinstance(path, str)
            or not path.startswith(
                self._PATH_PREFIX
            )
        ):
            await self.app(scope, receive, send)
            return

        token_and_suffix = path[
            len(self._PATH_PREFIX):
        ]

        if not token_and_suffix:
            await self.app(scope, receive, send)
            return

        separator_index = (
            token_and_suffix.find("/")
        )

        suffix = (
            token_and_suffix[
                separator_index:
            ]
            if separator_index >= 0
            else ""
        )

        redacted_path = (
            self._PATH_PREFIX
            + self._REDACTED_SEGMENT
            + suffix
        )


        async def send_with_redacted_path(
            message: ASGIMessage,
        ) -> None:
            if (
                message.get("type")
                == "http.response.start"
            ):
                scope["path"] = redacted_path
                scope["raw_path"] = (
                    redacted_path.encode("ascii")
                )

            await send(message)


        await self.app(
            scope,
            receive,
            send_with_redacted_path,
        )
