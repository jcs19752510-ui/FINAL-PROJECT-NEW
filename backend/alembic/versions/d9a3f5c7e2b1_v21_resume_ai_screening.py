"""v21_resume_ai_screening

이력서 AI 합격 판정(2026-10-14) — 회사 공통 면접기준 테이블(screening_criteria)과
resume_applications 의 AI 판정 결과 컬럼(ai_*) 추가. enum 변경을 피하려고 별도 컬럼으로 둔다.

Revision ID: d9a3f5c7e2b1
Revises: c8f2e4b6d1a9
Create Date: 2026-10-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd9a3f5c7e2b1'
down_revision: Union[str, None] = 'c8f2e4b6d1a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'screening_criteria',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('criteria_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('pass_threshold', sa.Integer(), nullable=False, server_default='70'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column('resume_applications', sa.Column('ai_status', sa.String(16), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_verdict', sa.String(8), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_score', sa.Integer(), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_threshold', sa.Integer(), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_reasons_json', sa.Text(), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_criteria_version', sa.Integer(), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_analyzed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('resume_applications', sa.Column('ai_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('resume_applications', sa.Column('ai_error', sa.String(200), nullable=True))


def downgrade() -> None:
    for col in ('ai_error', 'ai_attempts', 'ai_analyzed_at', 'ai_criteria_version',
                'ai_reasons_json', 'ai_threshold', 'ai_score', 'ai_verdict', 'ai_status'):
        op.drop_column('resume_applications', col)
    op.drop_table('screening_criteria')
