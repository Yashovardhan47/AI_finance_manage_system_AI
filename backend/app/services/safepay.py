"""Explainable finance intelligence used by BillFlow AI.

SafePay is intentionally advisory. It forecasts liquidity and proposes a payment
plan, while a separate payment provider requires explicit user authorization.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median

from app.models import Bill, FinancialAccount, Transaction, User


def money(value: Decimal | float | int) -> float:
    return round(float(value), 2)


def _expense_history(transactions: list[Transaction], days: int = 60) -> list[Transaction]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [
        item
        for item in transactions
        if item.kind == "expense"
        and item.status == "posted"
        and (item.occurred_at.replace(tzinfo=timezone.utc) if item.occurred_at.tzinfo is None else item.occurred_at) >= cutoff
        and item.bill_id is None
    ]


def forecast_cashflow(
    user: User,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
    days: int = 30,
) -> dict:
    days = max(7, min(days, 90))
    today = date.today()
    starting_balance = sum((account.balance for account in accounts if account.is_active), Decimal("0"))
    expense_history = _expense_history(transactions)
    if expense_history:
        oldest = min(t.occurred_at for t in expense_history)
        oldest = oldest.replace(tzinfo=timezone.utc) if oldest.tzinfo is None else oldest
        observed_days = max(1, min(60, (datetime.now(timezone.utc) - oldest).days + 1))
        daily_spend = sum((item.amount for item in expense_history), Decimal("0")) / Decimal(observed_days)
    else:
        daily_spend = (user.monthly_income * Decimal("0.30") / Decimal("30")) if user.monthly_income else Decimal("250")

    due_by_date: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for bill in bills:
        if bill.status in {"due", "overdue", "scheduled"} and today <= bill.due_date <= today + timedelta(days=days):
            due_by_date[bill.due_date] += bill.amount

    balance = starting_balance
    points: list[dict] = []
    lowest = balance
    for offset in range(days + 1):
        current = today + timedelta(days=offset)
        income = user.monthly_income if current.day == 1 and offset > 0 else Decimal("0")
        obligations = due_by_date[current]
        discretionary = Decimal("0") if offset == 0 else daily_spend
        balance += income - obligations - discretionary
        lowest = min(lowest, balance)
        points.append(
            {
                "date": current.isoformat(),
                "projected_balance": money(balance),
                "income": money(income),
                "bills": money(obligations),
                "estimated_spend": money(discretionary),
            }
        )

    history_factor = min(1.0, len(expense_history) / 25)
    return {
        "days": days,
        "starting_balance": money(starting_balance),
        "lowest_projected_balance": money(lowest),
        "average_daily_spend": money(daily_spend),
        "confidence": round(0.45 + 0.45 * history_factor, 2),
        "method": "cash-balance simulation using upcoming obligations, stated income and recent discretionary spending",
        "points": points,
    }


def detect_anomalies(transactions: list[Transaction]) -> list[dict]:
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for item in transactions:
        if item.kind == "expense" and item.status == "posted":
            groups[item.category].append(item)

    anomalies: list[dict] = []
    for category, items in groups.items():
        if len(items) < 4:
            continue
        values = [float(item.amount) for item in items]
        center = median(values)
        deviation = median([abs(value - center) for value in values]) or max(center * 0.1, 1)
        for item, value in zip(items, values, strict=True):
            robust_z = 0.6745 * (value - center) / deviation
            if robust_z > 3.5 and value > center * 1.5:
                anomalies.append(
                    {
                        "transaction_id": item.id,
                        "merchant": item.merchant,
                        "category": category,
                        "amount": round(value, 2),
                        "category_median": round(center, 2),
                        "severity": "high" if robust_z > 6 else "medium",
                        "confidence": round(min(0.99, 0.55 + robust_z / 20), 2),
                        "explanation": f"This is {value / max(center, 0.01):.1f}× the typical {category} transaction.",
                    }
                )
    return sorted(anomalies, key=lambda item: item["confidence"], reverse=True)


def financial_health(
    user: User,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
) -> dict:
    available = sum((account.balance for account in accounts if account.is_active), Decimal("0"))
    today = date.today()
    due_30 = sum(
        (bill.amount for bill in bills if bill.status in {"due", "overdue", "scheduled"} and bill.due_date <= today + timedelta(days=30)),
        Decimal("0"),
    )
    minimum = max(user.minimum_balance, Decimal("1"))
    income = max(user.monthly_income, Decimal("1"))
    liquidity = min(100, money((available / max(due_30, Decimal("1"))) * 35))
    reserve = min(100, money((available / minimum) * 35))
    obligation = max(0, 100 - money((due_30 / income) * 100))
    paid = len([bill for bill in bills if bill.status == "paid"])
    late = len([bill for bill in bills if bill.status == "overdue"])
    reliability = 100 if paid + late == 0 else round(100 * paid / (paid + late), 2)
    score = round(0.30 * liquidity + 0.25 * reserve + 0.25 * obligation + 0.20 * reliability)
    score = max(0, min(100, score))
    if score >= 80:
        label = "Strong"
    elif score >= 60:
        label = "Stable"
    elif score >= 40:
        label = "Watch"
    else:
        label = "At risk"
    return {
        "score": score,
        "label": label,
        "components": {
            "liquidity": round(liquidity),
            "reserve_buffer": round(reserve),
            "obligation_load": round(obligation),
            "payment_reliability": round(reliability),
        },
        "available_balance": money(available),
        "upcoming_30_day_obligations": money(due_30),
        "explanation": "The score combines liquidity, emergency reserve, bill pressure and payment history. It is guidance, not financial advice.",
    }


def build_safe_pay_plan(
    user: User,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
) -> dict:
    active_accounts = [account for account in accounts if account.is_active]
    pending_bills = sorted(
        [bill for bill in bills if bill.status in {"due", "overdue", "scheduled"}],
        key=lambda bill: bill.due_date,
    )
    forecast = forecast_cashflow(user, accounts, pending_bills, transactions, days=45)
    projected = {date.fromisoformat(point["date"]): Decimal(str(point["projected_balance"])) for point in forecast["points"]}
    today = date.today()
    reserve = user.minimum_balance
    remaining = {account.id: account.balance for account in active_accounts}
    plan: list[dict] = []

    for bill in pending_bills:
        deadline = max(today, bill.due_date)
        candidate_days = [day for day in projected if today <= day <= deadline]
        safe_days = [day for day in candidate_days if projected[day] - bill.amount >= reserve]
        recommended_date = max(safe_days) if safe_days else deadline
        viable = [account for account in active_accounts if remaining[account.id] >= bill.amount]
        viable.sort(
            key=lambda account: (
                remaining[account.id] - bill.amount >= reserve,
                account.reward_rate,
                remaining[account.id] - bill.amount,
            ),
            reverse=True,
        )
        chosen = viable[0] if viable else (max(active_accounts, key=lambda account: account.balance) if active_accounts else None)
        projected_total = projected.get(recommended_date, Decimal("0"))
        safe = bool(chosen and remaining[chosen.id] >= bill.amount and projected_total - bill.amount >= reserve)
        if chosen and remaining[chosen.id] >= bill.amount:
            remaining[chosen.id] -= bill.amount

        reasons = []
        if recommended_date < bill.due_date:
            reasons.append("scheduled before the due date")
        if chosen and chosen.reward_rate > 0:
            reasons.append(f"{money(chosen.reward_rate)}% configured reward rate")
        if safe:
            reasons.append(f"keeps the projected reserve near or above ₹{money(reserve):,.0f}")
        else:
            reasons.append("projected funds may fall below your safety reserve; review before paying")

        plan.append(
            {
                "bill_id": bill.id,
                "bill": bill.name,
                "category": bill.category,
                "amount": money(bill.amount),
                "due_date": bill.due_date.isoformat(),
                "recommended_date": recommended_date.isoformat(),
                "account_id": chosen.id if chosen else None,
                "account": chosen.name if chosen else "No funded account",
                "status": "safe_to_schedule" if safe else "needs_attention",
                "confidence": round(min(0.95, forecast["confidence"] + (0.08 if safe else -0.12)), 2),
                "explanation": "; ".join(reasons).capitalize() + ".",
                "requires_user_authorization": True,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "minimum_balance": money(reserve),
            "never_pay_without_confirmation": True,
            "objective": "avoid late fees and liquidity shortfalls, then prefer configured rewards",
        },
        "items": plan,
        "safe_count": len([item for item in plan if item["status"] == "safe_to_schedule"]),
        "attention_count": len([item for item in plan if item["status"] == "needs_attention"]),
    }
