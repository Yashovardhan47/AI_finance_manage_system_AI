# Billing Operations API Reference

Base path: `/api/v1/billing`. Except for the signed gateway webhook, endpoints require an authenticated BillFlow session and automatically scope records to the current tenant.

The running API publishes authoritative OpenAPI at `/openapi.json`, interactive Swagger UI at `/docs`, and ReDoc at `/redoc`.

## Demo and analytics

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/demo/seed` | Idempotently seed realistic plans, customers, lifecycle states, invoices, payments, retries, tax, notifications, and history. |
| `GET` | `/dashboard?months=12` | MRR, lifecycle, churn, trial conversion, outstanding revenue, retry count, invoice status, revenue trend, and revenue by plan. |
| `GET` | `/audit?customer_id=&limit=100` | Complete tenant or customer-scoped billing event history. |
| `GET` | `/notifications` | Durable customer notification outbox. |

## Plans and customers

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/plans?include_archived=false` | List the plan catalog. |
| `POST` | `/plans` | Create monthly/annual pricing, entitlements, and trial policy. |
| `PATCH` | `/plans/{plan_id}` | Update mutable commercial fields. |
| `POST` | `/plans/{plan_id}/archive` | Remove a plan from new sales while preserving history. |
| `GET` | `/customers` | List tenant billing customers. |
| `POST` | `/customers` | Create a customer, tax location, tax ID, address, and metadata. |
| `PATCH` | `/customers/{customer_id}` | Update customer billing attributes. |

## Subscriptions and usage

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/subscriptions?status=&customer_id=` | List subscriptions with customer, plan, pending plan, lifecycle timeline, and period. |
| `POST` | `/subscriptions` | Start a trial or active subscription. |
| `POST` | `/subscriptions/{id}/change-plan` | Change immediately with proration or schedule at period end. |
| `POST` | `/subscriptions/{id}/pause` | Pause an eligible subscription, optionally with a resume timestamp. |
| `POST` | `/subscriptions/{id}/resume` | Restore a paused subscription to active. |
| `POST` | `/subscriptions/{id}/cancel` | Cancel immediately or at period end; optionally refund unused paid time. |
| `POST` | `/usage` | Record idempotent metered usage for the next cycle. |
| `POST` | `/cycles/run` | Run due cycles now or at a supplied `as_of` time. |

## Invoices, gateway, refunds, and recovery

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/invoices?status=&customer_id=` | List itemized invoices. |
| `GET` | `/invoices/{invoice_id}` | Read one invoice, lines, totals, payment state, and PDF metadata. |
| `GET` | `/invoices/{invoice_id}/pdf` | Generate once, persist, and download a branded PDF. |
| `POST` | `/mock-gateway/charge` | Simulate success/failure and internally deliver a verified signed event. |
| `POST` | `/webhooks/mock-gateway` | Accept HMAC-signed `payment.paid`, `payment.failed`, or `payment.refunded` events. |
| `POST` | `/invoices/{invoice_id}/refund` | Refund all or part of the refundable balance and add an invoice line. |
| `GET` | `/retries` | List queued, processing, succeeded, failed, and cancelled attempts. |
| `POST` | `/retries/run` | Process due retries, optionally forcing a deterministic sandbox outcome. |

Webhook callers send the lowercase SHA-256 digest in `X-BillFlow-Signature`. The digest is calculated over JSON sorted by key with compact separators. Replaying an accepted `event_id` returns `duplicate: true` without applying money twice.

## Tax

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/tax-rates` | List configured country/region rates. |
| `POST` | `/tax-rates` | Create an effective-dated rate from 0–100%. |
| `PATCH` | `/tax-rates/{rate_id}` | Change rate, name, active state, or effective window. |
| `GET` | `/tax-summary?start=&end=` | Aggregate tax invoice lines by jurisdiction, label, and currency. |

## Common responses

- `400`: invalid or unsupported signed webhook.
- `401`: no valid BillFlow session.
- `404`: missing resource or a resource outside the current tenant.
- `409`: lifecycle conflict, duplicate commercial key, invalid charge state, or excessive refund.
- `422`: Pydantic validation error with field-level details.

Money is transmitted as JSON numbers at the HTTP boundary and calculated with Python `Decimal` internally. Dates use ISO 8601; timestamps are UTC.
