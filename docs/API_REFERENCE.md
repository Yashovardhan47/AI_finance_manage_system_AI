# BillFlow API Reference

## Financial Operations OS

Base path: `/api/v1/operations`. Every endpoint requires an authenticated session and scopes records to the current user.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/command-center` | Return policy, 90-day digital twin, obligations, decision inbox, exceptions, category graph, and action trail. |
| `POST` | `/bootstrap` | Idempotently synchronize bills into obligations and generate recommendations. |
| `GET/POST` | `/obligations` | List or create universal financial obligations. |
| `GET/POST` | `/obligations/{id}/documents` | List or attach reviewable contract-document metadata and extracted fields. |
| `GET/PUT` | `/policy` | Read or update autonomy mode, reserve, preparation limit, and provider-confirmation rules. |
| `POST` | `/recommendations/refresh` | Recalculate versioned decisions from current financial state. |
| `POST` | `/recommendations/{id}/decision` | Explicitly approve or reject; approval creates an idempotent action request. |
| `GET` | `/actions` | Inspect prepared, blocked, advice-only, or partner-authorization requests. |
| `GET/POST` | `/scenarios` | List or run 90-day what-if simulations. |
| `GET/POST` | `/outcomes` | Record independent payment/provider outcome evidence. |
| `GET` | `/exceptions` | List reconciliation and provider-state mismatch cases. |
| `POST` | `/exceptions/{id}/resolve` | Resolve a case while retaining evidence and audit history. |
| `GET/POST` | `/consents` | List or grant purpose-bound data consent. |
| `POST` | `/consents/{id}/revoke` | Revoke consent without erasing its audit trail. |

No Financial Operations endpoint directly settles money. `execute_authorized` creates an `awaiting_partner_authorization` handoff only when the policy permits it and a provider is connected.

## Billing Operations

Base path: `/api/v1/billing`. Except for the signed gateway webhook, endpoints require an authenticated BillFlow session and automatically scope records to the current tenant.

The running API publishes authoritative OpenAPI at `/openapi.json`, interactive Swagger UI at `/docs`, and ReDoc at `/redoc`.

## Demo and analytics

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/demo/seed` | Idempotently seed realistic plans, customers, lifecycle states, invoices, payments, retries, tax, notifications, and history. |
| `GET` | `/dashboard?months=12` | MRR, lifecycle, churn, trial conversion, outstanding revenue, retry count, invoice status, revenue trend, and revenue by plan. |
| `GET` | `/audit?customer_id=&limit=100` | Complete tenant or customer-scoped billing event history. |
| `GET` | `/notifications` | Transactional outbox with delivery state, attempts, provider IDs and timestamps. |

## Incidents, notification delivery and live operations

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/incidents?status=` | List tenant payment, provider, delivery and queue-health incidents. |
| `POST` | `/incidents/{id}/acknowledge` | Stop automatic escalation while retaining the incident. |
| `POST` | `/incidents/{id}/resolve` | Resolve an incident and preserve its timeline. |
| `GET/PUT` | `/notification-preferences[/{customer_id}]` | Read or replace channel, address, quiet-hours, retry and escalation policy. |
| `POST` | `/webhooks/notification-receipts/{provider}` | Accept an idempotent HMAC-signed queued/sent/delivered/opened/failed receipt. |
| `GET` | `/notification-receipts` | Inspect provider delivery evidence. |
| `GET` | `/reconciliations` | Inspect every gateway status check and its normalized result. |
| `GET` | `/queue-health` | Return tenant outbox age/depth, pending payment, incident and dead-letter health. |
| `GET` | `/events?after=` | Read durable domain events by monotonically increasing ID. |
| `GET` | `/events/stream` | Authenticated SSE feed with `Last-Event-ID` resume and heartbeats. |

Notification receipt callers sign the canonical JSON payload with `NOTIFICATION_RECEIPT_WEBHOOK_SECRET` and send the lowercase SHA-256 HMAC in `X-BillFlow-Signature`. `event_id` is unique per provider, so a replay returns `duplicate: true` without changing state twice.

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

Prometheus exposition is available at the unauthenticated infrastructure endpoint `/metrics`; keep it private at the ingress or scrape it on an internal network.

Money is transmitted as JSON numbers at the HTTP boundary and calculated with Python `Decimal` internally. Dates use ISO 8601; timestamps are UTC.
