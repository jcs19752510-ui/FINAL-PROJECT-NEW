"""v18_interview_final_decision

면접 완료 건의 최종 합격/불합격 처리(2026-10-07 사용자 요청) — interviews 테이블에
nullable 컬럼 5개와 enum 타입 1개를 추가한다. 기존 행은 모두 NULL(미처리)로 남는다.

Revision ID: a5d2c8e1f7b3
Revises: 4381fbfa47d2
Create Date: 2026-10-07 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a5d2c8e1f7b3'
down_revision: Union[str, None] = '4381fbfa47d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# d4f7b2c8a913(v14)에서 확인된 교훈: enum은 add_column 전에 명시적으로 CREATE TYPE 한다.
final_decision_enum = postgresql.ENUM('accepted', 'rejected', name='final_decision', create_type=False)


def upgrade() -> None:
    postgresql.ENUM('accepted', 'rejected', name='final_decision').create(op.get_bind(), checkfirst=True)
    op.add_column('interviews', sa.Column('final_decision', final_decision_enum, nullable=True))
    op.add_column('interviews', sa.Column('final_decision_note', sa.Text(), nullable=True))
    op.add_column('interviews', sa.Column('final_decided_by', sa.UUID(), nullable=True))
    op.add_column('interviews', sa.Column('final_decided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('interviews', sa.Column('final_notified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_interviews_final_decided_by_users', 'interviews', 'users', ['final_decided_by'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_interviews_final_decided_by_users', 'interviews', type_='foreignkey')
    op.drop_column('interviews', 'final_notified_at')
    op.drop_column('interviews', 'final_decided_at')
    op.drop_column('interviews', 'final_decided_by')
    op.drop_column('interviews', 'final_decision_note')
    op.drop_column('interviews', 'final_decision')
    postgresql.ENUM(name='final_decision').drop(op.get_bind(), checkfirst=True)
