from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import Settings


HTTP_REQUESTS = Counter(
    "billflow_http_requests_total",
    "HTTP requests handled by BillFlow",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "billflow_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "route"),
)
NOTIFICATION_ATTEMPTS = Counter(
    "billflow_notification_delivery_attempts_total",
    "Notification delivery attempts",
    ("channel", "provider", "outcome"),
)
PAYMENT_RECONCILIATIONS = Counter(
    "billflow_payment_reconciliations_total",
    "Gateway status reconciliation checks",
    ("gateway", "outcome"),
)
INCIDENTS_OPENED = Counter(
    "billflow_payment_incidents_opened_total",
    "Payment incidents opened",
    ("incident_type", "severity"),
)
OUTBOX_QUEUED = Gauge("billflow_outbox_queued", "Queued notification outbox rows")
OUTBOX_OLDEST_SECONDS = Gauge("billflow_outbox_oldest_age_seconds", "Age of the oldest queued notification")
PAYMENTS_PENDING = Gauge("billflow_payments_pending", "Pending gateway payments")
DEAD_LETTERS = Gauge("billflow_task_dead_letters", "Unresolved Celery dead letters")
OPEN_INCIDENTS = Gauge("billflow_open_payment_incidents", "Open or acknowledged payment incidents")


def configure_monitoring(app: FastAPI, settings: Settings) -> None:
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )

    @app.middleware("http")
    async def prometheus_http_metrics(request: Request, call_next):
        started = time.perf_counter()
        response_status = 500
        try:
            response = await call_next(request)
            response_status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_name = getattr(route, "path", request.url.path)
            HTTP_REQUESTS.labels(request.method, route_name, str(response_status)).inc()
            HTTP_LATENCY.labels(request.method, route_name).observe(time.perf_counter() - started)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        try:
            from app.database import SessionLocal
            from app.services.payment_incidents import queue_health_snapshot

            with SessionLocal() as db:
                queue_health_snapshot(db)
        except Exception as exc:
            if settings.sentry_dsn:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
