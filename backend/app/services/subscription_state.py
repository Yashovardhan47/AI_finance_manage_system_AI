from datetime import datetime

from app.billing_models import BillingSubscription, SubscriptionStatus
from app.services.billing_utils import as_utc, utcnow


ALLOWED_TRANSITIONS: dict[SubscriptionStatus, set[SubscriptionStatus]] = {
    SubscriptionStatus.trial: {SubscriptionStatus.active, SubscriptionStatus.cancelled},
    SubscriptionStatus.active: {
        SubscriptionStatus.past_due,
        SubscriptionStatus.paused,
        SubscriptionStatus.cancelled,
    },
    SubscriptionStatus.past_due: {
        SubscriptionStatus.active,
        SubscriptionStatus.paused,
        SubscriptionStatus.cancelled,
    },
    SubscriptionStatus.paused: {SubscriptionStatus.active, SubscriptionStatus.cancelled},
    SubscriptionStatus.cancelled: set(),
}


class InvalidSubscriptionTransition(ValueError):
    pass


def transition_subscription(
    subscription: BillingSubscription,
    target: SubscriptionStatus,
    *,
    at: datetime | None = None,
    reason: str | None = None,
) -> BillingSubscription:
    now = as_utc(at or utcnow())
    current = SubscriptionStatus(subscription.status)
    target = SubscriptionStatus(target)
    if current == target:
        return subscription
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidSubscriptionTransition(f"Cannot transition subscription from {current.value} to {target.value}")

    subscription.status = target
    subscription.status_changed_at = now
    subscription.version += 1
    if target == SubscriptionStatus.active:
        subscription.activated_at = subscription.activated_at or now
        subscription.past_due_at = None
        subscription.paused_at = None
        subscription.resumes_at = None
    elif target == SubscriptionStatus.past_due:
        subscription.past_due_at = now
    elif target == SubscriptionStatus.paused:
        subscription.paused_at = now
    elif target == SubscriptionStatus.cancelled:
        subscription.cancelled_at = now
        subscription.next_billing_at = None
        subscription.cancel_at_period_end = False
        subscription.cancellation_reason = reason or subscription.cancellation_reason
    return subscription


def status_timeline(subscription: BillingSubscription) -> dict[str, str | None]:
    return {
        "trial_started_at": subscription.trial_started_at.isoformat() if subscription.trial_started_at else None,
        "activated_at": subscription.activated_at.isoformat() if subscription.activated_at else None,
        "past_due_at": subscription.past_due_at.isoformat() if subscription.past_due_at else None,
        "paused_at": subscription.paused_at.isoformat() if subscription.paused_at else None,
        "cancelled_at": subscription.cancelled_at.isoformat() if subscription.cancelled_at else None,
        "status_changed_at": subscription.status_changed_at.isoformat(),
    }
