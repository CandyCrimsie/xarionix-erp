from pydantic import (
    Field,
    field_validator,
    model_validator,
)

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Config(BaseSettings):
    HOST: str
    PORT: int

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    REDIS_DB: int

    JWT_SECRET: str
    JWT_ALGORITHM: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int

    REFRESH_TOKEN_EXPIRE_DAYS: int
    REFRESH_COOKIE_NAME: str
    COOKIE_SECURE: bool

    SYSTEM_ADMIN_USERNAME: str = Field(
        min_length=3,
        max_length=64,
    )

    SYSTEM_ADMIN_PASSWORD: str = Field(
        min_length=8,
        max_length=128,
    )

    INVITATION_DEFAULT_EXPIRE_HOURS: int = Field(
        default=72,
        ge=1,
        le=720,
    )

    INVITATION_MAX_EXPIRE_HOURS: int = Field(
        default=720,
        ge=1,
        le=8760,
    )

    INVITATION_TOKEN_BYTES: int = Field(
        default=32,
        ge=32,
        le=64,
    )

    MAP_TILES_ENABLED: bool = False
    MAP_TILES_SIGNING_SECRET: str = Field(
        default="",
        max_length=256,
    )
    MAP_TILE_SESSION_TTL_SECONDS: int = Field(
        default=600,
        ge=60,
        le=3600,
    )
    MAP_MAX_BUILDINGS_PER_VIEWPORT: int = Field(
        default=2000,
        ge=100,
        le=10000,
    )


    @model_validator(mode="after")
    def validate_invitation_expiration(
        self,
    ) -> "Config":
        if (
            self.INVITATION_DEFAULT_EXPIRE_HOURS
            > self.INVITATION_MAX_EXPIRE_HOURS
        ):
            raise ValueError(
                "Default invitation expiration cannot "
                "exceed maximum invitation expiration"
            )

        if self.MAP_TILES_ENABLED:
            secret = self.MAP_TILES_SIGNING_SECRET
            if len(secret) < 32:
                raise ValueError(
                    "MAP_TILES_SIGNING_SECRET must contain at least "
                    "32 characters when map tiles are enabled"
                )

            if not all(
                character.isalnum() or character in "_-"
                for character in secret
            ):
                raise ValueError(
                    "MAP_TILES_SIGNING_SECRET may contain only letters, "
                    "digits, underscores and hyphens"
                )

        return self


    @field_validator(
        "SYSTEM_ADMIN_USERNAME"
    )
    @classmethod
    def normalize_system_admin_username(
        cls,
        value: str,
    ) -> str:
        value = (
            value.strip()
            .lower()
        )

        if not value:
            raise ValueError(
                "System administrator username "
                "cannot be empty"
            )

        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='allow'
    )

config = Config()
