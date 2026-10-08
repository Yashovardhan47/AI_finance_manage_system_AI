# Deployment Guide

## Local Docker Compose

Requirements: Docker Desktop or Docker Engine with Compose v2.

```bash
cp backend/.env.example backend/.env
docker compose --env-file backend/.env up --build
```

Open:

- Frontend: `http://localhost:5173`
- API health: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

PostgreSQL and Redis use named volumes. The API container runs `alembic upgrade head` before Uvicorn. Worker and Beat wait for the API health check, which ensures one migration owner.

## Services

| Service | Role | Default port |
|---|---|---:|
| `frontend` | Built React application served by Nginx | 5173 |
| `backend` | FastAPI, OpenAPI, SSE, PDFs, signed webhooks, Prometheus | 8000 |
| `worker` | Due cycles/retries, outbox delivery, payment polling, incidents, queue health | — |
| `beat` | 5-minute billing/retry and 30–60 second reliability schedules | — |
| `postgres` | Transactional system of record | 5432 internal |
| `redis` | Celery broker and results | 6379 internal |

## Required production configuration

Set secrets through the deployment platform, not committed files:

```text
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=<at least 32 random bytes>
BILLING_WEBHOOK_SECRET=<independent random secret>
NOTIFICATION_RECEIPT_WEBHOOK_SECRET=<a second independent random secret>
FRONTEND_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTO_CREATE_SCHEMA=false
CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...
INVOICE_BUSINESS_NAME=...
INVOICE_BUSINESS_ADDRESS=...
```

Choose real notification adapters only after injecting their credentials: `EMAIL_PROVIDER=smtp`, `SMS_PROVIDER=twilio`, and/or `PUSH_PROVIDER=fcm`. The complete variable list and operational guidance are in `REALTIME_INCIDENT_ENGINE.md`. Set `SENTRY_DSN` to enable Sentry; scrape `/metrics` only on a protected internal route.

Generate `JWT_SECRET` from a cryptographically secure source (for example, `openssl rand -hex 32`). Production startup rejects the development placeholder, secrets shorter than 32 characters, insecure auth cookies, and a non-HTTPS frontend URL.

Google sign-in additionally needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and the exact HTTPS API callback in `GOOGLE_REDIRECT_URI`. Register that URI in the Google Cloud OAuth web client exactly as deployed—scheme, host, port, path, and trailing slash must match. Configure both client credentials or neither; a partial configuration fails at startup.

Keep the frontend and API under the same registrable site when possible (for example, `app.example.com` and `api.example.com`) and retain `AUTH_COOKIE_SAMESITE=lax`. If they must be on different sites, set `AUTH_COOKIE_SAMESITE=none` with `AUTH_COOKIE_SECURE=true`, use the exact frontend origin in `CORS_ORIGINS`, and test the browser's third-party-cookie policy. Set `AUTH_COOKIE_DOMAIN` only when sibling subdomains intentionally need to share the cookie; host-only cookies are safer by default.

The OAuth callback is handled by the API and redirects to `${FRONTEND_URL}/auth/callback`. Verify `GET /api/v1/auth/methods`, a password registration/login/logout cycle, a Google success, a Google cancellation, and a cross-browser stale-state rejection during every release smoke test. Rotating `JWT_SECRET` intentionally invalidates all existing BillFlow sessions.

## Release procedure

1. Back up PostgreSQL and verify restoration in a non-production environment.
2. Build immutable backend and frontend images from the reviewed commit.
3. Run `alembic upgrade head` as a single release job.
4. Deploy API and verify `/health` and `/openapi.json`.
5. Deploy worker and one Beat replica.
6. Deploy frontend with `VITE_API_URL` pointing at the public API.
7. Run smoke tests: password register/login/logout, Google success/cancellation, seed only in non-production, create a plan/customer/subscription, run a cycle, send signed payment and notification-receipt test webhooks, download the PDF, inspect incidents, and verify SSE reconnect.
8. Confirm Prometheus scrape, Sentry capture, queue depth/oldest age, dead-letter, webhook-reject, HTTP-error, database saturation and notification-failure alerts.

## Scaling and reliability

- Scale API and Celery workers horizontally; run exactly one Beat scheduler unless using a distributed scheduler.
- PostgreSQL is the concurrency boundary. Keep SQLite to development/tests.
- Place Redis and PostgreSQL on private networks with encryption, authentication, backups, and retention policy.
- Replace persisted PDF bytes with encrypted object storage if invoice volume makes database storage uneconomical; retain the content hash and immutable reference.
- Configure reverse-proxy TLS, secure cookies, trusted hosts, request-size limits, rate limits, and webhook IP controls where the provider supports them.
- Assign ownership, replay policy and retention to the implemented notification and task dead-letter records.

## Rollback

Application rollback means deploying the prior image while keeping schema compatibility. Do not automatically downgrade a production database. Use reviewed forward-fix migrations unless a downgrade has been rehearsed against a backup.
