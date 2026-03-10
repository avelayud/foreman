"""phase4_customer_profile_gmail_thread

Revision ID: 9f3a1c2e4b7d
Revises: 204de110bebe
Create Date: 2026-03-10

Adds:
  - customers.customer_profile  (JSON blob for correspondence-derived profile)
  - outreach_logs.gmail_thread_id (Gmail thread ID for exact reply detection)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '9f3a1c2e4b7d'
down_revision: Union[str, Sequence[str], None] = '204de110bebe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('customer_profile', sa.Text(), nullable=True))
    op.add_column('outreach_logs', sa.Column('gmail_thread_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('outreach_logs', 'gmail_thread_id')
    op.drop_column('customers', 'customer_profile')
