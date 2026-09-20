"""RAG 질문은행 검색 (REQ-007, 03-system-design.md §2.4/§3.1).

임베딩 모델: sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`
(384차원, 다국어 지원 — 한국어 포함, 약 470MB). CPU에서 실행되며 GPU(llama-server가
점유)를 전혀 사용하지 않는다(unit-7-note.md §6 실측: 로드 약 18초 1회성, 인코딩은
문장당 수십 ms). 프로세스당 1회만 로드하는 모듈 전역 싱글턴이다(stt_engine.py와
동일 패턴).

MMR(Maximal Marginal Relevance)로 검색 결과의 다양성을 확보한다(03-design §2.4
"MMR로 다양성 확보, 원 계획서 §5.1.1 전략 계승") — pgvector 코사인 거리로 상위
pool_size개를 우선 조회한 뒤, 이미 선택된 후보와 너무 유사한 질문이 중복
추천되지 않도록 다양성 점수를 반영해 최종 top_k개를 순차 선택한다.

03-design §2.1: MVP 질문은행 규모(수천 건 이하)에서는 별도 ANN 인덱스(ivfflat/hnsw)
없이 pgvector의 순차 코사인 거리 연산자(`<=>`)만으로 충분하다(과설계 방지).
"""
import threading

import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionCategory

_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model_lock = threading.Lock()
_model: SentenceTransformer | None = None


def _get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """정규화된(코사인 유사도 = 내적) 임베딩 벡터를 반환한다."""
    model = _get_embedding_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def _mmr_select(
    candidates: list[tuple[Question, np.ndarray, float]],
    k: int,
    lambda_param: float = 0.5,
) -> list[Question]:
    """candidates: (question, embedding, query와의 유사도) 리스트에서 MMR로 k개 선택.

    lambda_param이 클수록 관련성(query 유사도)을, 작을수록 다양성(이미 선택된
    후보와의 비유사성)을 더 우선한다. 05-planning 원 계획서 §5.1.1과 동일하게
    0.5(균형)를 기본값으로 둔다 — 설계서 미명시 구현 세부값, 상수 하나로 격리.
    """
    selected: list[Question] = []
    selected_vecs: list[np.ndarray] = []
    pool = list(candidates)
    while pool and len(selected) < k:
        best_idx = -1
        best_score = float("-inf")
        for idx, (_q, vec, sim_query) in enumerate(pool):
            if selected_vecs:
                max_sim_selected = max(float(np.dot(vec, sv)) for sv in selected_vecs)
            else:
                max_sim_selected = 0.0
            mmr_score = lambda_param * sim_query - (1 - lambda_param) * max_sim_selected
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        chosen = pool.pop(best_idx)
        selected.append(chosen[0])
        selected_vecs.append(chosen[1])
    return selected


def search_similar_questions(
    db: Session,
    query_text: str,
    category: QuestionCategory | None = None,
    top_k: int = 3,
    pool_size: int = 10,
) -> list[Question]:
    """현재 대화 맥락(query_text)과 유사한 질문은행 항목을 검색한다.

    LLM에게는 이 함수의 반환값(질문 텍스트)만 "읽기 전용" 컨텍스트로 주입되며,
    LLM이 직접 이 함수나 DB에 접근할 권한은 없다(03-design §6.3 도구권한 최소화,
    REQ-037 — 실제 강제는 unit-8 범위이나 이 아키텍처 자체가 그 전제를 충족한다).
    """
    query_vec = np.array(embed_text(query_text), dtype=np.float32)

    stmt = select(Question)
    if category is not None:
        stmt = stmt.where(Question.category == category)
    stmt = stmt.order_by(Question.embedding.cosine_distance(query_vec.tolist())).limit(pool_size)
    pool_questions = list(db.scalars(stmt).all())
    if not pool_questions:
        return []

    candidates: list[tuple[Question, np.ndarray, float]] = []
    for q in pool_questions:
        vec = np.array(q.embedding, dtype=np.float32)
        similarity = float(np.dot(query_vec, vec))
        candidates.append((q, vec, similarity))

    return _mmr_select(candidates, k=min(top_k, len(candidates)))
