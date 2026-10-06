# BillFlow AI Architecture

## System purpose

BillFlow AI contains three tenant-isolated but complementary product areas:

1. **Personal Finance OS** — user bills, linked-provider obligations, balances, SafePay recommendations, and human-authorized settlement.
2. **Financial Operations OS** — a universal obligation graph, 90-day digital twin, user policies, explainable decisions, explicit approvals, outcome evidence, consent, and exception recovery.
3. **Billing Operations** — a SaaS operator control plane for plans, customers, recurring subscriptions, invoices, gateway events, retries, refunds, regional tax, PDFs, real-time payment incidents, multi-channel notifications, audit, and revenue analytics.

The third area implements the complete recurring-payment specification without pretending the sandbox is a licensed payment rail. The Financial Operations layer applies the same boundary: it can recommend and prepare a handoff, but only an authorized partner can execute it.

## Runtime topology

```mermaid
flowchart TB
    UI[React + Vite] --> API[FastAPI API]
    API --> DB[(PostgreSQL)]
    API --> OPS[Financial Operations engine]
    OPS --> DB
    OPS --> HANDOFF[Authorized partner handoff]
    API --> SSE[Durable SSE feed]
    API --> GW[Mock signed gateway]
    BEAT[Celery Beat] --> REDIS[(Redis)]
    REDIS --> WORKER[Celery worker]
    WORKER --> DB
    WORKER --> OUT[Transactional outbox]
    OUT --> ADAPTERS[SMTP · Twilio · FCM]
    API --> PDF[ReportLab PDF engine]
    PDF --> DB
```

Docker Compose runs PostgreSQL, Redis, the API, a worker, Beat, and the Nginx-hosted frontend. Alembic applies the schema before the API becomes healthy; workers wait for that health check to avoid concurrent migration races.

## Billing renewal data flow

```mermaid
flowchart TD
    A[Beat scans due subscriptions] --> B{Eligible state?}
    B -- No --> C[Skip safely]
    B -- Yes --> D[Resolve plan and usage]
    D --> E[Create idempotent billing cycle]
    E --> F[Build invoice lines]
    F --> G[Apply regional tax and credit]
    G --> H[Persist invoice and advance period]
    H --> I[Gateway payment event]
    I --> J{Paid?}
    J -- Yes --> K[Mark paid and notify]
    J -- No --> L[Past due + day 1/3/7 retries]
```

Every cycle has a unique `cycle:<subscription>:<period-start>` idempotency key. Invoice numbers use a tenant/month counter (`BF-YYYYMM-NNNNNN`). Usage records also carry tenant-scoped idempotency keys and are attached to one invoice only.

## Subscription state machine

```mermaid
stateDiagram-v2
    [*] --> trial
    trial --> active
    trial --> cancelled
    active --> past_due
    active --> paused
    active --> cancelled
    past_due --> active
    past_due --> paused
    past_due --> cancelled
    paused --> active
    paused --> cancelled
    cancelled --> [*]
```

State changes are validated centrally and timestamped (`trial_started_at`, `activated_at`, `past_due_at`, `paused_at`, `cancelled_at`, and `status_changed_at`). End-of-cycle changes are represented as pending state (`pending_plan_id` or `cancel_at_period_end`) and applied by the renewal engine.

## Payment and recovery flow

- The mock gateway creates the same canonical payload used by the public webhook endpoint.
- HMAC-SHA256 signs the canonical JSON body; the handler uses constant-time comparison.
- Gateway event ID and payment idempotency key prevent double processing.
- The first failure changes an active subscription to `past_due` and queues attempts for days 1, 3, and 7.
- A successful retry restores `active` and cancels later queued attempts.
- Exhausting the third retry cancels the subscription and creates a durable notification event.
- Refunds cannot exceed the paid, unrefunded balance. They add a negative invoice line and invalidate the stored PDF so the next download reflects the refund.

## Real-time incident and notification flow

```mermaid
flowchart TD
    A[Domain transaction] --> B[Outbox row + realtime event]
    C[Celery Beat] --> D[Worker claims with SKIP LOCKED]
    D --> E{Provider accepted?}
    E -- Yes --> F[Sent; await signed receipt]
    E -- No --> G[Exponential backoff]
    G --> H{Attempts exhausted?}
    H -- No --> D
    H -- Yes --> I[Dead-lettered notification + incident]
    F --> J[Delivered or opened]
```

- Payment, incident, and notification events are inserted in the same database transaction as the state they describe.
- Workers claim bounded batches with `FOR UPDATE SKIP LOCKED`, change them to `processing`, commit the lease, and perform provider I/O without holding a row lock.
- Expired leases are reclaimable after a worker crash. Provider failures use bounded exponential backoff; exhausted messages remain queryable and open an incident.
- SMTP, Twilio and Firebase Cloud Messaging are production-capable adapters selected by environment variables. `sandbox` remains the default and never makes a network call.
- Provider callbacks use an independent HMAC secret and append idempotent receipt rows. Delivery state never regresses from `opened` or `delivered` to a late failure.
- A durable `realtime_billing_events` table backs authenticated SSE. Browser reconnects resume from `Last-Event-ID`, so worker-process events are not lost between API instances.

## Pending-payment and reconciliation loop

Celery Beat runs a timeout watchdog, gateway poller, incident escalator, and queue-health monitor every minute. A payment that remains pending beyond `PENDING_PAYMENT_TIMEOUT_SECONDS` is marked `timed_out`, given an incident, and scheduled for immediate provider inquiry. Poll results are normalized to pending, succeeded, or failed, persisted as `payment_reconciliations`, and applied through the same signed, idempotent gateway-event path. A terminal provider result resolves timeout incidents but retains their full history.

## Security and tenancy

- JWT sessions are accepted through an HTTP-only cookie or Bearer token.
- Every Billing Operations query and mutation is scoped to `owner_user_id`.
- Cross-tenant resource IDs return `404`, avoiding resource enumeration.
- Webhooks do not require a browser JWT; they require the shared HMAC secret and include an owner identifier inside the signed payload.
- Payment, refund, lifecycle, invoice, plan, usage, and demo events write customer-aware audit records.
- BillFlow does not collect card data, UPI PINs, OTPs, bank passwords, or biometric material.

## Persistence decisions

PostgreSQL is the deployment database. SQLite remains supported for local development and deterministic tests. PDFs are persisted as bytes with SHA-256 and generation time, satisfying the specification while keeping the storage boundary replaceable with S3-compatible object storage later.

## Observability boundaries

`/health` reports process readiness and `/metrics` exposes Prometheus HTTP, outbox, payment, incident, delivery and dead-letter metrics. Optional Sentry initialization captures FastAPI and Celery exceptions when `SENTRY_DSN` is configured. Queue-health jobs turn backlog count or oldest-message threshold breaches into durable incidents. Terminal Celery failures are recorded in `task_dead_letters` after five automatic, jittered backoff retries.

Production still needs a metrics scraper, alert routing/SLO ownership, centralized logs, retention controls and infrastructure-level database/Redis monitoring. The application instrumentation does not provision those external systems.
