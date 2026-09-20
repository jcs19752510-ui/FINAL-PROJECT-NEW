"""QUESTIONS(RAG 질문은행) 초기 시드 데이터 (REQ-007, 03-system-design.md §3.3
"시드 데이터는 별도 시드 스크립트로 관리하고 마이그레이션과 분리한다").

**출처 확인(§2.4 "확인 필요" 이행)**: 아래 질문들은 특정 기업의 저작권 있는 실제
기출문제를 수집한 것이 아니라, 일반적인 기술/행동 면접에서 통용되는 주제(MSA,
트랜잭션, 성능튜닝, 협업, 갈등해결 등)를 이 작업 단위가 직접 새로 작성한
자체 제작 질문이다 — 03-design §2.4가 요구한 "출처 확인 불가 시 자체 제작으로
대체" 원칙을 그대로 따른다.

실행 방법: `python -m app.services.seed_questions` (Alembic 마이그레이션과 별개,
직접 실행하는 1회성 스크립트). 이미 존재하는 콘텐츠는 건너뛰어 재실행해도
중복 삽입되지 않는다(`content` 텍스트 기준 존재 여부 확인).
"""
import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.question import Question, QuestionCategory, QuestionSource
from app.services.rag_engine import embed_text

logger = logging.getLogger(__name__)

SEED_QUESTIONS: list[dict] = [
    # --- opening (면접 시작 오프닝, category=opening) ---
    {
        "content": "간단히 자기소개와 함께, 최근에 가장 몰입해서 진행했던 프로젝트를 소개해 주세요.",
        "category": QuestionCategory.opening,
        "difficulty": "easy",
    },
    # --- technical ---
    {
        "content": "MSA(마이크로서비스 아키텍처)로 전환하며 겪은 가장 큰 기술적 어려움은 무엇이었나요?",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    {
        "content": "분산 트랜잭션 환경에서 여러 서비스 간 데이터 정합성을 어떻게 보장했나요?",
        "category": QuestionCategory.technical,
        "difficulty": "hard",
    },
    {
        "content": "Saga 패턴과 2PC(Two-Phase Commit)의 차이를 설명하고, 실무에서 어떤 기준으로 선택했나요?",
        "category": QuestionCategory.technical,
        "difficulty": "hard",
    },
    {
        "content": "데이터베이스 쿼리 성능이 저하되었을 때 어떤 절차로 원인을 진단하고 개선했나요?",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    {
        "content": "캐시(Redis 등)를 도입할 때 캐시 무효화(invalidation) 전략을 어떻게 설계했나요?",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    {
        "content": "동시성 문제(레이스 컨디션)를 실제로 겪고 해결한 경험이 있다면 설명해 주세요.",
        "category": QuestionCategory.technical,
        "difficulty": "hard",
    },
    {
        "content": "테스트 코드(단위/통합 테스트)를 작성할 때 커버리지와 실효성 사이에서 어떤 기준을 두나요?",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    {
        "content": "CI/CD 파이프라인을 구축하거나 개선한 경험이 있다면, 어떤 문제를 해결했는지 설명해 주세요.",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    {
        "content": "장애 발생 시 원인을 파악하기 위해 어떤 모니터링/로깅 체계를 활용했나요?",
        "category": QuestionCategory.technical,
        "difficulty": "medium",
    },
    # --- behavioral ---
    {
        "content": "팀원과 기술적인 의견 충돌이 있었던 경험과 이를 어떻게 해결했는지 말씀해 주세요.",
        "category": QuestionCategory.behavioral,
        "difficulty": "medium",
    },
    {
        "content": "촉박한 일정 속에서 우선순위를 어떻게 정해 업무를 진행했는지 사례를 들어 설명해 주세요.",
        "category": QuestionCategory.behavioral,
        "difficulty": "medium",
    },
    {
        "content": "본인의 실수로 문제가 발생했던 경험과, 그 상황을 어떻게 수습했는지 이야기해 주세요.",
        "category": QuestionCategory.behavioral,
        "difficulty": "medium",
    },
    {
        "content": "새로운 기술을 빠르게 학습해서 실무에 적용해야 했던 경험이 있다면 소개해 주세요.",
        "category": QuestionCategory.behavioral,
        "difficulty": "easy",
    },
    {
        "content": "다른 직군(기획, 디자인 등)과 협업하며 어려움을 겪었던 경험과 해결 방법을 설명해 주세요.",
        "category": QuestionCategory.behavioral,
        "difficulty": "medium",
    },
]


def seed() -> int:
    db = SessionLocal()
    inserted = 0
    try:
        existing_contents = set(db.scalars(select(Question.content)).all())
        for item in SEED_QUESTIONS:
            if item["content"] in existing_contents:
                continue
            embedding = embed_text(item["content"])
            question = Question(
                content=item["content"],
                category=item["category"],
                difficulty=item["difficulty"],
                rubric_json={},
                embedding=embedding,
                source=QuestionSource.bank,
            )
            db.add(question)
            inserted += 1
        db.commit()
        logger.info("질문은행 시드 완료: 신규 %d건 삽입", inserted)
        return inserted
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
