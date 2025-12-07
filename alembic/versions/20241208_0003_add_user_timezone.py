"""Add timezone field to users table

Revision ID: 0003
Revises: 0002
Create Date: 2024-12-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone column with default Moscow timezone
    op.add_column('users', sa.Column('timezone', sa.String(length=50), nullable=False, server_default='Europe/Moscow'))


def downgrade() -> None:
    op.drop_column('users', 'timezone')
