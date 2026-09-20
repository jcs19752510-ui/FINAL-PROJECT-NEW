"""v5_whiteboard_snapshots

Revision ID: c1a2f5e9b7d3
Revises: 8a55fda78a42
Create Date: 2026-09-19 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1a2f5e9b7d3'
down_revision: Union[str, None] = '8a55fda78a42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('whiteboard_snapshots',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interview_id', sa.UUID(), nullable=False),
    sa.Column('canvas_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_whiteboard_snapshots_interview_id'), 'whiteboard_snapshots', ['interview_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_whiteboard_snapshots_interview_id'), table_name='whiteboard_snapshots')
    op.drop_table('whiteboard_snapshots')
