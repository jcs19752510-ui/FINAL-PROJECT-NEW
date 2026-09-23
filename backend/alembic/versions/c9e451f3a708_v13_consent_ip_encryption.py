"""v13_consent_ip_encryption

원안(REQ-N-003 축소판, 저장 시 AES-256 암호화) — 2026-09-22 사용자 승인.

`consents.ip_address`를 64→255자로 넓히고, **기존 평문 IP 값을 전부 같은
AES-256-GCM 키로 암호화해 덮어쓴다** — 스키마만 바꾸고 기존 행을 그대로 두면
`EncryptedString`이 평문을 암호문으로 오인해 복호화 시도 시 전부
`FieldEncryptionError`가 발생한다(실측 확인 필요 없이 알고리즘 설계상 자명 —
GCM은 태그 검증에 실패하면 예외를 던진다). 699건(2026-09-22 기준) 실측 확인 후
작성.

Revision ID: c9e451f3a708
Revises: b3f8d2a916c5
Create Date: 2026-09-22 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9e451f3a708'
down_revision: Union[str, None] = 'b3f8d2a916c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # field_encryption 모듈을 마이그레이션 시점에 import — alembic/env.py가 app 패키지를
    # 이미 sys.path에 올려두므로(기존 마이그레이션들의 관례와 동일하게 app.* import 가능).
    from app.services.field_encryption import encrypt_field

    op.alter_column('consents', 'ip_address', type_=sa.String(255), existing_type=sa.String(64))

    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id, ip_address FROM consents WHERE ip_address IS NOT NULL')).fetchall()
    for row_id, plaintext_ip in rows:
        conn.execute(
            sa.text('UPDATE consents SET ip_address = :enc WHERE id = :id'),
            {'enc': encrypt_field(plaintext_ip), 'id': row_id},
        )


def downgrade() -> None:
    # 복호화해 평문으로 되돌린 뒤 컬럼 폭을 원복한다(대칭적 다운그레이드 — 규칙 K/
    # 롤백 안전성 원칙에 따라 downgrade도 실제로 동작하도록 작성).
    from app.services.field_encryption import decrypt_field

    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id, ip_address FROM consents WHERE ip_address IS NOT NULL')).fetchall()
    for row_id, encrypted_ip in rows:
        conn.execute(
            sa.text('UPDATE consents SET ip_address = :plain WHERE id = :id'),
            {'plain': decrypt_field(encrypted_ip), 'id': row_id},
        )

    op.alter_column('consents', 'ip_address', type_=sa.String(64), existing_type=sa.String(255))
