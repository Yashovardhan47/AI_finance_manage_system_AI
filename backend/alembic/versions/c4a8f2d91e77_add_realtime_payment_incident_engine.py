"""add real-time payment incident and notification engine

Revision ID: c4a8f2d91e77
Revises: 9e1a7f4c2b10
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a8f2d91e77"
down_revision: Union[str, None] = "9e1a7f4c2b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("billing_payments") as batch_op:
        batch_op.add_column(sa.Column("processing_state", sa.String(length=40), server_default="pending", nullable=False))
        batch_op.add_column(sa.Column("provider_status", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("last_status_check_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("next_status_check_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("timed_out_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_billing_payments_processing_state", ["processing_state"])
        batch_op.create_index("ix_billing_payments_next_status_check_at", ["next_status_check_at"])
        batch_op.create_index(
            "ix_billing_payment_poll_claim", ["status", "next_status_check_at", "processing_state"]
        )

    with op.batch_alter_table("billing_notifications") as batch_op:
        batch_op.add_column(sa.Column("delivery_status", sa.String(length=30), server_default="queued", nullable=False))
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False))
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(length=40), server_default="sandbox", nullable=False))
        batch_op.add_column(sa.Column("provider_message_id", sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column("provider_response", sa.JSON(), server_default="{}", nullable=False))
        batch_op.add_column(sa.Column("dedupe_key", sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column("escalation_level", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_billing_notifications_delivery_status", ["delivery_status"])
        batch_op.create_index("ix_billing_notifications_next_attempt_at", ["next_attempt_at"])
        batch_op.create_index("ix_billing_notifications_lease_expires_at", ["lease_expires_at"])
        batch_op.create_index("ix_billing_notifications_provider_message_id", ["provider_message_id"])
        batch_op.create_unique_constraint(
            "uq_billing_notification_owner_dedupe", ["owner_user_id", "dedupe_key"]
        )
        batch_op.create_index(
            "ix_billing_notification_claim", ["delivery_status", "next_attempt_at", "lease_expires_at"]
        )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False),
        sa.Column("push_enabled", sa.Boolean(), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=True),
        sa.Column("phone_number", sa.String(length=40), nullable=True),
        sa.Column("push_token", sa.Text(), nullable=True),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
        sa.Column("timezone_name", sa.String(length=80), nullable=False),
        sa.Column("escalation_rules", sa.JSON(), nullable=False),
        sa.Column("max_delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["billing_customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "customer_id", name="uq_notification_preference_owner_customer"),
    )
    op.create_index("ix_notification_preferences_owner_user_id", "notification_preferences", ["owner_user_id"])
    op.create_index("ix_notification_preferences_customer_id", "notification_preferences", ["customer_id"])

    op.create_table(
        "payment_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("incident_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=25), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=180), nullable=False),
        sa.Column("escalation_level", sa.Integer(), nullable=False),
        sa.Column("next_escalation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["billing_customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["billing_payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "dedupe_key", name="uq_payment_incident_owner_dedupe"),
    )
    for name in ("owner_user_id", "customer_id", "subscription_id", "invoice_id", "payment_id", "incident_type", "severity", "status", "next_escalation_at"):
        op.create_index(f"ix_payment_incidents_{name}", "payment_incidents", [name])
    op.create_index(
        "ix_payment_incident_escalation_claim", "payment_incidents", ["status", "next_escalation_at"]
    )

    op.create_table(
        "notification_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=180), nullable=False),
        sa.Column("provider_message_id", sa.String(length=180), nullable=False),
        sa.Column("delivery_status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["billing_notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_notification_receipt_provider_event"),
    )
    for name in ("notification_id", "provider", "provider_message_id", "delivery_status"):
        op.create_index(f"ix_notification_receipts_{name}", "notification_receipts", [name])

    op.create_table(
        "payment_reconciliations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("provider_check_id", sa.String(length=180), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=False),
        sa.Column("provider_status", sa.String(length=80), nullable=False),
        sa.Column("resolved_status", sa.String(length=40), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["billing_payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "provider_check_id", name="uq_payment_reconciliation_check"),
    )
    for name in ("owner_user_id", "payment_id", "provider_status", "resolved_status", "checked_at"):
        op.create_index(f"ix_payment_reconciliations_{name}", "payment_reconciliations", [name])

    op.create_table(
        "realtime_billing_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in ("owner_user_id", "event_type", "created_at"):
        op.create_index(f"ix_realtime_billing_events_{name}", "realtime_billing_events", [name])

    op.create_table(
        "task_dead_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=180), nullable=False),
        sa.Column("task_name", sa.String(length=180), nullable=False),
        sa.Column("queue_name", sa.String(length=80), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("kwargs", sa.JSON(), nullable=False),
        sa.Column("exception_type", sa.String(length=160), nullable=False),
        sa.Column("exception_message", sa.Text(), nullable=False),
        sa.Column("traceback_text", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=25), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_task_dead_letter_task_id"),
    )
    op.create_index("ix_task_dead_letters_task_name", "task_dead_letters", ["task_name"])
    op.create_index("ix_task_dead_letters_status", "task_dead_letters", ["status"])


def downgrade() -> None:
    op.drop_index("ix_task_dead_letters_status", table_name="task_dead_letters")
    op.drop_index("ix_task_dead_letters_task_name", table_name="task_dead_letters")
    op.drop_table("task_dead_letters")

    for name in ("created_at", "event_type", "owner_user_id"):
        op.drop_index(f"ix_realtime_billing_events_{name}", table_name="realtime_billing_events")
    op.drop_table("realtime_billing_events")

    for name in ("checked_at", "resolved_status", "provider_status", "payment_id", "owner_user_id"):
        op.drop_index(f"ix_payment_reconciliations_{name}", table_name="payment_reconciliations")
    op.drop_table("payment_reconciliations")

    for name in ("delivery_status", "provider_message_id", "provider", "notification_id"):
        op.drop_index(f"ix_notification_receipts_{name}", table_name="notification_receipts")
    op.drop_table("notification_receipts")

    op.drop_index("ix_payment_incident_escalation_claim", table_name="payment_incidents")
    for name in ("next_escalation_at", "status", "severity", "incident_type", "payment_id", "invoice_id", "subscription_id", "customer_id", "owner_user_id"):
        op.drop_index(f"ix_payment_incidents_{name}", table_name="payment_incidents")
    op.drop_table("payment_incidents")

    op.drop_index("ix_notification_preferences_customer_id", table_name="notification_preferences")
    op.drop_index("ix_notification_preferences_owner_user_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")

    with op.batch_alter_table("billing_notifications") as batch_op:
        batch_op.drop_constraint("uq_billing_notification_owner_dedupe", type_="unique")
        batch_op.drop_index("ix_billing_notification_claim")
        for name in ("provider_message_id", "lease_expires_at", "next_attempt_at", "delivery_status"):
            batch_op.drop_index(f"ix_billing_notifications_{name}")
        for name in (
            "dead_lettered_at", "failed_at", "opened_at", "delivered_at", "escalation_level", "dedupe_key",
            "provider_response", "provider_message_id", "provider", "lease_expires_at", "last_attempt_at",
            "next_attempt_at", "max_attempts", "attempt_count", "delivery_status",
        ):
            batch_op.drop_column(name)

    with op.batch_alter_table("billing_payments") as batch_op:
        batch_op.drop_index("ix_billing_payment_poll_claim")
        batch_op.drop_index("ix_billing_payments_next_status_check_at")
        batch_op.drop_index("ix_billing_payments_processing_state")
        for name in ("reconciled_at", "timed_out_at", "next_status_check_at", "last_status_check_at", "provider_status", "processing_state"):
            batch_op.drop_column(name)
