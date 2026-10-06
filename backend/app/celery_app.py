from celery import Celery

from app.core.config import get_settings


settings = get_settings()
if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
celery_app = Celery(
    "billflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=270,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3600},
    task_default_queue="billing.default",
    task_routes={
        "billing.deliver_notifications": {"queue": "billing.notifications"},
        "billing.monitor_pending_payments": {"queue": "billing.incidents"},
        "billing.poll_gateway_status": {"queue": "billing.reconciliation"},
        "billing.escalate_incidents": {"queue": "billing.incidents"},
        "billing.monitor_queue_health": {"queue": "billing.monitoring"},
    },
    beat_schedule={
        "billing-cycle-scan": {"task": "billing.process_due_cycles", "schedule": 300.0},
        "payment-retry-scan": {"task": "billing.process_due_retries", "schedule": 300.0},
        "notification-outbox": {"task": "billing.deliver_notifications", "schedule": 30.0},
        "pending-payment-watchdog": {"task": "billing.monitor_pending_payments", "schedule": 60.0},
        "gateway-status-poll": {"task": "billing.poll_gateway_status", "schedule": 60.0},
        "incident-escalation": {"task": "billing.escalate_incidents", "schedule": 60.0},
        "queue-health": {"task": "billing.monitor_queue_health", "schedule": 60.0},
    },
)
