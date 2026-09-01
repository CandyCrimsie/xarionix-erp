import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from redis.exceptions import WatchError

from core.security.refresh import (
    InvalidRefreshTokenError,
    build_refresh_token,
    generate_refresh_secret,
    hash_refresh_secret,
    parse_refresh_token,
)
from database.redis import redis_client


SESSION_TTL_SECONDS = 60 * 60 * 24 * 30


class SessionNotFoundError(Exception):
    pass


@dataclass(slots=True, frozen=True)
class CreatedSession:
    session_id: UUID
    refresh_token: str


@dataclass(slots=True, frozen=True)
class RefreshedSession:
    session_id: UUID
    user_id: int
    refresh_token: str


@dataclass(slots=True, frozen=True)
class AuthSession:
    session_id: UUID
    user_id: int

    created_at: datetime
    last_used_at: datetime

    ip_address: str | None
    user_agent: str | None


async def create_session(
    *,
    user_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> CreatedSession:
    session_id = uuid4()

    refresh_secret = generate_refresh_secret()
    refresh_hash = hash_refresh_secret(refresh_secret)

    now = datetime.now(timezone.utc)

    data = {
        "user_id": user_id,
        "refresh_hash": refresh_hash,
        "created_at": now.isoformat(),
        "last_used_at": now.isoformat(),
        "ip_address": ip_address,
        "user_agent": user_agent,
    }

    await redis_client.set(
        f"auth:session:{session_id}",
        json.dumps(data),
        ex=SESSION_TTL_SECONDS,
    )

    await redis_client.sadd(
        f"auth:user-sessions:{user_id}",
        str(session_id),
    )

    refresh_token = build_refresh_token(
        session_id,
        refresh_secret,
    )

    return CreatedSession(
        session_id=session_id,
        refresh_token=refresh_token,
    )


async def rotate_refresh_token(
    token: str,
) -> RefreshedSession:
    session_id, old_secret = parse_refresh_token(token)

    key = f"auth:session:{session_id}"

    old_hash = hash_refresh_secret(old_secret)

    for _ in range(3):
        try:
            async with redis_client.pipeline() as pipe:
                await pipe.watch(key)

                raw_session = await pipe.get(key)

                if raw_session is None:
                    raise InvalidRefreshTokenError

                data = json.loads(raw_session)

                stored_hash = data.get("refresh_hash")

                if stored_hash != old_hash:
                    raise InvalidRefreshTokenError

                ttl = await pipe.ttl(key)

                if ttl <= 0:
                    raise InvalidRefreshTokenError

                new_secret = generate_refresh_secret()
                new_hash = hash_refresh_secret(new_secret)

                data["refresh_hash"] = new_hash
                data["last_used_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

                pipe.multi()

                pipe.set(
                    key,
                    json.dumps(data),
                    ex=ttl,
                )

                await pipe.execute()

                return RefreshedSession(
                    session_id=session_id,
                    user_id=int(data["user_id"]),
                    refresh_token=build_refresh_token(
                        session_id,
                        new_secret,
                    ),
                )

        except WatchError:
            continue

    raise InvalidRefreshTokenError


async def get_auth_session(
    session_id: UUID,
) -> AuthSession | None:
    key = f"auth:session:{session_id}"

    raw_session = await redis_client.get(key)

    if raw_session is None:
        return None

    try:
        data = json.loads(raw_session)

        return AuthSession(
            session_id=session_id,
            user_id=int(data["user_id"]),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            last_used_at=datetime.fromisoformat(
                data["last_used_at"]
            ),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
        )

    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None


async def delete_session(
    *,
    user_id: int,
    session_id: UUID,
) -> None:
    session_key = f"auth:session:{session_id}"
    user_sessions_key = f"auth:user-sessions:{user_id}"

    async with redis_client.pipeline(
        transaction=True
    ) as pipe:
        pipe.delete(session_key)

        pipe.srem(
            user_sessions_key,
            str(session_id),
        )

        await pipe.execute()


async def delete_user_session(
    *,
    user_id: int,
    session_id: UUID,
) -> None:
    auth_session = await get_auth_session(
        session_id
    )

    if (
        auth_session is None
        or auth_session.user_id != user_id
    ):
        raise SessionNotFoundError

    await delete_session(
        user_id=user_id,
        session_id=session_id,
    )


async def get_user_sessions(
    user_id: int,
) -> list[AuthSession]:
    user_sessions_key = (
        f"auth:user-sessions:{user_id}"
    )

    session_ids = await redis_client.smembers(
        user_sessions_key
    )

    if not session_ids:
        return []

    valid_ids: list[tuple[str, UUID]] = []
    stale_ids: list[str] = []

    for raw_id in session_ids:
        try:
            valid_ids.append(
                (raw_id, UUID(raw_id))
            )
        except ValueError:
            stale_ids.append(raw_id)

    if not valid_ids:
        if stale_ids:
            await redis_client.srem(
                user_sessions_key,
                *stale_ids,
            )

        return []

    async with redis_client.pipeline() as pipe:
        for _, session_id in valid_ids:
            pipe.get(
                f"auth:session:{session_id}"
            )

        raw_sessions = await pipe.execute()

    sessions: list[AuthSession] = []

    for (
        (raw_id, session_id),
        raw_session,
    ) in zip(valid_ids, raw_sessions):
        if raw_session is None:
            stale_ids.append(raw_id)
            continue

        try:
            data = json.loads(raw_session)

            session_user_id = int(
                data["user_id"]
            )

            if session_user_id != user_id:
                stale_ids.append(raw_id)
                continue

            sessions.append(
                AuthSession(
                    session_id=session_id,
                    user_id=session_user_id,
                    created_at=datetime.fromisoformat(
                        data["created_at"]
                    ),
                    last_used_at=datetime.fromisoformat(
                        data["last_used_at"]
                    ),
                    ip_address=data.get(
                        "ip_address"
                    ),
                    user_agent=data.get(
                        "user_agent"
                    ),
                )
            )

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            stale_ids.append(raw_id)

    if stale_ids:
        await redis_client.srem(
            user_sessions_key,
            *stale_ids,
        )

    return sessions


async def delete_all_user_sessions(
    user_id: int,
) -> None:
    user_sessions_key = (
        f"auth:user-sessions:{user_id}"
    )

    session_ids = await redis_client.smembers(
        user_sessions_key
    )

    if not session_ids:
        return

    async with redis_client.pipeline(
        transaction=True
    ) as pipe:
        for session_id in session_ids:
            pipe.delete(
                f"auth:session:{session_id}"
            )

        pipe.delete(user_sessions_key)

        await pipe.execute()