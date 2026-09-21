from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user
from app.database import get_db
from app.models import Bill, FinancialAccount, Payment, Transaction, User
from app.schemas import PaymentPrepare, PaymentRead
from app.services.audit import write_audit
from app.services.payment_provider import get_payment_provider
from app.services.provider_connectors import settle_external_provider
from app.services.receipt import build_payment_receipt


router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentRead])
def list_payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())))


@router.post("/prepare", response_model=PaymentRead)
def prepare_payment(
    payload: PaymentPrepare,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Payment:
    existing = db.scalar(
        select(Payment).where(Payment.user_id == user.id, Payment.idempotency_key == payload.idempotency_key)
    )
    if existing:
        return existing
    bill = db.scalar(select(Bill).where(Bill.id == payload.bill_id, Bill.user_id == user.id))
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == payload.account_id, FinancialAccount.user_id == user.id))
    if not bill or not account:
        raise HTTPException(status_code=404, detail="Bill or funding account not found")
    if bill.status == "paid":
        raise HTTPException(status_code=409, detail="This bill is already paid")
    payment = Payment(
        user_id=user.id,
        bill_id=bill.id,
        account_id=account.id,
        amount=bill.amount,
        idempotency_key=payload.idempotency_key,
        status="requires_authorization",
        provider_sync_status="awaiting_payment" if bill.provider_connection_id else "not_required",
    )
    db.add(payment)
    db.flush()
    provider_session = get_payment_provider().prepare(payment.id)
    payment.provider = provider_session.provider
    payment.status = provider_session.status
    payment.checkout_url = provider_session.checkout_url
    write_audit(
        db,
        user_id=user.id,
        action="payment.prepared",
        entity_type="payment",
        entity_id=payment.id,
        detail={"bill_id": bill.id, "account_id": account.id, "authorization_required": True},
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/{payment_id}/receipt")
def download_receipt(
    payment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    payment = db.scalar(
        select(Payment)
        .options(joinedload(Payment.bill), joinedload(Payment.account))
        .where(Payment.id == payment_id, Payment.user_id == user.id)
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "succeeded":
        raise HTTPException(status_code=409, detail="A receipt is available after payment succeeds")
    return StreamingResponse(
        build_payment_receipt(payment),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="billflow-receipt-{payment.id}.pdf"'},
    )


@router.post("/{payment_id}/confirm", response_model=PaymentRead)
def confirm_sandbox_payment(
    payment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Payment:
    payment = db.scalar(
        select(Payment)
        .options(joinedload(Payment.bill), joinedload(Payment.account))
        .where(Payment.id == payment_id, Payment.user_id == user.id)
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "succeeded":
        return payment
    if payment.status != "requires_authorization":
        raise HTTPException(status_code=409, detail="Payment cannot be confirmed in its current state")
    if payment.account.balance < payment.amount:
        payment.status = "failed"
        payment.failure_reason = "Insufficient sandbox account balance"
        write_audit(db, user_id=user.id, action="payment.failed", entity_type="payment", entity_id=payment.id, detail={"reason": payment.failure_reason})
        db.commit()
        raise HTTPException(status_code=409, detail=payment.failure_reason)

    payment.account.balance -= payment.amount
    payment.status = "succeeded"
    payment.completed_at = datetime.now(timezone.utc)
    payment.bill.status = "paid"
    db.add(
        Transaction(
            user_id=user.id,
            account_id=payment.account_id,
            bill_id=payment.bill_id,
            kind="expense",
            category=payment.bill.category,
            merchant=payment.bill.biller,
            amount=payment.amount,
            status="posted",
        )
    )
    provider_result = settle_external_provider(db, payment)
    write_audit(
        db,
        user_id=user.id,
        action="payment.succeeded",
        entity_type="payment",
        entity_id=payment.id,
        detail={
            "payment_provider": "sandbox",
            "external_provider_updated": bool(provider_result),
            "external_result": provider_result["result_action"] if provider_result else None,
            "provider_confirmation_id": provider_result["confirmation_id"] if provider_result else None,
        },
    )
    db.commit()
    db.refresh(payment)
    return payment
