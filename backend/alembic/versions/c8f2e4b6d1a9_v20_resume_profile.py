"""v20_resume_profile

이력서 기반 맞춤 면접(2026-10-14) — resume_applications 에 분석 상태(profile_status)와
암호화 요약(profile_json) 추가. 기존 행은 'pending'(첫 사용 시 한 번 추출).

Revision ID: c8f2e4b6d1a9
Revises: b7e1d3a9c5f2
Create Date: 2026-10-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c8f2e4b6d1a9'
down_revision: Union[str, None] = 'b7e1d3a9c5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('resume_applications', sa.Column('profile_status', sa.String(16), nullable=False, server_default='pending'))
    op.add_column('resume_applications', sa.Column('profile_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('resume_applications', 'profile_json')
    op.drop_column('resume_applications', 'profile_status')
