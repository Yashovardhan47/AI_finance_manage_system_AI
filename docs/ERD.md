# Database ERD

The diagram focuses on the recurring billing domain. Every tenant-owned root has `owner_user_id`; ownership is also retained on high-volume operational tables so queries can enforce tenancy directly.

```mermaid
erDiagram
    USERS ||--o{ BILLING_PLANS : owns
    USERS ||--o{ BILLING_CUSTOMERS : owns
    USERS ||--o{ AUDIT_LOGS : records
    BILLING_CUSTOMERS ||--o{ BILLING_SUBSCRIPTIONS : holds
    BILLING_PLANS ||--o{ BILLING_SUBSCRIPTIONS : prices
    BILLING_SUBSCRIPTIONS ||--o{ BILLING_CYCLES : renews
    BILLING_SUBSCRIPTIONS ||--o{ USAGE_RECORDS : meters
    BILLING_SUBSCRIPTIONS ||--o{ BILLING_INVOICES : generates
    BILLING_CUSTOMERS ||--o{ BILLING_INVOICES : receives
    BILLING_INVOICES ||--|{ INVOICE_LINE_ITEMS : itemizes
    BILLING_INVOICES ||--o{ BILLING_PAYMENTS : collects
    BILLING_INVOICES ||--o{ PAYMENT_RETRIES : recovers
    BILLING_INVOICES ||--o{ BILLING_REFUNDS : refunds
    BILLING_CUSTOMERS ||--o{ BILLING_NOTIFICATIONS : receives
    BILLING_CUSTOMERS ||--o| NOTIFICATION_PREFERENCES : configures
    BILLING_NOTIFICATIONS ||--o{ NOTIFICATION_RECEIPTS : proves
    BILLING_PAYMENTS ||--o{ PAYMENT_RECONCILIATIONS : checks
    BILLING_PAYMENTS o|--o{ PAYMENT_INCIDENTS : raises
    USERS ||--o{ REALTIME_BILLING_EVENTS : receives
    USERS ||--o{ TAX_RATES : configures
    USERS ||--o{ BILLING_WEBHOOK_EVENTS : verifies

    BILLING_PLANS {
        int id PK
        int owner_user_id FK
        string code UK
        decimal price
        enum billing_interval
        json feature_entitlements
        int trial_days
        bool is_archived
    }
    BILLING_CUSTOMERS {
        int id PK
        int owner_user_id FK
        string external_key UK
        string email
        string country_code
        string region
        decimal credit_balance
    }
    BILLING_SUBSCRIPTIONS {
        int id PK
        int customer_id FK
        int plan_id FK
        int pending_plan_id FK
        enum status
        datetime current_period_start
        datetime current_period_end
        datetime next_billing_at
        bool cancel_at_period_end
    }
    BILLING_INVOICES {
        int id PK
        string invoice_number UK
        enum status
        decimal subtotal
        decimal proration_total
        decimal usage_total
        decimal tax_total
        decimal total
        binary pdf_data
        string pdf_sha256
    }
    BILLING_PAYMENTS {
        int id PK
        int invoice_id FK
        enum status
        decimal amount
        string gateway_event_id UK
        string idempotency_key UK
        int attempt_number
        string processing_state
        string provider_status
        datetime next_status_check_at
    }
    PAYMENT_RETRIES {
        int id PK
        int invoice_id FK
        int attempt_number UK
        datetime scheduled_for
        enum status
    }
    BILLING_NOTIFICATIONS {
        int id PK
        string channel
        string delivery_status
        int attempt_count
        datetime next_attempt_at
        string provider_message_id
        datetime dead_lettered_at
    }
    PAYMENT_INCIDENTS {
        int id PK
        int payment_id FK
        string incident_type
        string severity
        string status
        int escalation_level
        datetime next_escalation_at
    }
    NOTIFICATION_RECEIPTS {
        int id PK
        int notification_id FK
        string event_id UK
        string delivery_status
        datetime occurred_at
    }
```

## Financial Operations domain

```mermaid
erDiagram
    USERS ||--o{ FINANCIAL_OBLIGATIONS : owns
    BILLS o|--o| FINANCIAL_OBLIGATIONS : normalizes
    PROVIDER_CONNECTIONS o|--o{ FINANCIAL_OBLIGATIONS : links
    FINANCIAL_OBLIGATIONS ||--o{ OBLIGATION_DOCUMENTS : evidences
    USERS ||--|| FINANCIAL_POLICIES : configures
    FINANCIAL_OBLIGATIONS ||--o{ FINANCIAL_RECOMMENDATIONS : evaluates
    FINANCIAL_RECOMMENDATIONS ||--o| FINANCIAL_ACTION_REQUESTS : approves
    FINANCIAL_OBLIGATIONS ||--o{ FINANCIAL_OUTCOME_EVENTS : verifies
    FINANCIAL_OUTCOME_EVENTS ||--o{ FINANCIAL_EXCEPTION_CASES : reconciles
    USERS ||--o{ FINANCIAL_SCENARIOS : simulates
    USERS ||--o{ CONSENT_RECORDS : controls

    FINANCIAL_OBLIGATIONS {
        int id PK
        int user_id FK
        int bill_id FK
        decimal amount
        date due_date
        string status
        json contract_terms
        json evidence
    }
    FINANCIAL_RECOMMENDATIONS {
        int id PK
        int obligation_id FK
        string action
        string risk_level
        decimal confidence
        json rationale
        json forecast_snapshot
    }
    FINANCIAL_ACTION_REQUESTS {
        int id PK
        string idempotency_key UK
        string status
        json policy_evaluation
    }
    FINANCIAL_OUTCOME_EVENTS {
        int id PK
        string event_type
        string source
        string status
        json evidence
    }
    FINANCIAL_EXCEPTION_CASES {
        int id PK
        string case_type
        string severity
        string status
        string resolution
    }
```

The Alembic migration chain contains the personal-finance, billing, and Financial Operations schemas with indexes, foreign keys, and uniqueness constraints. Apply it with `alembic upgrade head`.
