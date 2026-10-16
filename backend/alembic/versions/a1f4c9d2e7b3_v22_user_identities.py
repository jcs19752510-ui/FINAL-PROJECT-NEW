"""v22_user_identities

Google 계정 연동 로그인(2026-10-16): 외부 제공자 계정과 users를 잇는 새 테이블만 추가한다.
users 테이블은 변경하지 않는다. downgrade는 이 테이블만 삭제한다.

Revision ID: a1f4c9d2e7b3
Revises: d9a3f5c7e2b1
Create Date: 2026-10-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1f4c9d2e7b3'
down_revision: Union[str, None] = 'd9a3f5c7e2b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_identities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('provider_sub', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('provider', 'provider_sub', name='uq_user_identities_provider_sub'),
    )
    op.create_index('ix_user_identities_user_id', 'user_identities', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_user_identities_user_id', table_name='user_identities')
    op.drop_table('user_identities')
