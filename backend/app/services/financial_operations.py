"""Deterministic financial-operations intelligence and policy enforcement.

The engine may recommend and prepare actions, but it never moves money or mutates
a third-party account. Execution remains an explicit handoff to an authorized rail.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, FinancialAccount, Transaction, User
from app.operations_models import (
    ActionRequest,
    ExceptionCase,
    FinancialPolicy,
    Obligation,
    OutcomeEvent,
    Recommendation,
    Scenario,
)


OPEN_OBLIGATION_STATUSES = {"detected", "reviewed", "approved", "scheduled", "overdue"}
RECOMMENDABLE_STATUSES = {"detected", "reviewed", "scheduled", "overdue"}
ESSENTIAL_CATEGORIES = {"utility", "emi", "insurance", "health", "rent", "education", "tax"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal | float | int) -> float:
    return round(float(value), 2)


def get_or_create_policy(db: Session, user: User) -> FinancialPolicy:
    policy = db.scalar(select(FinancialPolicy).where(FinancialPolicy.user_id == user.id))
    if policy:
        return policy
    policy = FinancialPolicy(
        user_id=user.id,
        autonomy_mode="advise",
        minimum_reserve=user.minimum_balance,
        max_preparable_amount=Decimal("5000"),
        approval_above=Decimal("0"),
        allowed_categories=[],
        trusted_counterparties=[],
        require_provider_confirmation=True,
        protect_essential_first=True,
    )
    db.add(policy)
    db.flush()
    return policy


def sync_obligations_from_bills(db: Session, user: User) -> list[Obligation]:
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user.id).order_by(Bill.due_date, Bill.id)))
    synced: list[Obligation] = []
    for bill in bills:
        reference = f"bill:{bill.id}"
        obligation = db.scalar(
            select(Obligation).where(
                Obligation.user_id == user.id,
                Obligation.source == "bill",
                Obligation.external_reference == reference,
            )
        )
        obligation_status = "detected"
        if bill.status == "overdue":
            obligation_status = "overdue"
        elif bill.status in {"scheduled", "processing"}:
            obligation_status = "scheduled"
        elif bill.status == "paid":
            obligation_status = "verified" if bill.sync_status == "synced" else "paid"
        elif bill.status in {"cancelled", "void"}:
            obligation_status = "cancelled"
        if obligation and obligation_status == "detected" and obligation.status in {"approved", "disputed", "verified"}:
            obligation_status = obligation.status
        values = {
            "bill_id": bill.id,
            "provider_connection_id": bill.provider_connection_id,
            "name": bill.name,
            "counterparty": bill.biller,
            "category": bill.category,
            "amount": bill.amount,
            "currency": user.currency,
            "due_date": bill.due_date,
            "recurrence": bill.recurrence,
            "priority": 5 if bill.category in ESSENTIAL_CATEGORIES else 3,
            "essential": bill.category in ESSENTIAL_CATEGORIES,
            "status": obligation_status,
            "confidence": Decimal("1.000"),
            "contract_terms": {
                "service_action": bill.service_action,
                "autopay_enabled": bill.autopay_enabled,
                "provider_confirmation_required": bool(bill.provider_connection_id),
            },
            "evidence": {
                "bill_id": bill.id,
                "provider_reference": bill.provider_reference,
                "external_status": bill.external_status,
                "sync_status": bill.sync_status,
            },
        }
        if obligation:
            for key, value in values.items():
                setattr(obligation, key, value)
        else:
            obligation = Obligation(
                user_id=user.id,
                source="bill",
                external_reference=reference,
                **values,
            )
            db.add(obligation)
        synced.append(obligation)
    db.flush()
    return synced


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return date(year, month, min(value.day, month_lengths[month - 1]))


def _occurrences(obligation: Obligation, start: date, end: date) -> list[date]:
    current = (
        max(obligation.due_date, start)
        if obligation.due_date < start and obligation.recurrence == "once"
        else obligation.due_date
    )
    if obligation.recurrence == "once":
        return [max(start, current)] if current <= end else []
    dates: list[date] = []
    guard = 0
    while current < start and guard < 500:
        if obligation.recurrence == "weekly":
            current += timedelta(days=7)
        elif obligation.recurrence == "monthly":
            current = _add_months(current, 1)
        elif obligation.recurrence == "quarterly":
            current = _add_months(current, 3)
        elif obligation.recurrence == "yearly":
            current = _add_months(current, 12)
        else:
            return [max(start, obligation.due_date)] if obligation.due_date <= end else []
        guard += 1
    while current <= end and len(dates) < 100:
        dates.append(current)
        if obligation.recurrence == "weekly":
            current += timedelta(days=7)
        elif obligation.recurrence == "monthly":
            current = _add_months(current, 1)
        elif obligation.recurrence == "quarterly":
            current = _add_months(current, 3)
        elif obligation.recurrence == "yearly":
            current = _add_months(current, 12)
        else:
            break
    return dates


def forecast_financial_twin(
    user: User,
    accounts: list[FinancialAccount],
    obligations: list[Obligation],
    transactions: list[Transaction],
    days: int = 90,
) -> dict:
    days = max(7, min(days, 180))
    today = date.today()
    end = today + timedelta(days=days)
    starting_balance = sum((account.balance for account in accounts if account.is_active), Decimal("0"))
    cutoff = utcnow() - timedelta(days=60)
    recent_expenses = []
    for item in transactions:
        occurred = item.occurred_at.replace(tzinfo=timezone.utc) if item.occurred_at.tzinfo is None else item.occurred_at
        if item.kind == "expense" and item.status == "posted" and item.bill_id is None and occurred >= cutoff:
            recent_expenses.append(item)
    if recent_expenses:
        oldest = min(
            item.occurred_at.replace(tzinfo=timezone.utc) if item.occurred_at.tzinfo is None else item.occurred_at
            for item in recent_expenses
        )
        observed_days = max(1, min(60, (utcnow() - oldest).days + 1))
        daily_spend = sum((item.amount for item in recent_expenses), Decimal("0")) / Decimal(observed_days)
    else:
        daily_spend = user.monthly_income * Decimal("0.30") / Decimal("30") if user.monthly_income else Decimal("250")

    due_by_date: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    names_by_date: dict[date, list[str]] = defaultdict(list)
    active = [item for item in obligations if item.status in OPEN_OBLIGATION_STATUSES]
    for obligation in active:
        for occurrence in _occurrences(obligation, today, end):
            due_by_date[occurrence] += obligation.amount
            names_by_date[occurrence].append(obligation.name)

    balance = starting_balance
    lowest = starting_balance
    lowest_date = today
    points: list[dict] = []
    for offset in range(days + 1):
        current = today + timedelta(days=offset)
        income = user.monthly_income if current.day == 1 and offset > 0 else Decimal("0")
        required = due_by_date[current]
        discretionary = Decimal("0") if offset == 0 else daily_spend
        balance += income - required - discretionary
        if balance < lowest:
            lowest = balance
            lowest_date = current
        points.append(
            {
                "date": current.isoformat(),
                "projected_balance": money(balance),
                "income": money(income),
                "obligations": money(required),
                "bills": money(required),
                "estimated_spend": money(discretionary),
                "events": names_by_date[current],
            }
        )

    history_factor = min(1.0, len(recent_expenses) / 25)
    obligation_factor = min(1.0, len(active) / 8)
    return {
        "days": days,
        "starting_balance": money(starting_balance),
        "lowest_projected_balance": money(lowest),
        "lowest_balance_date": lowest_date.isoformat(),
        "ending_balance": money(balance),
        "average_daily_spend": money(daily_spend),
        "confidence": round(0.45 + 0.3 * history_factor + 0.15 * obligation_factor, 2),
        "method": "deterministic daily simulation using balances, obligations, stated income and recent non-bill spending",
        "points": points,
    }


def _recommendation_for(
    obligation: Obligation,
    policy: FinancialPolicy,
    forecast: dict,
    accounts: list[FinancialAccount],
) -> dict:
    today = date.today()
    due_date = max(today, obligation.due_date)
    point = next(
        (item for item in forecast["points"] if item["date"] == due_date.isoformat()),
        forecast["points"][-1],
    )
    projected_after = Decimal(str(point["projected_balance"]))
    reserve = policy.minimum_reserve
    days_to_due = (obligation.due_date - today).days
    funded_accounts = sorted(
        [account for account in accounts if account.is_active],
        key=lambda account: account.balance,
        reverse=True,
    )
    account = next(
        (item for item in funded_accounts if item.balance >= obligation.amount),
        funded_accounts[0] if funded_accounts else None,
    )
    safe = bool(account and projected_after >= reserve)
    near_reserve = projected_after < reserve + obligation.amount
    overdue = days_to_due < 0

    if overdue and safe:
        action = "pay_now"
        proposed_date = today
    elif overdue:
        action = "split_or_negotiate"
        proposed_date = today
    elif obligation.essential and days_to_due <= 3 and safe:
        action = "pay_now"
        proposed_date = today
    elif obligation.essential and not safe:
        action = "split_or_negotiate"
        proposed_date = due_date
    elif not safe:
        action = "hold"
        proposed_date = None
    else:
        action = "schedule"
        proposed_date = due_date

    if not safe or overdue:
        risk = "high"
    elif near_reserve or days_to_due <= 3:
        risk = "medium"
    else:
        risk = "low"

    evidence = [
        f"₹{money(obligation.amount):,.0f} due {obligation.due_date.isoformat()}",
        f"projected balance ₹{money(projected_after):,.0f}",
        f"protected reserve ₹{money(reserve):,.0f}",
    ]
    if obligation.essential:
        evidence.append("classified as an essential obligation")
    if not account:
        evidence.append("no active funding account is available")

    summaries = {
        "pay_now": "Pay promptly while preserving the configured reserve.",
        "schedule": "Schedule for the due date; current projection remains within policy.",
        "hold": "Hold this optional expense because the projection would breach the reserve.",
        "split_or_negotiate": "Prepare a split-payment or provider negotiation instead of risking a shortfall.",
    }
    confidence = min(
        Decimal("0.970"),
        max(
            Decimal("0.400"),
            Decimal(str(forecast["confidence"])) * Decimal("0.7") + obligation.confidence * Decimal("0.3"),
        ),
    )
    return {
        "action": action,
        "proposed_date": proposed_date,
        "account_id": account.id if account else None,
        "risk_level": risk,
        "confidence": confidence,
        "rationale": {
            "summary": summaries[action],
            "evidence": evidence,
            "days_to_due": days_to_due,
            "projected_balance_after_obligations": money(projected_after),
            "minimum_reserve": money(reserve),
            "user_authorization_required": True,
        },
        "forecast_snapshot": {
            "generated_for": due_date.isoformat(),
            "projected_balance": money(projected_after),
            "forecast_confidence": forecast["confidence"],
        },
    }


def refresh_recommendations(db: Session, user: User) -> list[Recommendation]:
    sync_obligations_from_bills(db, user)
    policy = get_or_create_policy(db, user)
    obligations = list(
        db.scalars(
            select(Obligation)
            .where(Obligation.user_id == user.id, Obligation.status.in_(RECOMMENDABLE_STATUSES))
            .order_by(Obligation.due_date, Obligation.priority.desc())
        )
    )
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id)))
    forecast = forecast_financial_twin(user, accounts, obligations, transactions, days=90)

    stale = list(
        db.scalars(
            select(Recommendation).where(
                Recommendation.user_id == user.id,
                Recommendation.status == "pending",
            )
        )
    )
    for item in stale:
        item.status = "expired"

    generated: list[Recommendation] = []
    for obligation in obligations:
        decision = _recommendation_for(obligation, policy, forecast, accounts)
        recommendation = Recommendation(
            user_id=user.id,
            obligation_id=obligation.id,
            action=decision["action"],
            proposed_date=decision["proposed_date"],
            proposed_amount=obligation.amount,
            account_id=decision["account_id"],
            risk_level=decision["risk_level"],
            confidence=decision["confidence"],
            rationale=decision["rationale"],
            forecast_snapshot=decision["forecast_snapshot"],
            model_version="financial-ops-rules-v1",
        )
        obligation.next_action = decision["action"]
        db.add(recommendation)
        generated.append(recommendation)
    db.flush()
    return generated


def evaluate_policy(policy: FinancialPolicy, obligation: Obligation, recommendation: Recommendation) -> dict:
    category_allowed = not policy.allowed_categories or obligation.category in policy.allowed_categories
    counterparty_trusted = (
        not policy.trusted_counterparties or obligation.counterparty in policy.trusted_counterparties
    )
    within_amount_limit = recommendation.proposed_amount <= policy.max_preparable_amount
    connected = obligation.provider_connection_id is not None
    can_prepare = policy.autonomy_mode != "advise" and category_allowed and within_amount_limit
    can_request_execution = (
        policy.autonomy_mode == "execute_authorized"
        and can_prepare
        and counterparty_trusted
        and connected
    )
    return {
        "mode": policy.autonomy_mode,
        "category_allowed": category_allowed,
        "counterparty_trusted": counterparty_trusted,
        "within_amount_limit": within_amount_limit,
        "provider_connected": connected,
        "can_prepare": can_prepare,
        "can_request_execution": can_request_execution,
        "requires_explicit_user_approval": True,
        "requires_external_authorization": True,
        "reason": (
            "Eligible for authorized-partner handoff."
            if can_request_execution
            else "Prepared guidance only; a user and authorized provider must complete execution."
        ),
    }


def approve_recommendation(
    db: Session,
    user: User,
    recommendation: Recommendation,
    idempotency_key: str,
    note: str | None = None,
) -> ActionRequest:
    existing = db.scalar(
        select(ActionRequest).where(
            ActionRequest.user_id == user.id,
            ActionRequest.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    obligation = db.scalar(
        select(Obligation).where(
            Obligation.id == recommendation.obligation_id,
            Obligation.user_id == user.id,
        )
    )
    if not obligation:
        raise ValueError("Obligation not found")
    policy = get_or_create_policy(db, user)
    evaluation = evaluate_policy(policy, obligation, recommendation)
    if evaluation["can_request_execution"]:
        request_status = "awaiting_partner_authorization"
    elif evaluation["can_prepare"]:
        request_status = "ready_for_handoff"
    elif policy.autonomy_mode == "advise":
        request_status = "approved_advice"
    else:
        request_status = "policy_blocked"
    action = ActionRequest(
        user_id=user.id,
        recommendation_id=recommendation.id,
        obligation_id=obligation.id,
        action_type=recommendation.action,
        idempotency_key=idempotency_key,
        status=request_status,
        payload={
            "amount": money(recommendation.proposed_amount),
            "date": recommendation.proposed_date.isoformat() if recommendation.proposed_date else None,
            "account_id": recommendation.account_id,
            "note": note,
        },
        policy_evaluation=evaluation,
        approved_at=utcnow(),
    )
    recommendation.status = "approved"
    recommendation.decided_at = utcnow()
    obligation.status = "approved" if request_status != "policy_blocked" else obligation.status
    db.add(action)
    db.flush()
    return action


def simulate_scenario(
    db: Session,
    user: User,
    name: str,
    amount: Decimal,
    due_date: date,
    category: str,
    essential: bool,
    recurring_monthly: bool,
) -> Scenario:
    sync_obligations_from_bills(db, user)
    obligations = list(
        db.scalars(
            select(Obligation).where(
                Obligation.user_id == user.id,
                Obligation.status.in_(OPEN_OBLIGATION_STATUSES),
            )
        )
    )
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id)))
    policy = get_or_create_policy(db, user)
    baseline = forecast_financial_twin(user, accounts, obligations, transactions, days=90)
    effective_due = max(date.today(), due_date)
    occurrences = [effective_due]
    if recurring_monthly:
        current = _add_months(effective_due, 1)
        horizon = date.today() + timedelta(days=90)
        while current <= horizon:
            occurrences.append(current)
            current = _add_months(current, 1)
    adjusted_points = []
    for point in baseline["points"]:
        point_date = date.fromisoformat(point["date"])
        deductions = sum((amount for occurrence in occurrences if occurrence <= point_date), Decimal("0"))
        adjusted = dict(point)
        adjusted["projected_balance"] = money(Decimal(str(point["projected_balance"])) - deductions)
        adjusted_points.append(adjusted)
    projected_low = min(
        (Decimal(str(item["projected_balance"])) for item in adjusted_points),
        default=Decimal("0"),
    )
    reserve_breach = projected_low < policy.minimum_reserve
    result = {
        "baseline_lowest_balance": baseline["lowest_projected_balance"],
        "projected_lowest_balance": money(projected_low),
        "cash_impact": money(amount * len(occurrences)),
        "occurrences": [item.isoformat() for item in occurrences],
        "minimum_reserve": money(policy.minimum_reserve),
        "reserve_breach": reserve_breach,
        "decision": "wait_or_reduce" if reserve_breach and not essential else "review_plan" if reserve_breach else "affordable",
        "explanation": (
            "This scenario breaches the protected reserve; reduce, postpone or split it."
            if reserve_breach
            else "The scenario remains above the protected reserve in the 90-day projection."
        ),
        "points": adjusted_points,
    }
    scenario = Scenario(
        user_id=user.id,
        name=name,
        assumptions={
            "amount": money(amount),
            "due_date": due_date.isoformat(),
            "category": category,
            "essential": essential,
            "recurring_monthly": recurring_monthly,
        },
        result=result,
    )
    db.add(scenario)
    db.flush()
    return scenario


def record_outcome(
    db: Session,
    user: User,
    obligation: Obligation,
    *,
    action_request_id: int | None,
    event_type: str,
    source: str,
    status: str,
    provider_reference: str | None,
    expected_status: str | None,
    actual_status: str | None,
    evidence: dict,
) -> tuple[OutcomeEvent, ExceptionCase | None]:
    combined_evidence = {
        **evidence,
        "expected_status": expected_status,
        "actual_status": actual_status,
    }
    event = OutcomeEvent(
        user_id=user.id,
        obligation_id=obligation.id,
        action_request_id=action_request_id,
        event_type=event_type,
        source=source,
        status=status,
        provider_reference=provider_reference,
        evidence=combined_evidence,
    )
    db.add(event)
    db.flush()

    mismatch = status in {"mismatch", "failed"} or (
        expected_status is not None and actual_status is not None and expected_status != actual_status
    )
    case = None
    if mismatch:
        case = ExceptionCase(
            user_id=user.id,
            obligation_id=obligation.id,
            outcome_event_id=event.id,
            case_type="provider_outcome_mismatch",
            severity="high" if status == "failed" else "medium",
            summary=(
                f"Expected provider status '{expected_status or 'confirmed'}' but received "
                f"'{actual_status or status}'. No successful provider update is assumed."
            ),
            evidence=combined_evidence,
        )
        db.add(case)
        obligation.status = "disputed"
    elif status in {"confirmed", "verified"}:
        obligation.status = "verified"
        obligation.next_action = None
    db.flush()
    return event, case


def command_center(db: Session, user: User) -> dict:
    policy = get_or_create_policy(db, user)
    sync_obligations_from_bills(db, user)
    obligations = list(
        db.scalars(
            select(Obligation)
            .where(Obligation.user_id == user.id)
            .order_by(Obligation.due_date, Obligation.id)
        )
    )
    accounts = list(db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id)))
    transactions = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id)))
    recommendations = list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.user_id == user.id, Recommendation.status == "pending")
            .order_by(Recommendation.created_at.desc())
        )
    )
    exceptions = list(
        db.scalars(
            select(ExceptionCase)
            .where(ExceptionCase.user_id == user.id, ExceptionCase.status == "open")
            .order_by(ExceptionCase.created_at.desc())
        )
    )
    actions = list(
        db.scalars(
            select(ActionRequest)
            .where(ActionRequest.user_id == user.id)
            .order_by(ActionRequest.created_at.desc())
            .limit(25)
        )
    )
    active = [item for item in obligations if item.status in OPEN_OBLIGATION_STATUSES]
    forecast = forecast_financial_twin(user, accounts, active, transactions, days=90)
    categories: dict[str, dict] = {}
    for item in active:
        bucket = categories.setdefault(item.category, {"category": item.category, "count": 0, "total": 0.0})
        bucket["count"] += 1
        bucket["total"] = round(bucket["total"] + money(item.amount), 2)
    return {
        "generated_at": utcnow().isoformat(),
        "policy": policy,
        "summary": {
            "active_obligations": len(active),
            "due_within_7_days": len(
                [item for item in active if item.due_date <= date.today() + timedelta(days=7)]
            ),
            "pending_decisions": len(recommendations),
            "open_exceptions": len(exceptions),
            "projected_lowest_balance": forecast["lowest_projected_balance"],
            "minimum_reserve": money(policy.minimum_reserve),
            "reserve_at_risk": forecast["lowest_projected_balance"] < money(policy.minimum_reserve),
        },
        "forecast": forecast,
        "obligations": obligations,
        "recommendations": recommendations,
        "exceptions": exceptions,
        "actions": actions,
        "categories": sorted(categories.values(), key=lambda item: item["total"], reverse=True),
        "execution_boundary": (
            "BillFlow can advise and prepare an authorized handoff. It never treats a payment or "
            "provider update as complete until an authorized rail returns outcome evidence."
        ),
    }


def new_consent_reference() -> str:
    return f"consent_{uuid4().hex}"
