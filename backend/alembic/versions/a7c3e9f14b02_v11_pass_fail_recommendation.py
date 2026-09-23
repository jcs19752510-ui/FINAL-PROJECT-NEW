"""v11_pass_fail_recommendation

원안(REQ-F-006/007) 복원분 — 2026-09-22 사용자 명시 승인, REQ-031과 긴장 관계
(app/models/evaluation_report.py 모듈 docstring 참고, 배포 전 법무 검토 필요).

Revision ID: a7c3e9f14b02
Revises: 9c91a685f9df
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f14b02'
down_revision: Union[str, None] = '9c91a685f9df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# unit-1 선례(v10 create_table)와 달리 add_column은 종속 ENUM 타입을 자동
# 생성해주지 않는다(2026-09-22 실측: `type "pass_fail_recommendation" does not
# exist`) — CREATE TYPE을 add_column 이전에 명시적으로 실행해야 한다.
pass_fail_enum = postgresql.ENUM('pass', 'fail', 'borderline', name='pass_fail_recommendation')


def upgrade() -> None:
    pass_fail_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'evaluation_reports',
        sa.Column('pass_fail_recommendation', pass_fail_enum, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('evaluation_reports', 'pass_fail_recommendation')
    pass_fail_enum.drop(op.get_bind(), checkfirst=True)
