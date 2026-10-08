from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
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
    auth_cookie_secure: bool | None = None
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_cookie_domain: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    oauth_state_minutes: int = Field(default=10, ge=5, le=30)
    auto_create_schema: bool = True
    billing_webhook_secret: str = "change-this-billing-webhook-secret"
    notification_receipt_webhook_secret: str = "change-this-notification-receipt-secret"
    mock_payment_success_rate: float = Field(default=0.82, ge=0, le=1)
    payment_retry_schedule_days: str = "1,3,7"
    pending_payment_timeout_seconds: int = Field(default=900, ge=30, le=86400)
    gateway_poll_interval_seconds: int = Field(default=60, ge=10, le=3600)
    gateway_status_base_url: str | None = None
    gateway_status_token: str | None = None
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    notification_claim_batch_size: int = Field(default=100, ge=1, le=1000)
    notification_lease_seconds: int = Field(default=120, ge=30, le=3600)
    notification_max_attempts: int = Field(default=5, ge=1, le=20)
    notification_backoff_base_seconds: int = Field(default=30, ge=1, le=3600)
    notification_backoff_cap_seconds: int = Field(default=3600, ge=30, le=86400)
    email_provider: str = "sandbox"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "notifications@billflow.local"
    smtp_starttls: bool = True
    sms_provider: str = "sandbox"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    push_provider: str = "sandbox"
    fcm_project_id: str | None = None
    fcm_service_account_json: str | None = None
    queue_backlog_alert_threshold: int = Field(default=250, ge=1)
    queue_oldest_alert_seconds: int = Field(default=900, ge=30)
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0, le=1)
    invoice_business_name: str = "BillFlow AI"
    invoice_business_address: str = "Finance Operations, India"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> Self:
        if bool(self.google_client_id) != bool(self.google_client_secret):
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together")
        if self.auth_cookie_samesite == "none" and not self.secure_auth_cookies:
            raise ValueError("AUTH_COOKIE_SAMESITE=none requires secure authentication cookies")
        if self.environment.lower() == "production":
            unsafe_secret = (
                len(self.jwt_secret) < 32
                or self.jwt_secret.startswith("change-this")
                or self.jwt_secret.startswith("replace-with")
            )
            if unsafe_secret:
                raise ValueError("Production JWT_SECRET must be a non-placeholder secret of at least 32 characters")
            if not self.secure_auth_cookies:
                raise ValueError("Production authentication cookies must be secure")
            if not self.frontend_url.lower().startswith("https://"):
                raise ValueError("Production FRONTEND_URL must use HTTPS")
            if self.google_oauth_enabled and not self.google_redirect_uri.lower().startswith("https://"):
                raise ValueError("Production GOOGLE_REDIRECT_URI must use HTTPS")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def secure_auth_cookies(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.environment.lower() == "production"

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.google_redirect_uri)

    @property
    def retry_schedule_days(self) -> list[int]:
        values = sorted({int(value.strip()) for value in self.payment_retry_schedule_days.split(",") if value.strip()})
        return [value for value in values if value >= 0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
