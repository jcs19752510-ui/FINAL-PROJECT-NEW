"""v14_consent_lawful_basis

원안 확장(GDPR 제6조 적법근거 기록, unit-34) — 2026-09-23 사용자 승인.

unit-23(v11)에서 실측한 교훈 그대로: enum 타입을 `add_column` 전에 명시적으로
`CREATE TYPE`해야 한다(안 그러면 `type "lawful_basis" does not exist` 발생).

Revision ID: d4f7b2c8a913
Revises: c9e451f3a708
Create Date: 2026-09-23 00:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4f7b2c8a913'
down_revision: Union[str, None] = 'c9e451f3a708'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

lawful_basis_enum = postgresql.ENUM(
    'consent', 'contract', 'legal_obligation', 'vital_interests', 'public_task', 'legitimate_interests',
    name='lawful_basis',
)


def upgrade() -> None:
    lawful_basis_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'consents',
        sa.Column('lawful_basis', lawful_basis_enum, nullable=False, server_default='consent'),
    )


def downgrade() -> None:
    op.drop_column('consents', 'lawful_basis')
    lawful_basis_enum.drop(op.get_bind(), checkfirst=True)
