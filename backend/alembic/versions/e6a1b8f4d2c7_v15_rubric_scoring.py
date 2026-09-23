"""v15_rubric_scoring

원안 REQ-010/012 반영(03-system-design.md v4 §4.6, unit-37) — 2026-09-23 사용자
승인(DEC-054/055). 루브릭 템플릿 기반 항목별 채점을 위해 EVALUATION_REPORTS에
컬럼 3개를 추가하고, RUBRIC_TEMPLATES에 시스템 기본 템플릿 1행을 시드한다.

시스템 기본 템플릿 UUID는 이 리비전에 고정한다(재실행해도 같은 id) —
`app/services/rubric_defaults.py`의 상수와 반드시 일치해야 한다.

Revision ID: e6a1b8f4d2c7
Revises: d4f7b2c8a913
Create Date: 2026-09-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e6a1b8f4d2c7'
down_revision: Union[str, None] = 'd4f7b2c8a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_DEFAULT_TEMPLATE_ID = 'f50c128a-c09a-4bd6-9f25-4fa6d75cc57a'


def upgrade() -> None:
    op.add_column(
        'evaluation_reports',
        sa.Column('rubric_template_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'evaluation_reports',
        sa.Column('rubric_snapshot_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'evaluation_reports',
        sa.Column('criteria_scores_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        'fk_evaluation_reports_rubric_template_id',
        'evaluation_reports', 'rubric_templates',
        ['rubric_template_id'], ['id'],
        ondelete='SET NULL',
    )

    # 시스템 기본 템플릿(recruiter_id=NULL) — 03-system-design v4 §4.6 (1).
    # 기존 3축 점수(기술/의사소통/조직적합)와 같은 의미의 가중치 40/30/30으로 맞춰
    # 이 기능 도입 전후 점수가 급격히 달라지지 않게 한다.
    rubric_templates = sa.table(
        'rubric_templates',
        sa.column('id', sa.UUID()),
        sa.column('recruiter_id', sa.UUID()),
        sa.column('name', sa.String()),
        sa.column('criteria_json', postgresql.JSONB()),
    )
    op.bulk_insert(rubric_templates, [{
        'id': SYSTEM_DEFAULT_TEMPLATE_ID,
        'recruiter_id': None,
        'name': '기본 루브릭',
        'criteria_json': [
            {'name': '기술 이해도', 'weight': 40, 'description': '기술 개념의 정확성과 실무 적용 경험'},
            {'name': '의사소통', 'weight': 30, 'description': '답변의 명료함과 논리적 구조'},
            {'name': '조직 적합도', 'weight': 30, 'description': '협업 태도와 팀 상황 대응'},
        ],
    }])

    # 기존 면접(진행 전/중인 것 포함)에 템플릿이 지정돼 있지 않으면 기본 템플릿으로
    # 채운다 — §4.6 (2) "템플릿 결정 순서"의 1순위가 항상 채워지게 한다.
    op.execute(
        f"UPDATE interviews SET rubric_template_id = '{SYSTEM_DEFAULT_TEMPLATE_ID}' "
        "WHERE rubric_template_id IS NULL"
    )


def downgrade() -> None:
    op.execute(f"UPDATE interviews SET rubric_template_id = NULL WHERE rubric_template_id = '{SYSTEM_DEFAULT_TEMPLATE_ID}'")
    op.execute(f"DELETE FROM rubric_templates WHERE id = '{SYSTEM_DEFAULT_TEMPLATE_ID}'")
    op.drop_constraint('fk_evaluation_reports_rubric_template_id', 'evaluation_reports', type_='foreignkey')
    op.drop_column('evaluation_reports', 'criteria_scores_json')
    op.drop_column('evaluation_reports', 'rubric_snapshot_json')
    op.drop_column('evaluation_reports', 'rubric_template_id')
