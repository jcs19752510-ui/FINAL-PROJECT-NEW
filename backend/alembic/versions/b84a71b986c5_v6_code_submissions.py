"""v6_code_submissions

Revision ID: b84a71b986c5
Revises: c1a2f5e9b7d3
Create Date: 2026-09-19 08:03:52.131099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b84a71b986c5'
down_revision: Union[str, None] = 'c1a2f5e9b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 참고(unit-9-note.md에도 기록): `alembic revision --autogenerate`가 병렬로 진행 중인
# 다른 작업 단위(whiteboard, unit-17)의 모델이 이 유닛의 `alembic/env.py`에는 아직
# import되어 있지 않다는 이유로 `whiteboard_snapshots` 테이블을 "삭제 대상"으로
# 오탐지했다 — 이 유닛은 code_submissions 테이블 신설만 책임지므로 그 오탐지 부분
# (whiteboard_snapshots drop/recreate)은 자동생성 결과에서 수동으로 제거했다.


def upgrade() -> None:
    op.create_table('code_submissions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interview_id', sa.UUID(), nullable=False),
    sa.Column('language', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_code_submissions_interview_id'), 'code_submissions', ['interview_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_code_submissions_interview_id'), table_name='code_submissions')
    op.drop_table('code_submissions')
