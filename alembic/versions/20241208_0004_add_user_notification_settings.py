"""Add notification settings to users table

Revision ID: 0004
Revises: 0003
Create Date: 2024-12-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notification settings columns
    op.add_column('users', sa.Column('alerts_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('alert_threshold', sa.Integer(), nullable=False, server_default='1000'))

    op.add_column('users', sa.Column('morning_report_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('morning_report_time', sa.Time(), nullable=False, server_default='08:00:00'))

    op.add_column('users', sa.Column('evening_report_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('evening_report_time', sa.Time(), nullable=False, server_default='22:00:00'))

    op.add_column('users', sa.Column('snapshot_interval_hours', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'snapshot_interval_hours')
    op.drop_column('users', 'evening_report_time')
    op.drop_column('users', 'evening_report_enabled')
    op.drop_column('users', 'morning_report_time')
    op.drop_column('users', 'morning_report_enabled')
    op.drop_column('users', 'alert_threshold')
    op.drop_column('users', 'alerts_enabled')
