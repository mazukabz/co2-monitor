"""Add os_version to devices table

Revision ID: 0006
Revises: 0005
Create Date: 2024-12-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add os_version column (e.g., "Raspbian GNU/Linux 11 (bullseye)")
    op.add_column('devices', sa.Column('os_version', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'os_version')
