from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.billing_models import BillingInterval


MONEY_QUANTUM = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def add_billing_period(start: datetime, interval: BillingInterval | str) -> datetime:
    value = as_utc(start)
    months = 12 if str(getattr(interval, "value", interval)) == BillingInterval.annual.value else 1
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def period_fraction_remaining(start: datetime, end: datetime, at: datetime) -> Decimal:
    start_utc, end_utc, at_utc = as_utc(start), as_utc(end), as_utc(at)
    total_seconds = Decimal(str(max((end_utc - start_utc).total_seconds(), 1)))
    remaining_seconds = Decimal(str(max((end_utc - at_utc).total_seconds(), 0)))
    return min(Decimal("1"), max(Decimal("0"), remaining_seconds / total_seconds))
