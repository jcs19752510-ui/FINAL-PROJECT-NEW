"""v19_coding_problems_analysis

원본 REQ-F-004(라이브 코딩 AI 분석, 2026-10-12) — 코딩 문제 테이블 신설, code_submissions 에
풀이 문제 연결(problem_id)과 분석 결과(analysis_json) nullable 컬럼 추가. 기존 행은 NULL 로 남는다.

Revision ID: b7e1d3a9c5f2
Revises: a5d2c8e1f7b3
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7e1d3a9c5f2'
down_revision: Union[str, None] = 'a5d2c8e1f7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coding_problems',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(64), nullable=False, unique=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('difficulty', sa.String(16), nullable=False),
        sa.Column('tests_json', postgresql.JSONB(), nullable=False),
        sa.Column('perf_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column('code_submissions', sa.Column('problem_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('code_submissions', sa.Column('analysis_json', postgresql.JSONB(), nullable=True))
    op.create_foreign_key(
        'fk_code_submissions_problem_id', 'code_submissions', 'coding_problems', ['problem_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_code_submissions_problem_id', 'code_submissions', type_='foreignkey')
    op.drop_column('code_submissions', 'analysis_json')
    op.drop_column('code_submissions', 'problem_id')
    op.drop_table('coding_problems')
