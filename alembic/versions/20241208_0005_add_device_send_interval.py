"""Add send_interval to devices table

Revision ID: 0005
Revises: 0004
Create Date: 2024-12-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add send_interval column (default 60 seconds)
    op.add_column('devices', sa.Column('send_interval', sa.Integer(), nullable=False, server_default='60'))


def downgrade() -> None:
    op.drop_column('devices', 'send_interval')
