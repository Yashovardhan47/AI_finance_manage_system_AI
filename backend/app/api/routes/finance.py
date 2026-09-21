from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models import Bill, FinancialAccount, Transaction, User
from app.schemas import (
    AccountCreate,
    AccountRead,
    BillCreate,
    BillRead,
    TransactionCreate,
    TransactionRead,
    UserPreferencesUpdate,
    UserRead,
)
from app.services.audit import write_audit


router = APIRouter(tags=["finance"])


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[FinancialAccount]:
    return list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id).order_by(FinancialAccount.id)))


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialAccount:
    account = FinancialAccount(user_id=user.id, **payload.model_dump())
    db.add(account)
    db.flush()
    write_audit(db, user_id=user.id, action="account.created", entity_type="account", entity_id=account.id)
    db.commit()
    db.refresh(account)
    return account


@router.get("/bills", response_model=list[BillRead])
def list_bills(
    bill_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Bill]:
    query = select(Bill).where(Bill.user_id == user.id)
    if bill_status:
        query = query.where(Bill.status == bill_status)
    return list(db.scalars(query.order_by(Bill.due_date, Bill.id)))


@router.post("/bills", response_model=BillRead, status_code=status.HTTP_201_CREATED)
def create_bill(payload: BillCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Bill:
    bill = Bill(user_id=user.id, **payload.model_dump())
    db.add(bill)
    db.flush()
    write_audit(db, user_id=user.id, action="bill.created", entity_type="bill", entity_id=bill.id, detail={"amount": str(bill.amount)})
    db.commit()
    db.refresh(bill)
    return bill


@router.patch("/bills/{bill_id}/autopay", response_model=BillRead)
def toggle_autopay(
    bill_id: int,
    enabled: bool,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Bill:
    bill = db.scalar(select(Bill).where(Bill.id == bill_id, Bill.user_id == user.id))
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill.autopay_enabled = enabled
    write_audit(
        db,
        user_id=user.id,
        action="bill.autopay_updated",
        entity_type="bill",
        entity_id=bill.id,
        detail={"enabled": enabled, "authorization_required": True},
    )
    db.commit()
    db.refresh(bill)
    return bill


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.occurred_at.desc())
            .limit(limit)
        )
    )


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transaction:
    if payload.account_id and not db.scalar(
        select(FinancialAccount).where(FinancialAccount.id == payload.account_id, FinancialAccount.user_id == user.id)
    ):
        raise HTTPException(status_code=404, detail="Account not found")
    data = payload.model_dump(exclude_none=True)
    transaction = Transaction(user_id=user.id, occurred_at=data.pop("occurred_at", datetime.now(timezone.utc)), **data)
    db.add(transaction)
    db.flush()
    write_audit(db, user_id=user.id, action="transaction.added", entity_type="transaction", entity_id=transaction.id)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.patch("/profile/preferences", response_model=UserRead)
def update_preferences(
    payload: UserPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    write_audit(db, user_id=user.id, action="preferences.updated", entity_type="user", entity_id=user.id, detail={key: str(value) for key, value in changes.items()})
    db.commit()
    db.refresh(user)
    return user

