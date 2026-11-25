from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TaskFlow API"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./taskflow.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
