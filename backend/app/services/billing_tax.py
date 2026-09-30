from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.billing_models import BillingCustomer, TaxRate


def resolve_tax_rate(
    db: Session,
    *,
    owner_user_id: int,
    customer: BillingCustomer,
    on_date: date,
) -> TaxRate | None:
    candidates = list(
        db.scalars(
            select(TaxRate)
            .where(
                TaxRate.owner_user_id == owner_user_id,
                TaxRate.country_code == customer.country_code.upper(),
                TaxRate.is_active.is_(True),
                TaxRate.effective_from <= on_date,
                or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= on_date),
            )
            .order_by(TaxRate.region.is_(None), TaxRate.effective_from.desc())
        )
    )
    exact = next((item for item in candidates if item.region and item.region == customer.region), None)
    return exact or next((item for item in candidates if item.region is None), None)
