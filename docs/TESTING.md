# Testing Guide

## Automated layers

| Layer | Command | Coverage intent |
|---|---|---|
| Python compile | `python -m compileall -q app` | Import and syntax safety. |
| Database migration | `DATABASE_URL=sqlite:///./migration-smoke.db alembic upgrade head` | Clean-schema reproducibility. |
| Backend integration | `pytest -q` | Auth, personal finance, billing/Financial Operations, gateway security, retries, outbox claiming/backoff, delivery receipts, payment timeout/polling/reconciliation, incident escalation, metrics and tenancy. |
| Frontend production build | `npm run build` | JSX, CSS, Recharts, lazy route, and optimized bundle compilation. |
| Browser E2E | `npm run test:e2e` | Two complete journeys: Billing Operations lifecycle and Financial Autopilot decision-to-outcome workflow. |
| Load test | Locust command below | Concurrent authenticated operational reads and tenant setup. |

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
```

The test database is recreated per test. No test depends on order or a live gateway.

## Browser E2E

```bash
cd frontend
npm ci
npx playwright install chromium
E2E_PYTHON=../backend/.venv/bin/python npm run test:e2e
```

On Windows PowerShell, use the interpreter path appropriate to the backend environment:

```powershell
$env:E2E_PYTHON = "..\backend\.venv\Scripts\python.exe"
npm run test:e2e
```

Playwright starts the API and Vite itself. It stores traces/screenshots only on failure. CI uploads the HTML report when the browser job fails.

## Load test

Start the API on port 8000, then:

```bash
cd backend
locust -f loadtests/locustfile.py \
  --host http://127.0.0.1:8000 \
  --headless --users 20 --spawn-rate 4 --run-time 20s
```

Each virtual operator registers an isolated tenant and seeds its own deterministic billing portfolio. The steady-state mix is read-heavy across dashboard, invoices, subscriptions, retries, tax, and audit.

## Manual acceptance checklist

- Invalid lifecycle transitions return a readable `409` and leave state unchanged.
- Repeating a cycle, usage key, payment key, or gateway event does not duplicate financial state.
- Repeating obligation bootstrap or action approval does not duplicate obligations or action requests.
- Advice mode cannot claim preparation or execution; partner handoffs retain external-authorization requirements.
- A provider-state mismatch opens an evidence-backed exception instead of assuming success.
- A second user cannot read obligations, scenarios, decisions, actions, outcomes, exceptions, documents, or consent belonging to another user.
- An immediate upgrade shows both proration credit and debit.
- A regional tax override wins over a country default only inside its effective window.
- A failed payment creates exactly three queued attempts and one customer alert.
- Retry success restores service; attempt-three failure cancels it.
- Refund amount cannot exceed paid minus already refunded.
- Regenerated invoice PDF includes the refund line and a new hash.
- A second authenticated tenant cannot list or fetch the first tenant's resources.
- PostgreSQL claim SQL contains `FOR UPDATE SKIP LOCKED`, and an expired lease can be reclaimed without double-sending an active lease.
- Provider delivery failure increments attempts, applies exponential backoff, and opens an incident after the configured maximum.
- Replayed receipt IDs are idempotent; delivered/opened state does not regress on a late failure.
- A stale pending payment opens a timeout incident; a terminal poll result writes reconciliation evidence and resolves it.
- Incident acknowledgement stops escalation, while resolution preserves the record and realtime event history.
- `/metrics` exports queue/payment/incident gauges and the SSE dashboard reconnects without a full page reload.
- Desktop, tablet, and mobile layouts expose all operator actions without horizontal page overflow.
