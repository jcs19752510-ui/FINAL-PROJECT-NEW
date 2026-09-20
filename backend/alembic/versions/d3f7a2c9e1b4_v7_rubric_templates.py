"""v7_rubric_templates

Revision ID: d3f7a2c9e1b4
Revises: b84a71b986c5
Create Date: 2026-09-19 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd3f7a2c9e1b4'
down_revision: Union[str, None] = 'b84a71b986c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rubric_templates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('recruiter_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('criteria_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['recruiter_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rubric_templates_recruiter_id'), 'rubric_templates', ['recruiter_id'], unique=False)

    # unit-2가 만든 interviews.rubric_template_id는 FK 제약 없이 nullable 컬럼만
    # 존재했다(app/models/interview.py 모듈 docstring 참고) — 이제 RUBRIC_TEMPLATES가
    # 생겼으므로 FK 제약을 추가한다.
    op.create_foreign_key(
        'fk_interviews_rubric_template_id',
        'interviews', 'rubric_templates',
        ['rubric_template_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_interviews_rubric_template_id', 'interviews', type_='foreignkey')
    op.drop_index(op.f('ix_rubric_templates_recruiter_id'), table_name='rubric_templates')
    op.drop_table('rubric_templates')
