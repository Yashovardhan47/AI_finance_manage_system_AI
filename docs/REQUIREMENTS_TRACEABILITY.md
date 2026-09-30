# Weekly Requirements Traceability

This matrix maps every bullet in the supplied 8-week specification to working code and verification evidence.

## Weeks 1–2 — Plans, customers, and billing cycle

| Requirement | Implementation | Verification |
|---|---|---|
| PostgreSQL schema for plans, customers, subscriptions, cycles, invoices, payments, and audit with enum status | `app/billing_models.py`; Alembic initial migration; named enum types, indexes, constraints, ownership FKs | Clean `alembic upgrade head`; backend model/integration suite |
| Valid trial → active → past_due → cancelled and trial → cancelled state machine with timestamps | `services/subscription_state.py`; additional safe pause/recovery transitions | Lifecycle, retry recovery/exhaustion, and cancellation tests |
| Create/update/archive plans with price, interval, entitlements, and trial | `/billing/plans` endpoints and Billing Operations catalog forms | Plan creation E2E and API tests |
| Create trial, change plan, pause, resume, immediate/end-cycle cancel | `/billing/subscriptions` endpoints; `services/subscriptions.py` | Lifecycle, proration, scheduled change/cancel, refund tests |
| Celery Beat renewal scheduler at correct dates | `celery_app.py`, `tasks.py`, idempotent due-cycle engine | Due-date/as-of cycle integration tests |

## Weeks 3–4 — Invoicing, proration, and webhooks

| Requirement | Implementation | Verification |
|---|---|---|
| Mid-cycle unused-plan credit and new-plan remainder debit | `proration_quote` and `create_proration_invoice` | Immediate plan-change test validates both line types |
| Cycle invoices with plan, proration, usage, tax, and unique number | `services/invoicing.py`; tenant/month counter; usage idempotency | Usage/tax/invoice test and uniqueness constraints |
| Configurable mock success/failure and webhook sender | `/mock-gateway/charge`; success-rate setting; signed internal delivery payload | Failure/retry and successful recovery tests |
| Webhook handler updates invoice/subscription and notifies | HMAC handler, replay table, durable notification outbox | Tamper rejection, accepted event, replay idempotency, notification assertions |
| Unused-period cancellation refunds with invoice line | `unused_period_refund_amount`, `issue_refund`, immediate cancel path | Cancellation/refund integration test |

## Weeks 5–6 — Recovery, tax, PDF, and dashboard

| Requirement | Implementation | Verification |
|---|---|---|
| Configurable day 1/3/7 retries; past due after first failure; cancellation after exhaustion | `PAYMENT_RETRY_SCHEDULE_DAYS`; retry service and Celery task | Exact three-attempt, success-recovery, and exhaustion tests |
| Country/region tax rates, tax invoice lines, and summaries | `services/billing_tax.py`; tax CRUD and summary APIs | Tax invoice and dashboard/tax summary tests |
| Branded ReportLab PDF with items, tax, terms, and reference, stored for download | Embedded-font `services/billing_pdf.py`; persisted bytes/hash/time | PDF API test plus A4 visual render inspection |
| React admin dashboard: MRR, churn, conversion with Recharts; invoice board; retry queue; revenue by plan; PDF download | Lazy-loaded `BillingOperations.jsx`, Recharts 3, responsive CSS | Production build and Playwright E2E |
| Per-customer complete billing audit viewer | Customer-aware `AuditLog` details and `/billing/audit` filter | Audit filter test and E2E audit view |

## Weeks 7–8 — Integration, quality, and delivery

| Requirement | Implementation | Verification |
|---|---|---|
| End-to-end chain from subscription through dashboard, including edge cases | 21 backend integration/regression tests plus browser E2E | `pytest -q`; `npm run test:e2e`; CI jobs |
| Locust load/stress benchmark and performance review | `loadtests/locustfile.py`; `docs/PERFORMANCE.md` | 20-user result: 783 requests, 0 failures, 39.52 req/s, aggregate p95 49 ms in the documented local profile |
| Clear validated forms, contextual help, responsive mobile/tablet, transitions, and errors | Native constraints + API errors; contextual sandbox/lifecycle copy; four responsive breakpoints | Vite build and Playwright desktop path; manual responsive checklist |
| Architecture, flows, OpenAPI, ERD, Docker deployment, and known limitations | `docs/ARCHITECTURE.md`, `API_REFERENCE.md`, `ERD.md`, `DEPLOYMENT.md`, `KNOWN_LIMITATIONS.md`; live `/docs` | Documentation review and Docker Compose config validation |
| Final presentation and rehearsable E2E demo | `docs/BillFlow_AI_Final_Presentation.pptx`; `docs/DEMO_SCRIPT.md` | Slide render/overflow QA and demo checklist |

## Cross-cutting quality controls

- **Tenant isolation:** owner-scoped reads/writes plus explicit second-tenant test.
- **Idempotency:** cycles, usage, payment requests, and webhook event IDs.
- **Financial precision:** `Decimal` calculations and fixed-scale database numerics.
- **Auditability:** state-changing business operations record entity, tenant user, customer context, details, and timestamp.
- **Safety:** mock/provider boundaries are explicit; browser users cannot silently move real money.
