"""add_event_id_to_audit_logs

Revision ID: c4e9f1a2b3d5
Revises: d5d6c7e7a93b
Create Date: 2026-07-24 19:50:00.000000

Purpose:
  Enable idempotent Kafka audit consumer inserts.
  Without event_id, a Kafka offset replay (consumer crash before commit,
  rebalance, or manual offset reset) creates duplicate rows in audit_logs —
  silently inflating metrics and corrupting the audit trail.
  The UNIQUE constraint lets the consumer use INSERT ... ON CONFLICT DO NOTHING.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e9f1a2b3d5'
down_revision: Union[str, Sequence[str], None] = 'd5d6c7e7a93b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add event_id UUID column with a unique index for deduplication."""
    # Nullable because pre-existing audit rows don't have an event_id.
    # PostgreSQL unique constraints allow multiple NULLs, so this is safe.
    op.add_column('audit_logs', sa.Column('event_id', sa.UUID(), nullable=True))
    op.create_index(
        'ix_audit_logs_event_id',
        'audit_logs',
        ['event_id'],
        unique=True,
    )


def downgrade() -> None:
    """Remove the event_id column and its index."""
    op.drop_index('ix_audit_logs_event_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'event_id')
