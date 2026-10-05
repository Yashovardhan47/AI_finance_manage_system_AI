# Financial Operations OS

BillFlow's Financial Operations layer expands the product from bill payment into an accountable **decision-to-outcome operating system**. It owns the intelligence, policy, approval, evidence, and recovery loop while keeping regulated settlement and provider-side mutations behind explicit external authorization.

## Lifecycle

1. **Discover** — normalize bills, connected-provider obligations, and manually entered commitments into one obligation graph.
2. **Understand** — preserve category, priority, recurrence, contract metadata, source evidence, and extraction confidence.
3. **Forecast** — simulate 90 days of balances using active accounts, income, recent non-bill spending, and recurring obligations.
4. **Recommend** — choose `pay_now`, `schedule`, `hold`, or `split_or_negotiate` with inspectable evidence and confidence.
5. **Approve** — record an explicit user decision and create an idempotent action request.
6. **Hand off** — classify the request as advice, prepared handoff, policy-blocked, or awaiting an authorized partner. No endpoint silently moves money.
7. **Verify** — record gateway/provider/user outcome evidence independently of the payment request.
8. **Reconcile** — open an exception whenever the expected provider state and observed state disagree.
9. **Learn** — retain decisions, scenarios, outcomes, and audit events for later preference and outcome evaluation.

## Autonomy modes

| Mode | System behavior | Execution boundary |
|---|---|---|
| `advise` | Produces explainable recommendations. | Approval records advice only. |
| `prepare` | Creates a ready-for-handoff action when amount/category policy permits. | A user and external rail still authorize execution. |
| `execute_authorized` | Creates an awaiting-partner-authorization request for trusted, connected obligations. | The partner mandate, provider API, and returned evidence remain mandatory. |

Every mode preserves `requires_explicit_user_approval` and `requires_external_authorization` in the policy evaluation.

## Persistent domain

- `financial_obligations` — universal commitment graph linked to bills and provider accounts.
- `obligation_documents` — document metadata and reviewable extracted contract fields; raw secrets are not stored.
- `financial_policies` — reserve, preparation limit, category/counterparty rules, and outcome requirements.
- `financial_recommendations` — versioned action, risk, confidence, evidence, and forecast snapshot.
- `financial_action_requests` — idempotent approval-to-handoff state.
- `financial_scenarios` — saved what-if assumptions and 90-day results.
- `financial_outcome_events` — independent evidence from user, gateway, provider, reconciliation, or system.
- `financial_exception_cases` — mismatch/recovery work queue.
- `consent_records` — purpose, data categories, expiry, and revocation history.

## Command center

The React **Autopilot** workspace includes:

- projected low balance, upcoming obligation, decision, and exception metrics;
- a 90-day financial digital-twin chart;
- a user-editable policy builder;
- an evidence-backed decision inbox with approve/decline actions;
- obligation totals grouped by category;
- a recurring or one-time what-if simulator;
- manual obligation capture;
- provider-outcome mismatch reporting and resolution;
- a recent action-request trail.

## Correctness and safety properties

- All reads and writes are scoped to the authenticated user.
- Bill-to-obligation synchronization is idempotent through a source/reference constraint.
- Approval requests are idempotent per user-supplied key.
- Recalculating recommendations expires previous pending versions instead of mutating decision history.
- Forecast balances and policy decisions use `Decimal` inputs; the explanation layer does not perform settlement arithmetic.
- A payment is never considered a provider success merely because a gateway succeeded.
- A provider-state mismatch creates an exception and marks the obligation disputed.
- Consent can be granted and revoked without deleting the evidence trail.

## Verification

The backend suite covers obligation synchronization, forecast generation, policy enforcement, approval idempotency, advice-only behavior, scenario reserve breaches, mismatch exceptions, contract metadata, consent revocation, and tenant isolation. The Alembic migration is tested from an empty database, and the frontend is verified with the production Vite build.
