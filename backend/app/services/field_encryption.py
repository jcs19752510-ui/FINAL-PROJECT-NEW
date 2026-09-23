"""저장 시 암호화(AES-256, 원안 REQ-N-003 축소판) — 2026-09-22 사용자 승인
(unit-25, `docs/harness/units/unit-25-note.md` 참고).

원 계획서(§3.2.2)는 "모든 데이터는 ... 저장 시(AES-256) 암호화되어야 한다"고
명시했다. 이 모듈은 컬럼 단위 투명 암호화(SQLAlchemy `TypeDecorator`) 인프라를
제공한다 — "모든" 컬럼에 소급 적용하지는 않았다(범위/사유는 unit-25-note.md 참고,
특히 `TRANSCRIPTS.content_text`는 별개로 발견된 인코딩 손상 결함 조사가 먼저
선행되어야 해 이번 범위에서 제외).

[2026-09-23 정정, DEC-051] 위 "인코딩 손상 결함"은 재조사 결과 오탐으로
판정됨(실제 데이터 손상 없음, 콘솔 표시 오류였음) — 상세는
docs/harness/decisions.md DEC-051, unit-25-note.md 정정 주석 참고. 암호화
범위 확대는 후속 유닛으로 별도 진행.

**알고리즘**: AES-256-GCM(`cryptography.hazmat.primitives.ciphers.aead.AESGCM`,
32바이트 키 — 문자 그대로 "AES-256"). GCM은 인증 태그를 포함해 변조도 함께
탐지한다(단순 CBC보다 안전한 기본 선택, 구현 세부값이나 되돌리기 쉬움).

**키 관리**: `FIELD_ENCRYPTION_KEY` 환경변수(base64, 32바이트 디코딩 결과)를
`app/core/config.py`에서 읽는다. 로컬 개발 전용 플레이스홀더 키가 `.env`에
있으며, **실제 운영 배포 전 반드시 안전한 키 관리 시스템(KMS/Vault 등)으로
교체해야 한다** — 이 모듈 자체는 어떤 키 관리 시스템을 쓰든 `bytes` 32개만 받으면
동작하므로 교체는 설정값 변경만으로 가능하다.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

_NONCE_BYTES = 12  # AESGCM 표준 논스 길이


class FieldEncryptionError(Exception):
    """키 형식 오류, 복호화 실패(변조/키 불일치) 등을 단일 계약으로 승격한다."""


def _get_aesgcm() -> AESGCM:
    from app.core.config import settings  # 지연 임포트 — 순환 임포트 방지

    try:
        key = base64.b64decode(settings.field_encryption_key)
    except Exception as exc:  # noqa: BLE001
        raise FieldEncryptionError("FIELD_ENCRYPTION_KEY가 올바른 base64 값이 아닙니다.") from exc
    if len(key) != 32:
        raise FieldEncryptionError(
            f"FIELD_ENCRYPTION_KEY는 디코딩 후 정확히 32바이트여야 합니다(현재 {len(key)}바이트)."
        )
    return AESGCM(key)


def encrypt_field(plaintext: str) -> str:
    """평문을 AES-256-GCM으로 암호화해 `base64(nonce || ciphertext_with_tag)`로 반환한다."""
    aesgcm = _get_aesgcm()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_field(encoded: str) -> str:
    """`encrypt_field()`가 만든 값을 원문으로 복호화한다. 변조/키 불일치 시
    `FieldEncryptionError`를 낸다(인증 태그 검증 실패, GCM의 무결성 보장).
    """
    aesgcm = _get_aesgcm()
    try:
        raw = base64.b64decode(encoded)
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001 — cryptography의 다양한 하위 예외를 단일 계약으로 승격
        raise FieldEncryptionError("복호화에 실패했습니다(변조 또는 키 불일치 가능성).") from exc
    return plaintext.decode("utf-8")


class EncryptedString(TypeDecorator):
    """String 컬럼을 저장 시 투명하게 AES-256-GCM 암호화한다. DB에는 항상
    ciphertext(base64)만 저장되고, ORM을 통해 읽으면 자동으로 평문 str을 받는다
    — 호출부 코드는 일반 `String` 컬럼처럼 다루면 된다.

    암호화 오버헤드(논스 12B + GCM 태그 16B + base64 팽창 약 4/3배) 때문에 실제
    저장 폭은 평문보다 넉넉히 커야 한다 — `impl`의 길이는 이 오버헤드를 감안해
    호출부가 지정한다(예: 평문 64자 컬럼 → `EncryptedString(255)`).
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_field(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return decrypt_field(value)
