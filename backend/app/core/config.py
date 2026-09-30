from functools import lru_cache

from pydantic import Field
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
    auto_create_schema: bool = True
    billing_webhook_secret: str = "change-this-billing-webhook-secret"
    mock_payment_success_rate: float = Field(default=0.82, ge=0, le=1)
    payment_retry_schedule_days: str = "1,3,7"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    invoice_business_name: str = "BillFlow AI"
    invoice_business_address: str = "Finance Operations, India"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def retry_schedule_days(self) -> list[int]:
        values = sorted({int(value.strip()) for value in self.payment_retry_schedule_days.split(",") if value.strip()})
        return [value for value in values if value >= 0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
