"""Initial schema - devices and telemetry tables

Revision ID: 0001
Revises:
Create Date: 2024-12-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_uid', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('owner_telegram_id', sa.Integer(), nullable=True),
        sa.Column('firmware_version', sa.String(length=20), nullable=True),
        sa.Column('last_ip', sa.String(length=45), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('is_online', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_devices_device_uid', 'devices', ['device_uid'], unique=True)
    op.create_index('ix_devices_owner_telegram_id', 'devices', ['owner_telegram_id'], unique=False)

    # Create telemetry table
    op.create_table(
        'telemetry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('co2', sa.Integer(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_telemetry_device_id', 'telemetry', ['device_id'], unique=False)
    op.create_index('ix_telemetry_timestamp', 'telemetry', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_telemetry_timestamp', table_name='telemetry')
    op.drop_index('ix_telemetry_device_id', table_name='telemetry')
    op.drop_table('telemetry')
    op.drop_index('ix_devices_owner_telegram_id', table_name='devices')
    op.drop_index('ix_devices_device_uid', table_name='devices')
    op.drop_table('devices')
