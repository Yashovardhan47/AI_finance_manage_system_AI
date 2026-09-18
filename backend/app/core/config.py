from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BillFlow AI"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./billflow.db"
    jwt_secret: str = "change-this-development-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

