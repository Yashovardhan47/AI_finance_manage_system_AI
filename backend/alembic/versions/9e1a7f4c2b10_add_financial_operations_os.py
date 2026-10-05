"""add financial operations os

Revision ID: 9e1a7f4c2b10
Revises: 6f76deade351
Create Date: 2026-10-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e1a7f4c2b10"
down_revision: Union[str, None] = "6f76deade351"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_obligations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.Column("provider_connection_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("counterparty", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("recurrence", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("essential", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=35), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("external_reference", sa.String(length=180), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("contract_terms", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("next_action", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_connection_id"], ["provider_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source", "external_reference", name="uq_obligation_source_reference"),
    )
    op.create_index("ix_financial_obligations_user_id", "financial_obligations", ["user_id"])
    op.create_index("ix_financial_obligations_bill_id", "financial_obligations", ["bill_id"])
    op.create_index("ix_financial_obligations_provider_connection_id", "financial_obligations", ["provider_connection_id"])
    op.create_index("ix_financial_obligations_counterparty", "financial_obligations", ["counterparty"])
    op.create_index("ix_financial_obligations_category", "financial_obligations", ["category"])
    op.create_index("ix_financial_obligations_due_date", "financial_obligations", ["due_date"])
    op.create_index("ix_financial_obligations_status", "financial_obligations", ["status"])

    op.create_table(
        "obligation_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=True),
        sa.Column("extraction_status", sa.String(length=30), nullable=False),
        sa.Column("extraction_confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["obligation_id"], ["financial_obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_obligation_documents_user_id", "obligation_documents", ["user_id"])
    op.create_index("ix_obligation_documents_obligation_id", "obligation_documents", ["obligation_id"])
    op.create_index("ix_obligation_documents_content_hash", "obligation_documents", ["content_hash"])

    op.create_table(
        "financial_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("autonomy_mode", sa.String(length=30), nullable=False),
        sa.Column("minimum_reserve", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("max_preparable_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("approval_above", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("allowed_categories", sa.JSON(), nullable=False),
        sa.Column("trusted_counterparties", sa.JSON(), nullable=False),
        sa.Column("require_provider_confirmation", sa.Boolean(), nullable=False),
        sa.Column("protect_essential_first", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_financial_policy_user"),
    )
    op.create_index("ix_financial_policies_user_id", "financial_policies", ["user_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider_connection_id", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(length=240), nullable=False),
        sa.Column("data_categories", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("consent_reference", sa.String(length=180), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["provider_connection_id"], ["provider_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consent_reference"),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])
    op.create_index("ix_consent_records_provider_connection_id", "consent_records", ["provider_connection_id"])
    op.create_index("ix_consent_records_status", "consent_records", ["status"])

    op.create_table(
        "financial_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=35), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("proposed_date", sa.Date(), nullable=True),
        sa.Column("proposed_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("forecast_snapshot", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["financial_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["obligation_id"], ["financial_obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_financial_recommendations_user_id", "financial_recommendations", ["user_id"])
    op.create_index("ix_financial_recommendations_obligation_id", "financial_recommendations", ["obligation_id"])
    op.create_index("ix_financial_recommendations_action", "financial_recommendations", ["action"])
    op.create_index("ix_financial_recommendations_status", "financial_recommendations", ["status"])

    op.create_table(
        "financial_action_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("policy_evaluation", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["financial_recommendations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["financial_obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_action_request_idempotency"),
    )
    op.create_index("ix_financial_action_requests_user_id", "financial_action_requests", ["user_id"])
    op.create_index("ix_financial_action_requests_recommendation_id", "financial_action_requests", ["recommendation_id"])
    op.create_index("ix_financial_action_requests_obligation_id", "financial_action_requests", ["obligation_id"])
    op.create_index("ix_financial_action_requests_status", "financial_action_requests", ["status"])

    op.create_table(
        "financial_scenarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_financial_scenarios_user_id", "financial_scenarios", ["user_id"])

    op.create_table(
        "financial_outcome_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("action_request_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=180), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_request_id"], ["financial_action_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["obligation_id"], ["financial_obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_financial_outcome_events_user_id", "financial_outcome_events", ["user_id"])
    op.create_index("ix_financial_outcome_events_obligation_id", "financial_outcome_events", ["obligation_id"])
    op.create_index("ix_financial_outcome_events_action_request_id", "financial_outcome_events", ["action_request_id"])
    op.create_index("ix_financial_outcome_events_event_type", "financial_outcome_events", ["event_type"])
    op.create_index("ix_financial_outcome_events_status", "financial_outcome_events", ["status"])
    op.create_index("ix_financial_outcome_events_occurred_at", "financial_outcome_events", ["occurred_at"])

    op.create_table(
        "financial_exception_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("obligation_id", sa.Integer(), nullable=False),
        sa.Column("outcome_event_id", sa.Integer(), nullable=True),
        sa.Column("case_type", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=25), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["outcome_event_id"], ["financial_outcome_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["obligation_id"], ["financial_obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_financial_exception_cases_user_id", "financial_exception_cases", ["user_id"])
    op.create_index("ix_financial_exception_cases_obligation_id", "financial_exception_cases", ["obligation_id"])
    op.create_index("ix_financial_exception_cases_case_type", "financial_exception_cases", ["case_type"])
    op.create_index("ix_financial_exception_cases_status", "financial_exception_cases", ["status"])


def downgrade() -> None:
    for index_name in (
        "ix_financial_exception_cases_status",
        "ix_financial_exception_cases_case_type",
        "ix_financial_exception_cases_obligation_id",
        "ix_financial_exception_cases_user_id",
    ):
        op.drop_index(index_name, table_name="financial_exception_cases")
    op.drop_table("financial_exception_cases")

    for index_name in (
        "ix_financial_outcome_events_occurred_at",
        "ix_financial_outcome_events_status",
        "ix_financial_outcome_events_event_type",
        "ix_financial_outcome_events_action_request_id",
        "ix_financial_outcome_events_obligation_id",
        "ix_financial_outcome_events_user_id",
    ):
        op.drop_index(index_name, table_name="financial_outcome_events")
    op.drop_table("financial_outcome_events")

    op.drop_index("ix_financial_scenarios_user_id", table_name="financial_scenarios")
    op.drop_table("financial_scenarios")

    for index_name in (
        "ix_financial_action_requests_status",
        "ix_financial_action_requests_obligation_id",
        "ix_financial_action_requests_recommendation_id",
        "ix_financial_action_requests_user_id",
    ):
        op.drop_index(index_name, table_name="financial_action_requests")
    op.drop_table("financial_action_requests")

    for index_name in (
        "ix_financial_recommendations_status",
        "ix_financial_recommendations_action",
        "ix_financial_recommendations_obligation_id",
        "ix_financial_recommendations_user_id",
    ):
        op.drop_index(index_name, table_name="financial_recommendations")
    op.drop_table("financial_recommendations")

    for index_name in (
        "ix_consent_records_status",
        "ix_consent_records_provider_connection_id",
        "ix_consent_records_user_id",
    ):
        op.drop_index(index_name, table_name="consent_records")
    op.drop_table("consent_records")

    op.drop_index("ix_financial_policies_user_id", table_name="financial_policies")
    op.drop_table("financial_policies")

    for index_name in (
        "ix_obligation_documents_content_hash",
        "ix_obligation_documents_obligation_id",
        "ix_obligation_documents_user_id",
    ):
        op.drop_index(index_name, table_name="obligation_documents")
    op.drop_table("obligation_documents")

    for index_name in (
        "ix_financial_obligations_status",
        "ix_financial_obligations_due_date",
        "ix_financial_obligations_category",
        "ix_financial_obligations_counterparty",
        "ix_financial_obligations_provider_connection_id",
        "ix_financial_obligations_bill_id",
        "ix_financial_obligations_user_id",
    ):
        op.drop_index(index_name, table_name="financial_obligations")
    op.drop_table("financial_obligations")
