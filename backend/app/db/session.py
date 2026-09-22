from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# 장애 대응(2026-09-22): 기본값(pool_size=5, max_overflow=10, 총 15)이 WS 연결 +
# 면접장 화면의 백그라운드 재확인 폴링(GET /transcripts) + 동시 다중 탭/E2E 부하가
# 겹치면 쉽게 소진되어 신규 요청이 커넥션을 영원히 기다리며 응답 없는 상태(hang)로
# 보일 수 있음이 실측됨(로그인 완전 무응답 장애). 로컬/소규모 배포 기준으로 여유를
# 늘린다 — 근본적으로는 동시 접속자 규모에 맞춘 운영 튜닝이 별도로 필요하다(인수인계).
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20, pool_timeout=30)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
