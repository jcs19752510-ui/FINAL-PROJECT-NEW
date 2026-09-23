"""v12_transcript_prosody

원안(REQ-018/019 축소판, 음성 Prosody 분석) — 2026-09-22 사용자 승인.

Revision ID: b3f8d2a916c5
Revises: a7c3e9f14b02
Create Date: 2026-09-22 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3f8d2a916c5'
down_revision: Union[str, None] = 'a7c3e9f14b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transcripts',
        sa.Column('prosody_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('transcripts', 'prosody_json')
