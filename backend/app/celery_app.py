from celery import Celery

from app.core.config import get_settings


settings = get_settings()
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
    worker_prefetch_multiplier=1,
    beat_schedule={
        "billing-cycle-scan": {"task": "billing.process_due_cycles", "schedule": 300.0},
        "payment-retry-scan": {"task": "billing.process_due_retries", "schedule": 300.0},
        "notification-outbox": {"task": "billing.deliver_notifications", "schedule": 60.0},
    },
)
