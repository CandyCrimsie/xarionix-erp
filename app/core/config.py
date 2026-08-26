from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    HOST: str
    PORT: int

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='allow'
    )

config = Config()