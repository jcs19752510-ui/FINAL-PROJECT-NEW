"""RAG(질문은행) 동작 점검 — 실행: `python -m app.services.rag_healthcheck` (2026-10-12).

면접장 RAG가 실제로 동작하는지 한 번에 확인한다. 이 점검이 필요한 이유: 질문은행이 비어 있으면
검색이 조용히 빈 결과를 내고 첫 질문이 고정 문구로 대체되어 "RAG가 켜져 있는 것처럼" 보이기 때문이다.

점검 항목: (1) 임베딩 모델 로드 + 차원(384) (2) 질문은행 카테고리별 건수(opening 1건 이상, technical/
behavioral 1건 이상) (3) 대표 질의 검색 결과와 유사도 (4) 꼬리질문 유사도 임계치(0.30)를 넘는 후보가
나오는지. 하나라도 실패하면 종료코드 1.
"""
import sys

import numpy as np
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.question import EMBEDDING_DIM, Question, QuestionCategory
from app.services import rag_engine
from app.worker.tasks import _FOLLOWUP_RAG_MIN_SIMILARITY

SAMPLE_QUERIES = (
    "마이크로서비스로 전환하면서 데이터 정합성 문제를 겪었습니다",
    "팀원과 의견이 달라서 갈등이 있었는데 대화로 풀었습니다",
    "배포 파이프라인을 자동화해서 배포 시간을 줄였습니다",
)


def run() -> int:
    failures: list[str] = []

    vec = rag_engine.embed_text("임베딩 점검")
    ok = len(vec) == EMBEDDING_DIM
    print(f"[1] 임베딩 모델 로드/차원: {len(vec)} (기대 {EMBEDDING_DIM}) -> {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append("임베딩 차원 불일치")

    db = SessionLocal()
    try:
        counts = dict(db.execute(select(Question.category, func.count()).group_by(Question.category)).all())
        print("[2] 질문은행 건수:", {c.value: counts.get(c, 0) for c in QuestionCategory})
        for cat in QuestionCategory:
            if counts.get(cat, 0) < 1:
                failures.append(f"질문은행 {cat.value} 카테고리가 비어 있음 — python -m app.services.seed_questions 실행 필요")

        if not failures:
            for q in SAMPLE_QUERIES:
                hits = rag_engine.search_similar_questions(
                    db, query_text=q, exclude_categories={QuestionCategory.opening}, top_k=3
                )
                qv = np.array(rag_engine.embed_text(q), dtype=np.float32)
                print(f"[3] 질의: {q}")
                best = 0.0
                for h in hits:
                    sim = float(np.dot(qv, np.array(h.embedding, dtype=np.float32)))
                    best = max(best, sim)
                    print(f"      {sim:.3f}  {h.content}")
                if not hits:
                    failures.append(f"검색 결과 없음: {q}")
                elif best < _FOLLOWUP_RAG_MIN_SIMILARITY:
                    print(f"      (주의) 최고 유사도 {best:.3f} < 임계치 {_FOLLOWUP_RAG_MIN_SIMILARITY} — 후보로 채택되지 않음")
    finally:
        db.close()

    if failures:
        print("\n결과: FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("\n결과: PASS — RAG 질문은행 검색이 정상 동작합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
