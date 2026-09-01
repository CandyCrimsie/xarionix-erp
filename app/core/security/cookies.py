from fastapi import Response

from core.config import config


REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(
    response: Response,
    refresh_token: str,
) -> None:
    max_age = (
        config.REFRESH_TOKEN_EXPIRE_DAYS
        * 24
        * 60
        * 60
    )

    response.set_cookie(
        key=config.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def delete_refresh_cookie(
    response: Response,
) -> None:
    response.delete_cookie(
        key=config.REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=config.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )