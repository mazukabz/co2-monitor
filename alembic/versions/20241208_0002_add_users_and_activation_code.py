"""Add users table and activation_code to devices

Revision ID: 0002
Revises: 0001
Create Date: 2024-12-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)

    # Add activation_code to devices table
    op.add_column('devices', sa.Column('activation_code', sa.String(length=8), nullable=True))
    op.create_index('ix_devices_activation_code', 'devices', ['activation_code'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_devices_activation_code', table_name='devices')
    op.drop_column('devices', 'activation_code')
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_table('users')
