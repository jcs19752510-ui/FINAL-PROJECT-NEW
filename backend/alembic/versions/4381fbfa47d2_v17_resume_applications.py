"""v17_resume_applications

Revision ID: 4381fbfa47d2
Revises: f1a3c7e92b04
Create Date: 2026-09-29 20:37:22.685245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4381fbfa47d2'
down_revision: Union[str, None] = 'f1a3c7e92b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 참고(b84a71b986c5_v6_code_submissions.py의 동일 경고와 같은 사유):
# `--autogenerate`가 이 유닛과 무관한 기존 드리프트 2건(interviews.rubric_template_id의
# FK, transcripts의 (interview_id,turn_index) unique 제약 — 둘 다 현재 모델 파일에는
# 선언되어 있지 않지만 실제 DB에는 존재하는 것으로 감지됨, DEF-010류 기존 갭)을
# "제거 대상"으로 오탐지했다. 이 마이그레이션은 resume_applications 신설만 책임지므로
# 그 두 건은 자동생성 결과에서 수동으로 제거했다 — 기존 DB 제약을 건드리지 않는다.


def upgrade() -> None:
    op.create_table('resume_applications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('candidate_id', sa.UUID(), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'accepted', 'rejected', name='resume_application_status'), server_default='pending', nullable=False),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('interview_schedule_note', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resume_applications_candidate_id'), 'resume_applications', ['candidate_id'], unique=True)
    # unit-14/15 패턴(신규 ConsentType은 기존 native enum에 값을 추가): PG12+는
    # 트랜잭션 내 ALTER TYPE ... ADD VALUE를 허용하되, 그 값을 "같은 트랜잭션 안에서"
    # 즉시 사용(INSERT 등)할 수는 없다 — 이 마이그레이션은 추가만 하고 사용하지
    # 않으므로 안전하다.
    op.execute("ALTER TYPE consent_type ADD VALUE IF NOT EXISTS 'resume_submission'")


def downgrade() -> None:
    # PostgreSQL은 enum에서 값을 제거하는 기능을 제공하지 않는다(타입 재생성 필요) —
    # 이 프로젝트의 다른 enum 확장 마이그레이션에도 선례가 없어, 여기서도 안전하게
    # "값은 되돌리지 않고 테이블만 되돌린다"로 처리한다(구현 세부값, 비가역성 낮음 —
    # 실제 downgrade가 필요해지면 그때 enum 재생성 절차를 별도로 설계).
    op.drop_index(op.f('ix_resume_applications_candidate_id'), table_name='resume_applications')
    op.drop_table('resume_applications')
