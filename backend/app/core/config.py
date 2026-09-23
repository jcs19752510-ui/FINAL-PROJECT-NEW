"""환경변수 기반 설정. 시크릿을 코드에 하드코딩하지 않는다 (게이트2 체크리스트)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    # unit-7(REQ-007): Celery 브로커/백엔드 + WS push용 Redis pub/sub (03-design §1.3/§2.1).
    # unit-7 재작업(DEF-011/DEC-035 Q2): docker-compose.yml의 `--requirepass`와 짝을
    # 맞춰 기본값에도 인증정보를 포함한다(로컬 개발 전용 placeholder, 위 파일 주석 참고).
    redis_url: str = "redis://:final_redis_pw@localhost:6389/0"
    # 운영(Nginx TLS 종단, 03-system-design.md §6.4)에서는 반드시 True.
    # 로컬 개발 서버가 http인 동안은 브라우저가 Secure 쿠키를 저장하지 않으므로 False로 둔다.
    cookie_secure: bool = True
    # unit-25(원안 REQ-N-003 축소판, 저장 시 AES-256 암호화, 2026-09-22 사용자 승인):
    # base64 인코딩된 32바이트 키(app/services/field_encryption.py). 로컬 개발 전용
    # 플레이스홀더 — 운영 배포 전 반드시 KMS/Vault 등 안전한 키 관리로 교체 필요.
    field_encryption_key: str = "3Rc9k21J4zYUNiDgSlmcPrFpZ2ESFUzeK9aEN16oyUU="
    # unit-37(03-system-design v4 §4.6, 2026-09-23 기준선 실측 결함 해소): 리포트
    # 생성은 턴 응답(25초 고정)과 제한시간을 공유하면 저사양 환경(GPU 없는 PC 등)에서
    # 항상 타임아웃으로 실패한다(unit-37-test.md 기준선 실측). 리포트는 비동기 job이라
    # 여유를 둔다.
    llm_report_timeout_seconds: int = 300
    # unit-32/DEC-057(2026-09-23, 사용자 제공 키로 실측 검증): 벤더 어댑터는
    # `app/services/stt_adapter_deepgram.py`/`tts_adapter_elevenlabs.py`/
    # `whiteboard_vision.py`에 함수로만 존재하고 아직 어떤 API 엔드포인트에도
    # 배선되지 않았다(운영 경로는 여전히 로컬 faster-whisper/Piper, DEC-005).
    # 키가 없으면 None — 미검증 상태를 코드로도 드러낸다(가짜 진행률 금지 원칙).
    deepgram_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    openai_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
