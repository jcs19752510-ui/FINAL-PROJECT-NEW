"""v9_transcripts_unique_turn_index

Revision ID: f2a9c4d81e36
Revises: e4b6a1c9f2d7
Create Date: 2026-09-20 22:40:00.000000

unit-7 재작업(DEF-002/DEC-035 Q5): 오프닝 AI 턴(turn_index=0 하드코딩)과 사용자/AI
턴(건수 기반 채번)이 서로 다른 방식으로 번호를 매겨, 오프닝 완료 전 사용자가 답변을
제출하면 turn_index가 중복되는 결함이 실측으로 확인됐다(unit-7-test.md TC-030).
`(interview_id, turn_index)` 유니크 제약을 DB 레벨 최종 방어선으로 추가하고,
애플리케이션 레벨 채번은 `app/services/turn_numbering.py`(MAX+1 계산 +
IntegrityError 재시도)로 통일한다. 적용 시점 기준 `transcripts` 0건이라(실측
확인) 기존 데이터 마이그레이션/정리는 필요 없다.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2a9c4d81e36'
down_revision: Union[str, None] = 'e4b6a1c9f2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_transcripts_interview_id_turn_index',
        'transcripts',
        ['interview_id', 'turn_index'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_transcripts_interview_id_turn_index', 'transcripts', type_='unique')
