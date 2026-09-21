"""Subscription marketplace and explainable affordability guidance.

The catalog uses fictional sandbox providers. Recommendations are advisory: an
intent creates a bill, while the existing payment flow still requires explicit
provider/user authorization before any subscription is activated.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models import Bill, FinancialAccount, MarketplaceInteraction, ProviderConnection, Transaction, User
from app.services.safepay import forecast_cashflow, money


MARKETPLACE_APPS: dict[str, dict] = {
    "streamplus": {
        "slug": "streamplus",
        "name": "StreamPlus",
        "category": "entertainment",
        "tagline": "Movies, series and live premieres",
        "description": "A fictional video-streaming sandbox used to demonstrate plan comparison and provider activation.",
        "accent": "violet",
        "plans": [
            {
                "id": "mobile",
                "name": "Mobile",
                "price": Decimal("149.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 7,
                "features": ["Full catalog", "Standard definition", "Offline downloads"],
                "limits": {"simultaneous_streams": 1, "video_quality": "SD", "offline_devices": 1},
                "cancellation": "Cancel any time; access continues to the end of the billing period.",
                "refund_policy": "No partial-period refund after the trial converts.",
                "auto_renews": True,
            },
            {
                "id": "standard",
                "name": "Standard",
                "price": Decimal("499.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 7,
                "features": ["Full catalog", "Full HD", "Offline downloads", "Household profiles"],
                "limits": {"simultaneous_streams": 2, "video_quality": "Full HD", "offline_devices": 2},
                "cancellation": "Cancel any time; access continues to the end of the billing period.",
                "refund_policy": "No partial-period refund after the trial converts.",
                "auto_renews": True,
            },
            {
                "id": "premium",
                "name": "Premium",
                "price": Decimal("799.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 7,
                "features": ["Full catalog", "4K + HDR", "Spatial audio", "Family profiles", "Offline downloads"],
                "limits": {"simultaneous_streams": 4, "video_quality": "4K + HDR", "offline_devices": 6},
                "cancellation": "Cancel any time; access continues to the end of the billing period.",
                "refund_policy": "No partial-period refund after the trial converts.",
                "auto_renews": True,
            },
        ],
    },
    "musicwave": {
        "slug": "musicwave",
        "name": "MusicWave",
        "category": "entertainment",
        "tagline": "Ad-free music and podcasts",
        "description": "A fictional audio-membership sandbox with individual and family access plans.",
        "accent": "rose",
        "plans": [
            {
                "id": "individual",
                "name": "Individual",
                "price": Decimal("119.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 30,
                "features": ["Ad-free listening", "Offline downloads", "High-quality audio"],
                "limits": {"members": 1, "offline_devices": 5, "audio_quality": "High"},
                "cancellation": "Cancel before renewal to avoid the next charge.",
                "refund_policy": "Unused time is not refunded after renewal.",
                "auto_renews": True,
            },
            {
                "id": "family",
                "name": "Family",
                "price": Decimal("179.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 30,
                "features": ["Ad-free listening", "Offline downloads", "Separate libraries", "Kids mode"],
                "limits": {"members": 6, "offline_devices": 30, "audio_quality": "High"},
                "cancellation": "Cancel before renewal to avoid the next charge.",
                "refund_policy": "Unused time is not refunded after renewal.",
                "auto_renews": True,
            },
        ],
    },
    "cloudbox": {
        "slug": "cloudbox",
        "name": "CloudBox",
        "category": "productivity",
        "tagline": "Private backup across your devices",
        "description": "A fictional cloud-storage sandbox for testing storage entitlements and recurring billing.",
        "accent": "blue",
        "plans": [
            {
                "id": "storage-100",
                "name": "100 GB",
                "price": Decimal("130.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 14,
                "features": ["Automatic photo backup", "File version history", "Secure sharing"],
                "limits": {"storage": "100 GB", "members": 1, "version_history": "30 days"},
                "cancellation": "Downgrade any time; excess files become read-only after the billing period.",
                "refund_policy": "No prorated refund for a monthly downgrade.",
                "auto_renews": True,
            },
            {
                "id": "storage-2tb",
                "name": "2 TB Family",
                "price": Decimal("650.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 14,
                "features": ["Automatic backup", "Advanced sharing", "Ransomware recovery", "Family storage"],
                "limits": {"storage": "2 TB", "members": 6, "version_history": "180 days"},
                "cancellation": "Downgrade any time; excess files become read-only after the billing period.",
                "refund_policy": "No prorated refund for a monthly downgrade.",
                "auto_renews": True,
            },
        ],
    },
    "fitpulse": {
        "slug": "fitpulse",
        "name": "FitPulse",
        "category": "wellness",
        "tagline": "Guided workouts and habit coaching",
        "description": "A fictional general-wellness membership; it does not provide medical diagnosis or treatment advice.",
        "accent": "emerald",
        "plans": [
            {
                "id": "basic",
                "name": "Basic",
                "price": Decimal("499.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 14,
                "features": ["Workout library", "Habit tracking", "Weekly progress summary"],
                "limits": {"profiles": 1, "live_classes_per_month": 0, "downloaded_sessions": 10},
                "cancellation": "Cancel any time from membership settings.",
                "refund_policy": "No refund for a partially used month.",
                "auto_renews": True,
            },
            {
                "id": "pro",
                "name": "Pro",
                "price": Decimal("999.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 14,
                "features": ["Workout library", "Live classes", "Adaptive routines", "Advanced progress trends"],
                "limits": {"profiles": 4, "live_classes_per_month": "Unlimited", "downloaded_sessions": "Unlimited"},
                "cancellation": "Cancel any time from membership settings.",
                "refund_policy": "No refund for a partially used month.",
                "auto_renews": True,
            },
        ],
    },
    "learnpro": {
        "slug": "learnpro",
        "name": "LearnPro",
        "category": "education",
        "tagline": "Career courses and guided projects",
        "description": "A fictional learning-platform sandbox with monthly and annual access options.",
        "accent": "amber",
        "plans": [
            {
                "id": "monthly",
                "name": "Monthly Access",
                "price": Decimal("699.00"),
                "currency": "INR",
                "billing_cycle": "monthly",
                "trial_days": 7,
                "features": ["Complete course library", "Guided projects", "Completion certificates"],
                "limits": {"active_courses": 10, "project_reviews_per_month": 2, "members": 1},
                "cancellation": "Cancel before the next monthly renewal.",
                "refund_policy": "No refund after a certificate is issued in the current period.",
                "auto_renews": True,
            },
            {
                "id": "annual",
                "name": "Annual Access",
                "price": Decimal("4999.00"),
                "currency": "INR",
                "billing_cycle": "yearly",
                "trial_days": 7,
                "features": ["Complete course library", "Guided projects", "Priority reviews", "Completion certificates"],
                "limits": {"active_courses": "Unlimited", "project_reviews_per_month": 5, "members": 1},
                "cancellation": "Cancel renewal at any time; access continues through the paid year.",
                "refund_policy": "Refund review is available within 7 days of the first annual charge.",
                "auto_renews": True,
            },
        ],
    },
}


def app_for(slug: str) -> dict:
    app = MARKETPLACE_APPS.get(slug)
    if not app:
        raise ValueError("Marketplace application not found")
    return app


def plan_for(app_slug: str, plan_id: str) -> tuple[dict, dict]:
    app = app_for(app_slug)
    plan = next((item for item in app["plans"] if item["id"] == plan_id), None)
    if not plan:
        raise ValueError("Subscription plan not found")
    return app, plan


def public_plan(plan: dict) -> dict:
    return {**plan, "price": money(plan["price"]), "monthly_equivalent": money(monthly_equivalent(plan))}


def monthly_equivalent(plan: dict) -> Decimal:
    price = Decimal(str(plan["price"]))
    return {
        "weekly": price * Decimal("52") / Decimal("12"),
        "monthly": price,
        "quarterly": price / Decimal("3"),
        "yearly": price / Decimal("12"),
    }.get(plan["billing_cycle"], price)


def app_state(app_slug: str, connections: list[ProviderConnection]) -> dict:
    connection = next((item for item in connections if item.provider_slug == app_slug), None)
    state = connection.provider_state if connection else {}
    return {
        "connected": connection is not None,
        "connection_id": connection.id if connection else None,
        "subscription_status": state.get("subscription_status", "not_subscribed"),
        "active_plan": state.get("plan"),
        "active_plan_id": state.get("plan_id"),
        "valid_until": state.get("valid_until"),
        "pending_plan": state.get("pending_plan"),
    }


def _preference_signal(app: dict, plan: dict, interactions: list[MarketplaceInteraction]) -> tuple[float, list[str]]:
    action_weight = {
        "viewed": 0.02,
        "shortlisted": 0.12,
        "dismissed": -0.18,
        "subscribe_intent": 0.10,
        "subscribed": 0.15,
        "cancelled": -0.25,
    }
    signal = 0.0
    evidence: list[str] = []
    for item in interactions:
        candidate = MARKETPLACE_APPS.get(item.app_slug)
        if not candidate:
            continue
        weight = action_weight.get(item.action, 0)
        if item.app_slug == app["slug"]:
            signal += weight if item.plan_id in {None, plan["id"]} else weight * 0.35
        elif candidate["category"] == app["category"]:
            signal += weight * 0.25
    matching = [item for item in interactions if item.app_slug == app["slug"]]
    if any(item.action == "shortlisted" and item.plan_id == plan["id"] for item in matching):
        evidence.append("You previously shortlisted this plan.")
    if any(item.action == "dismissed" and item.plan_id == plan["id"] for item in matching):
        evidence.append("You previously dismissed this plan, so preference fit is reduced.")
    if matching and not evidence:
        evidence.append("Your recent browsing history contributes a small preference signal.")
    return max(-0.25, min(0.25, signal)), evidence


def recommend_plan(
    user: User,
    app: dict,
    plan: dict,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
    interactions: list[MarketplaceInteraction],
    connections: list[ProviderConnection],
) -> dict:
    today = date.today()
    price = Decimal(str(plan["price"]))
    monthly_cost = monthly_equivalent(plan)
    reserve = Decimal(str(user.minimum_balance))
    total_balance = sum((item.balance for item in accounts if item.is_active), Decimal("0"))
    forecast = forecast_cashflow(user, accounts, bills, transactions, days=45)
    overdue_total = sum(
        (
            item.amount
            for item in bills
            if item.status in {"due", "overdue", "scheduled"} and item.due_date < today
        ),
        Decimal("0"),
    )
    # The general forecast starts at today, so conservatively reserve overdue
    # obligations here instead of letting an old deadline disappear from view.
    base_lowest = Decimal(str(forecast["lowest_projected_balance"])) - overdue_total
    obligation_id = f"MARKET-{app['slug']}-{plan['id']}-{user.id}"
    pending_bill = next(
        (
            item
            for item in bills
            if item.external_obligation_id == obligation_id and item.status in {"due", "overdue", "scheduled"}
        ),
        None,
    )
    incremental_price = Decimal("0") if pending_bill else price
    projected_lowest = base_lowest - incremental_price
    income = Decimal(str(user.monthly_income))
    income_share = (monthly_cost / income * Decimal("100")) if income > 0 else None
    unpaid = [item for item in bills if item.status in {"due", "overdue", "scheduled"}]
    upcoming_30 = [item for item in unpaid if item.due_date <= today + timedelta(days=30)]
    upcoming_total = sum((item.amount for item in upcoming_30), Decimal("0"))
    conflicts = sorted(
        [item for item in unpaid if item.due_date <= today + timedelta(days=14) and item.id != getattr(pending_bill, "id", None)],
        key=lambda item: item.due_date,
    )[:5]
    active_connections = [
        item
        for item in connections
        if (item.provider_state or {}).get("subscription_status") == "active"
    ]
    same_connection = next((item for item in active_connections if item.provider_slug == app["slug"]), None)
    same_plan_active = bool(
        same_connection
        and (
            (same_connection.provider_state or {}).get("plan_id") == plan["id"]
            or (same_connection.provider_state or {}).get("plan") in {plan["name"], f"{app['name']} {plan['name']}"}
        )
    )
    category_subscriptions = [item for item in active_connections if item.category == app["category"]]
    preference, preference_reasons = _preference_signal(app, plan, interactions)

    score = 62.0
    if projected_lowest >= reserve * Decimal("1.5"):
        score += 18
    elif projected_lowest >= reserve:
        score += 8
    elif projected_lowest >= 0:
        score -= 25
    else:
        score -= 55
    if income_share is None:
        score -= 10
    elif income_share <= 2:
        score += 10
    elif income_share <= 5:
        score += 4
    elif income_share > 10:
        score -= 18
    if conflicts and projected_lowest < reserve * Decimal("1.25"):
        score -= 10
    score -= min(20, len(category_subscriptions) * 8)
    score += preference * 60
    if same_plan_active:
        score = min(score, 12)
    score = round(max(0, min(100, score)))

    if same_plan_active:
        decision = "not_recommended"
    elif projected_lowest < 0 or (income_share is not None and income_share > 15 and projected_lowest < reserve):
        decision = "not_recommended"
    elif projected_lowest < reserve or (conflicts and projected_lowest < reserve * Decimal("1.25")):
        decision = "wait"
    elif score >= 65:
        decision = "subscribe"
    elif score < 35:
        decision = "not_recommended"
    else:
        decision = "wait"

    reasons: list[str] = []
    risks: list[str] = []
    if same_plan_active:
        reasons.append("This plan already appears active in the connected provider account.")
    elif projected_lowest >= reserve:
        reasons.append(
            f"The 45-day forecast stays about ₹{money(projected_lowest):,.0f}, above your ₹{money(reserve):,.0f} reserve."
        )
    elif projected_lowest >= 0:
        reasons.append(
            f"The plan would leave the forecast about ₹{money(reserve - projected_lowest):,.0f} below your reserve."
        )
        risks.append("Buying now would cross the safety reserve you configured.")
    else:
        reasons.append("The 45-day cash-flow forecast turns negative after this purchase.")
        risks.append("A negative projection raises the risk of a missed bill or failed payment.")
    if income_share is not None:
        reasons.append(f"Its monthly-equivalent cost is {float(income_share):.1f}% of stated monthly income.")
    else:
        risks.append("No monthly income is recorded, so affordability confidence is lower.")
    if conflicts:
        reasons.append(f"{len(conflicts)} bill deadline{'s' if len(conflicts) != 1 else ''} fall within the next 14 days.")
    if overdue_total:
        risks.append(f"₹{money(overdue_total):,.0f} of overdue obligations is reserved before this plan is assessed.")
    if category_subscriptions:
        risks.append(
            f"You already have {len(category_subscriptions)} active {app['category']} subscription"
            f"{'s' if len(category_subscriptions) != 1 else ''}; check for overlapping value."
        )
    reasons.extend(preference_reasons)
    if pending_bill:
        reasons.insert(0, f"A payment-ready bill for this plan already exists as bill #{pending_bill.id}.")

    data_points = min(1.0, (len(transactions) / 20) * 0.4 + (len(bills) / 8) * 0.35 + (len(interactions) / 8) * 0.15 + (0.1 if accounts else 0))
    return {
        "decision": decision,
        "decision_label": {"subscribe": "Subscribe", "wait": "Wait", "not_recommended": "Do not subscribe"}[decision],
        "score": score,
        "confidence": round(0.48 + 0.44 * data_points, 2),
        "projected_lowest_balance": money(projected_lowest),
        "minimum_reserve": money(reserve),
        "reserve_after_plan": money(projected_lowest - reserve),
        "monthly_income_share_percent": round(float(income_share), 2) if income_share is not None else None,
        "existing_category_subscriptions": len(category_subscriptions),
        "preference_signal": round(preference, 2),
        "pending_bill_id": pending_bill.id if pending_bill else None,
        "reasons": reasons[:5],
        "risks": risks[:4],
        "conflicting_deadlines": [
            {
                "bill_id": item.id,
                "name": item.name,
                "amount": money(item.amount),
                "due_date": item.due_date.isoformat(),
                "days_until_due": (item.due_date - today).days,
            }
            for item in conflicts
        ],
        "financial_snapshot": {
            "available_balance": money(total_balance),
            "upcoming_30_day_obligations": money(upcoming_total),
            "base_45_day_low": money(base_lowest),
            "plan_charge": money(price),
            "monthly_equivalent": money(monthly_cost),
        },
        "explanation": "Affordability is evaluated before preference. Browsing history can adjust fit, but can never override a failed balance or reserve check.",
        "disclaimer": "Personalized budgeting guidance, not financial advice. You make the final subscription and payment decision.",
    }


def marketplace_app_detail(
    user: User,
    app_slug: str,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
    interactions: list[MarketplaceInteraction],
    connections: list[ProviderConnection],
) -> dict:
    app = app_for(app_slug)
    plans = []
    for plan in app["plans"]:
        plans.append(
            {
                **public_plan(plan),
                "recommendation": recommend_plan(
                    user, app, plan, accounts, bills, transactions, interactions, connections
                ),
            }
        )
    order = {"subscribe": 2, "wait": 1, "not_recommended": 0}
    best = max(plans, key=lambda item: (order[item["recommendation"]["decision"]], item["recommendation"]["score"], -item["price"]))
    return {
        **{key: value for key, value in app.items() if key != "plans"},
        "sandbox": True,
        "provider_notice": "Plan data and activation are sandbox demonstrations. Real availability requires the provider's official API and commercial agreement.",
        "state": app_state(app_slug, connections),
        "recommended_plan_id": best["id"],
        "plans": plans,
    }


def marketplace_overview(
    user: User,
    accounts: list[FinancialAccount],
    bills: list[Bill],
    transactions: list[Transaction],
    interactions: list[MarketplaceInteraction],
    connections: list[ProviderConnection],
) -> dict:
    items = []
    for app in MARKETPLACE_APPS.values():
        recommendations = [
            recommend_plan(user, app, plan, accounts, bills, transactions, interactions, connections)
            for plan in app["plans"]
        ]
        priority = {"subscribe": 2, "wait": 1, "not_recommended": 0}
        best_index = max(range(len(recommendations)), key=lambda index: (priority[recommendations[index]["decision"]], recommendations[index]["score"], -app["plans"][index]["price"]))
        best_plan = app["plans"][best_index]
        items.append(
            {
                **{key: value for key, value in app.items() if key != "plans"},
                "sandbox": True,
                "plan_count": len(app["plans"]),
                "starting_price": money(min(plan["price"] for plan in app["plans"])),
                "state": app_state(app["slug"], connections),
                "best_match": {
                    "plan_id": best_plan["id"],
                    "plan_name": best_plan["name"],
                    **recommendations[best_index],
                },
            }
        )
    return {
        "items": items,
        "method": "Plans are ranked using forecast liquidity, reserve protection, bill deadlines, recurring-subscription load and interaction history.",
        "safety_rule": "Preference history never overrides affordability, and no subscription is activated until the user authorizes payment.",
    }
