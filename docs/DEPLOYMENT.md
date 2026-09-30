# Deployment Guide

## Local Docker Compose

Requirements: Docker Desktop or Docker Engine with Compose v2.

```bash
cp backend/.env.example backend/.env
docker compose up --build
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
| `backend` | FastAPI, OpenAPI, PDFs, webhooks | 8000 |
| `worker` | Due cycles, retries, outbox delivery | — |
| `beat` | 5-minute billing/retry and 1-minute notification schedules | — |
| `postgres` | Transactional system of record | 5432 internal |
| `redis` | Celery broker and results | 6379 internal |

## Required production configuration

Set secrets through the deployment platform, not committed files:

```text
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=<at least 32 random bytes>
BILLING_WEBHOOK_SECRET=<independent random secret>
FRONTEND_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
AUTO_CREATE_SCHEMA=false
CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...
INVOICE_BUSINESS_NAME=...
INVOICE_BUSINESS_ADDRESS=...
```

Google sign-in additionally needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and the exact HTTPS callback in `GOOGLE_REDIRECT_URI`.

## Release procedure

1. Back up PostgreSQL and verify restoration in a non-production environment.
2. Build immutable backend and frontend images from the reviewed commit.
3. Run `alembic upgrade head` as a single release job.
4. Deploy API and verify `/health` and `/openapi.json`.
5. Deploy worker and one Beat replica.
6. Deploy frontend with `VITE_API_URL` pointing at the public API.
7. Run smoke tests: register/login, seed only in non-production, create a plan/customer/subscription, run a cycle, send one signed test webhook, download the PDF, and inspect audit history.
8. Monitor queue depth, failed tasks, webhook rejects, HTTP errors, database saturation, and notification failures.

## Scaling and reliability

- Scale API and Celery workers horizontally; run exactly one Beat scheduler unless using a distributed scheduler.
- PostgreSQL is the concurrency boundary. Keep SQLite to development/tests.
- Place Redis and PostgreSQL on private networks with encryption, authentication, backups, and retention policy.
- Replace persisted PDF bytes with encrypted object storage if invoice volume makes database storage uneconomical; retain the content hash and immutable reference.
- Configure reverse-proxy TLS, secure cookies, trusted hosts, request-size limits, rate limits, and webhook IP controls where the provider supports them.
- Use a dead-letter strategy for notifications and tasks after bounded retries.

## Rollback

Application rollback means deploying the prior image while keeping schema compatibility. Do not automatically downgrade a production database. Use reviewed forward-fix migrations unless a downgrade has been rehearsed against a backup.
