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
    # 운영(Nginx TLS 종단, 03-system-design.md §6.4)에서는 반드시 True.
    # 로컬 개발 서버가 http인 동안은 브라우저가 Secure 쿠키를 저장하지 않으므로 False로 둔다.
    cookie_secure: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
