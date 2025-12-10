"""Add display_enabled and live_mode_until to devices table

Revision ID: 0007
Revises: 0006
Create Date: 2024-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add display_enabled column (OLED display on/off, default True)
    op.add_column('devices', sa.Column('display_enabled', sa.Boolean(), nullable=False, server_default='true'))

    # Add live_mode_until column (datetime when live mode ends, null = not active)
    op.add_column('devices', sa.Column('live_mode_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'live_mode_until')
    op.drop_column('devices', 'display_enabled')
