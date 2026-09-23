"""루브릭 시스템 기본 템플릿 상수 (03-system-design.md v4 §4.6 (1), unit-37).

alembic/versions/e6a1b8f4d2c7_v15_rubric_scoring.py가 시드하는 행의 id와 반드시
일치해야 한다 — 마이그레이션과 애플리케이션 코드 양쪽에서 같은 값을 하드코딩하는
대신 이 상수 하나를 두 곳이 참조하면 더 안전하지만, alembic 리비전은 관례상 미래
버전의 애플리케이션 코드에 의존하지 않는다(리비전 파일은 그 시점의 스냅샷). 그래서
값은 두 곳에 고정 문자열로 각각 두되, 06단계가 두 값이 같은지 테스트로 확인한다.
"""
import uuid

SYSTEM_DEFAULT_RUBRIC_TEMPLATE_ID = uuid.UUID("f50c128a-c09a-4bd6-9f25-4fa6d75cc57a")
