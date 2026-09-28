"""v16_content_encryption

원안(REQ-N-003 축소판, 저장 시 AES-256 암호화) 범위 확대 — 2026-09-28 사용자
승인(DEC-078). unit-25(2026-09-22) 당시 `TRANSCRIPTS.content_text`는 "별도로
발견된 인코딩 손상 결함 조사가 먼저 선행되어야 한다"는 이유로 암호화 범위에서
제외됐으나, 그 손상 결함은 2026-09-23(DEC-051) 재조사 결과 오탐(콘솔 표시
오류일 뿐 실제 데이터 손상 없음)으로 판정돼 제외 사유 자체가 사라졌다.

이번 마이그레이션은 `TRANSCRIPTS.content_text`·`code_submissions.content`
(둘 다 이미 `Text`라 컬럼 폭 변경은 불필요) **기존 평문 값을 전부 같은
AES-256-GCM 키로 암호화해 덮어쓴다** — c9e451f3a708(consents.ip_address
암호화)와 정확히 동일한 패턴. 스키마만 바꾸고 기존 행을 그대로 두면
`EncryptedText`가 평문을 암호문으로 오인해 복호화 시도 시 전부
`FieldEncryptionError`가 발생한다(GCM 태그 검증 실패, 알고리즘 설계상 자명).

Revision ID: f1a3c7e92b04
Revises: e6a1b8f4d2c7
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a3c7e92b04'
down_revision: Union[str, None] = 'e6a1b8f4d2c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # field_encryption 모듈을 마이그레이션 시점에 import(기존 마이그레이션 관례와 동일).
    from app.services.field_encryption import encrypt_field

    conn = op.get_bind()

    rows = conn.execute(sa.text('SELECT id, content_text FROM transcripts')).fetchall()
    for row_id, plaintext in rows:
        conn.execute(
            sa.text('UPDATE transcripts SET content_text = :enc WHERE id = :id'),
            {'enc': encrypt_field(plaintext), 'id': row_id},
        )

    rows = conn.execute(sa.text('SELECT id, content FROM code_submissions')).fetchall()
    for row_id, plaintext in rows:
        conn.execute(
            sa.text('UPDATE code_submissions SET content = :enc WHERE id = :id'),
            {'enc': encrypt_field(plaintext), 'id': row_id},
        )


def downgrade() -> None:
    # 복호화해 평문으로 되돌린다(대칭적 다운그레이드 — 규칙 K/롤백 안전성 원칙).
    from app.services.field_encryption import decrypt_field

    conn = op.get_bind()

    rows = conn.execute(sa.text('SELECT id, content_text FROM transcripts')).fetchall()
    for row_id, encrypted in rows:
        conn.execute(
            sa.text('UPDATE transcripts SET content_text = :plain WHERE id = :id'),
            {'plain': decrypt_field(encrypted), 'id': row_id},
        )

    rows = conn.execute(sa.text('SELECT id, content FROM code_submissions')).fetchall()
    for row_id, encrypted in rows:
        conn.execute(
            sa.text('UPDATE code_submissions SET content = :plain WHERE id = :id'),
            {'plain': decrypt_field(encrypted), 'id': row_id},
        )
