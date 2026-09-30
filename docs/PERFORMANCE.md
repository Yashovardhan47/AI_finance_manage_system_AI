# Performance Benchmark

## Measured development result

Date: 25 September 2026. Tool: Locust 2.32.6. Profile: one Uvicorn process, local SQLite database, 20 concurrent authenticated operators, spawn rate 4 users/second, 20-second run.

| Metric | Result |
|---|---:|
| Requests | 783 |
| Failures | 0 (0.00%) |
| Aggregate throughput | 39.52 requests/second |
| Aggregate median | 7 ms |
| Aggregate p95 | 49 ms |
| Aggregate p99 | 230 ms |
| Maximum | 482 ms |

The maximum came from tenant registration/demo seeding, which writes a complete portfolio. Steady operational GET endpoints had these average response times:

| Endpoint | Requests | Average | Failures |
|---|---:|---:|---:|
| Dashboard | 227 | 11 ms | 0 |
| Invoices | 202 | 9 ms | 0 |
| Subscriptions | 144 | 7 ms | 0 |
| Retries | 90 | 5 ms | 0 |
| Tax summary | 40 | 6 ms | 0 |
| Audit | 40 | 4 ms | 0 |

## Interpretation

This is a reproducible development benchmark, not a production capacity promise. SQLite serializes writes, the test ran on one local process, and there was no external network, Redis task execution, managed PostgreSQL latency, TLS, or real notification/payment provider.

Production sizing should repeat at multiple concurrency levels against the intended PostgreSQL/Redis deployment, with realistic tenant sizes and separately measured write workflows. Establish SLOs before launch; a reasonable initial target is zero incorrect financial state, p95 below 500 ms for synchronous operational reads, and bounded background completion for renewals and retries.

## Reproduce

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
locust -f loadtests/locustfile.py --host http://127.0.0.1:8000 \
  --headless --users 20 --spawn-rate 4 --run-time 20s --only-summary
```
