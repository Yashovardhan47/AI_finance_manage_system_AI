# Known Limitations and Production Boundaries

The implemented product is complete for the supplied engineering specification and safe demonstration. The following items require real commercial, regulatory, or infrastructure decisions and therefore are intentionally not represented as production integrations.

## Payments and provider accounts

- `mock_gateway` is deterministic test infrastructure. It does not move funds, tokenize cards, settle through UPI, or clear through Bharat Connect/BBPS.
- Production requires a licensed/accredited payment partner, hosted authorization, provider webhooks, reconciliation files, disputes, chargebacks, and settlement reporting.
- Existing home/health/entertainment connectors are sandbox adapters. Updating arbitrary third-party accounts requires each provider's supported OAuth/API or an approved aggregator; Google identity alone cannot grant that access.

## Notifications

- The durable outbox is implemented, but its default Celery adapter marks sandbox delivery as sent. Integrate an approved email/SMS/push provider, delivery webhooks, suppression handling, templates, and dead-letter alerts.

## Tax and accounting

- Country/region rates and effective dates are configurable, but the engine is not a substitute for a tax service or accountant. Product taxability, nexus, exemptions, reverse charge, inclusive pricing, multi-jurisdiction rules, credit notes, and statutory e-invoicing need jurisdiction-specific implementation.
- Revenue metrics are operational analytics, not GAAP/IFRS revenue recognition or a general ledger.

## Security and compliance

- The application avoids raw payment credentials, but a production security program still needs KMS-backed secret encryption, key rotation, rate limiting, CSRF strategy, CSP, WAF, SAST/DAST, dependency scanning, penetration testing, privacy controls, retention/deletion policy, incident response, and relevant PCI/privacy/regulatory assessment.
- Authentication supports workspace users, not a full organization/RBAC model with operator roles, maker-checker approval, SSO, or SCIM.
- Webhook HMAC uses a shared secret. Real gateways may require asymmetric signatures, rotating key IDs, timestamp tolerance, and IP allowlists.

## Scale and operations

- SQLite is only for local development/tests. PostgreSQL is the supported multi-process deployment database.
- PDFs are stored in the database for specification fidelity. High-volume deployments should move immutable files to encrypted object storage.
- Health checks are process-level. Production needs metrics, traces, centralized logs, queue alerts, SLOs, disaster recovery exercises, and multi-zone design.
- Currency is stored per plan/invoice, but foreign exchange conversion and consolidated multi-currency reporting are not implemented.

These boundaries are also visible in the UI and documentation so a sandbox event is never presented as a real financial settlement.
