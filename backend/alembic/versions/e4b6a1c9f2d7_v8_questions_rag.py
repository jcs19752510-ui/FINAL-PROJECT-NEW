"""v8_questions_rag

Revision ID: e4b6a1c9f2d7
Revises: d3f7a2c9e1b4
Create Date: 2026-09-19 21:50:00.000000

unit-7(REQ-007): pgvector 확장 활성화 + QUESTIONS 테이블(RAG 질문은행) 신설,
TRANSCRIPTS.question_id에 FK 제약 추가(unit-4가 nullable 컬럼만 만들어둔 것을
이번에 실제로 연결).
"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4b6a1c9f2d7'
down_revision: Union[str, None] = 'd3f7a2c9e1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 03-design §3.3: 원칙적으로 초기 스키마보다 먼저 선행되어야 하나, 이 프로젝트는
    # 이미 v1~v7이 pgvector 없이 진행된 뒤라 필요해진 시점(unit-7)에 별도 revision으로
    # 활성화한다(docker-compose.yml을 pgvector/pgvector:pg16 이미지로 교체한 뒤에만
    # 성공 — unit-7-note.md §6 참고).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'questions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'category',
            sa.Enum('technical', 'behavioral', 'opening', name='question_category'),
            nullable=False,
        ),
        sa.Column('difficulty', sa.String(length=20), nullable=False),
        sa.Column('rubric_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.Column(
            'source',
            sa.Enum('bank', 'generated', name='question_source'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_questions_category'), 'questions', ['category'], unique=False)

    op.create_foreign_key(
        'fk_transcripts_question_id',
        'transcripts', 'questions',
        ['question_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_transcripts_question_id', 'transcripts', type_='foreignkey')
    op.drop_index(op.f('ix_questions_category'), table_name='questions')
    op.drop_table('questions')
    op.execute("DROP TYPE IF EXISTS question_category")
    op.execute("DROP TYPE IF EXISTS question_source")
    # vector 확장은 다른 테이블이 의존할 수 있어 downgrade에서 DROP EXTENSION을
    # 수행하지 않는다(과잉 제거 방지 — 확장 제거는 운영자가 수동으로 판단).
