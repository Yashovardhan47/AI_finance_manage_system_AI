# End-to-End Demo Script

Target length: 6–8 minutes.

## 1. Frame the problem (30 seconds)

“BillFlow AI is both an all-in-one personal bill assistant and a recurring-revenue operations platform. The personal side helps a user decide and authorize bills safely. Billing Operations lets a SaaS team manage plans, renewals, invoices, failures, tax, refunds, and compliance from the same Python full-stack system.”

## 2. Sign in and open Billing Operations (30 seconds)

Register, select **Billing ops**, and click **Load live demo**. Explain that every seeded record belongs only to the signed-in workspace and can be recreated deterministically.

## 3. Explain the overview (60 seconds)

Point out MRR, outstanding revenue, trial conversion, churn, and recovery queue. Show the Recharts revenue trend, revenue by plan, invoice status mix, and latest invoice board.

## 4. Demonstrate lifecycle and proration (90 seconds)

Open **Subscriptions**. Pause and resume Acme Analytics. Choose **Change plan**, select another plan, and keep **Immediately, with proration**. Show the resulting invoice with an unused-plan credit and a new-plan debit. Then show end-of-cycle as the alternative timing.

Record metered usage on an active subscription and explain that it is idempotently attached to the next due invoice.

## 5. Demonstrate collection and PDF (75 seconds)

Open **Invoices**, expand an invoice, and identify plan fee, usage/proration, tax, and totals. Use **Fail** on an eligible invoice to generate a verified signed failure event; show the subscription becomes past due and the retry queue appears. Use **PDF** to display the persisted branded invoice.

## 6. Demonstrate recovery and cancellation (60 seconds)

Open **Recovery**. Explain the day 1, 3, and 7 schedule. Click **Recover** to show a successful attempt returning the subscription to active and cancelling later attempts. For the failure path, explain that exhausting attempt three cancels access and queues a customer notification.

## 7. Demonstrate refund, tax, and audit (60 seconds)

Refund a paid invoice, then reopen its PDF to show the refund line. In **Tax & audit**, show the country/region rule, tax summary, and customer filter. Highlight plan-created, subscription-created, payment-received, payment-failed, plan-changed, and refund-issued events.

## 8. Close with architecture and trust (45 seconds)

“FastAPI and PostgreSQL are the system of record, Celery Beat schedules renewals, Redis transports background work, ReportLab generates immutable invoices, and React/Recharts gives operators visibility. The gateway and provider adapters are explicit sandboxes: no PIN, OTP, card, or real money is handled here. Production integration happens only through licensed and official provider APIs.”

Before presenting, run the acceptance commands in `docs/TESTING.md` and keep `/docs` open as a fallback technical view.
