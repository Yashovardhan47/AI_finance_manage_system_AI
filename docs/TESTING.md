# Testing Guide

## Automated layers

| Layer | Command | Coverage intent |
|---|---|---|
| Python compile | `python -m compileall -q app` | Import and syntax safety. |
| Database migration | `DATABASE_URL=sqlite:///./migration-smoke.db alembic upgrade head` | Clean-schema reproducibility. |
| Backend integration | `pytest -q` | Auth, personal finance, connectors, plan/customer/subscription lifecycle, cycles, proration, usage, tax, payment events, HMAC rejection/replay, retry recovery/exhaustion, refunds, PDFs, analytics, audit, and tenant isolation. |
| Frontend production build | `npm run build` | JSX, CSS, Recharts, lazy route, and optimized bundle compilation. |
| Browser E2E | `npm run test:e2e` | Register → Billing Operations → seed → charts → pause/resume → invoice detail/PDF link → retry queue → create plan → tax/audit. |
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
- An immediate upgrade shows both proration credit and debit.
- A regional tax override wins over a country default only inside its effective window.
- A failed payment creates exactly three queued attempts and one customer alert.
- Retry success restores service; attempt-three failure cancels it.
- Refund amount cannot exceed paid minus already refunded.
- Regenerated invoice PDF includes the refund line and a new hash.
- A second authenticated tenant cannot list or fetch the first tenant's resources.
- Desktop, tablet, and mobile layouts expose all operator actions without horizontal page overflow.
