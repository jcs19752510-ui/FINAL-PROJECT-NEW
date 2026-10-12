"""RAG 질문은행 검색(app/services/rag_engine.py) 내부 테스트 — 실제 PostgreSQL + pgvector 로 SQL 경로를 검증한다.
임베딩 모델(sentence-transformers)은 이 환경에서 내려받을 수 없어, 결정적 가짜 임베더(키워드 → 벡터)로 대체한다.
따라서 이 파일이 검증하는 것은 "검색/필터/MMR/임계치/시드/그래프 연동 로직"이고 "임베딩 모델의 의미 품질"이 아니다
(후자는 `python -m app.services.rag_healthcheck` 를 모델이 있는 PC 에서 실행해 확인).
사전 조건: DATABASE_URL 이 pgvector 확장이 설치된 DB 를 가리킬 것."""

import numpy as np
import pytest
from sqlalchemy import text

from tests.turn_graph import stubs

stubs.install()

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.question import EMBEDDING_DIM, Question, QuestionCategory, QuestionSource  # noqa: E402
from app.services import rag_engine, seed_questions, turn_graph  # noqa: E402

# 키워드 → 차원 매핑. 같은 키워드를 가진 문장끼리만 유사해지는 결정적 임베더.
KEYWORDS = ["MSA", "트랜잭션", "테스트", "CI/CD", "장애", "갈등", "일정", "실수", "학습", "협업", "자기소개"]


def fake_embed(text_: str) -> list[float]:
    v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    for i, kw in enumerate(KEYWORDS):
        if kw in text_:
            v[i] = 1.0
    if not v.any():
        v[EMBEDDING_DIM - 1] = 1.0  # 어느 키워드와도 무관한 문장
    return (v / np.linalg.norm(v)).tolist()


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    monkeypatch.setattr(rag_engine, "embed_text", fake_embed)
    monkeypatch.setattr(seed_questions, "embed_text", fake_embed)
    Question.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM questions"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM questions"))


def _add(db, content, category=QuestionCategory.technical):
    q = Question(
        content=content,
        category=category,
        difficulty="easy",
        rubric_json={},
        embedding=fake_embed(content),
        source=QuestionSource.bank,
    )
    db.add(q)
    db.commit()
    return q


def test_rag01_empty_bank_returns_empty():
    with SessionLocal() as db:
        assert rag_engine.search_similar_questions(db, "MSA 전환 경험") == []


def test_rag02_most_similar_first():
    with SessionLocal() as db:
        _add(db, "MSA 전환의 어려움은?")
        _add(db, "트랜잭션 정합성은 어떻게?")
        _add(db, "일정 우선순위는?", QuestionCategory.behavioral)
        got = rag_engine.search_similar_questions(db, "MSA 로 옮기면서", top_k=1)
        assert [q.content for q in got] == ["MSA 전환의 어려움은?"]


def test_rag03_category_filter_opening_only():
    with SessionLocal() as db:
        _add(db, "간단히 자기소개 해 주세요.", QuestionCategory.opening)
        _add(db, "MSA 전환의 어려움은?")
        got = rag_engine.search_similar_questions(
            db, "면접 시작 오프닝 자기소개", category=QuestionCategory.opening, top_k=1
        )
        assert len(got) == 1 and got[0].category == QuestionCategory.opening


def test_rag04_exclude_opening_for_followups():
    with SessionLocal() as db:
        _add(db, "간단히 자기소개 해 주세요.", QuestionCategory.opening)
        _add(db, "자기소개 이후 협업 경험은?")
        got = rag_engine.search_similar_questions(
            db, "자기소개", exclude_categories={QuestionCategory.opening}, top_k=3
        )
        assert all(q.category != QuestionCategory.opening for q in got) and len(got) == 1


def test_rag05_min_similarity_drops_unrelated():
    with SessionLocal() as db:
        _add(db, "MSA 전환의 어려움은?")
        assert rag_engine.search_similar_questions(db, "오늘 점심 뭐 먹지", min_similarity=0.30) == []
        assert len(rag_engine.search_similar_questions(db, "MSA", min_similarity=0.30)) == 1


def test_rag06_mmr_prefers_diverse_second_pick():
    with SessionLocal() as db:
        _add(db, "MSA 전환의 어려움은?")
        _add(db, "MSA 전환 후 운영 이슈는?")  # 첫 번째와 거의 동일 주제
        _add(db, "MSA 와 트랜잭션 정합성은?")  # 질의와 부분 유사 + 다른 주제 포함
        got = rag_engine.search_similar_questions(db, "MSA", top_k=2)
        contents = [q.content for q in got]
        assert len(contents) == 2 and len(set(contents)) == 2


def test_rag07_top_k_bounded_by_available():
    with SessionLocal() as db:
        _add(db, "MSA 전환의 어려움은?")
        assert len(rag_engine.search_similar_questions(db, "MSA", top_k=5)) == 1


def test_rag08_retriever_wrapper_documents_and_last_questions():
    with SessionLocal() as db:
        q = _add(db, "MSA 전환의 어려움은?")
        r = turn_graph.QuestionBankRetriever(db=db, exclude_categories={QuestionCategory.opening}, top_k=3)
        docs = r.invoke("MSA")
        assert [d.page_content for d in docs] == [q.content]
        assert docs[0].metadata == {"question_id": str(q.id), "category": "technical"}
        assert [x.id for x in r.last_questions] == [q.id]


def test_rag09_graph_with_real_db_links_question_id_and_prompt():
    from app.models.question import QuestionCategory as C
    from app.services.llm_engine import TurnLLMOutput

    with SessionLocal() as db:
        q = _add(db, "분산 트랜잭션 정합성은 어떻게 보장했나요?")
        seen = {}

        def gen(system_prompt, user_message):
            seen["sys"] = system_prompt
            return TurnLLMOutput(speak_text="그 방식을 선택한 이유는 무엇이었나요?")

        res = turn_graph.run_followup_graph(
            db,
            query_text="트랜잭션 문제를 겪었습니다",
            user_message="u",
            min_similarity=0.30,
            on_persona_leak=lambda t: None,
            turn_fallback_text="폴백",
            generate=gen,
        )
        assert [c.id for c in res.candidates] == [q.id] and q.content in seen["sys"]
        assert res.trace == ["retrieve", "generate", "validate"]
        assert all(c.category != C.opening for c in res.candidates)


def test_rag10_graph_real_db_bank_fallback_uses_db_question():
    from app.services.llm_engine import TurnLLMOutput

    with SessionLocal() as db:
        q = _add(db, "CI/CD 파이프라인 개선 경험을 설명해 주세요.")
        res = turn_graph.run_followup_graph(
            db,
            query_text="CI/CD 를 개선했습니다",
            user_message="u",
            min_similarity=0.30,
            on_persona_leak=lambda t: None,
            turn_fallback_text="폴백",
            generate=lambda s, u: TurnLLMOutput(speak_text="알겠습니다 감사합니다"),
        )
        assert res.used_bank_fallback and res.output.speak_text == q.content and res.generations == 2


def test_rag11_seed_inserts_all_and_is_idempotent():
    assert len(seed_questions.SEED_QUESTIONS) == 15
    first = seed_questions.seed()
    second = seed_questions.seed()
    assert first == 15 and second == 0
    with SessionLocal() as db:
        cats = [q.category for q in db.query(Question).all()]
    assert cats.count(QuestionCategory.opening) == 1 and len(cats) == 15


def test_rag12_opening_selection_after_seed():
    seed_questions.seed()
    with SessionLocal() as db:
        got = rag_engine.search_similar_questions(
            db, query_text="면접 시작 오프닝 자기소개", category=QuestionCategory.opening, top_k=1
        )
    assert len(got) == 1 and "자기소개" in got[0].content


def test_rag13_pgvector_dimension_enforced():
    with SessionLocal() as db:
        db.add(
            Question(
                content="x",
                category=QuestionCategory.technical,
                difficulty="easy",
                rubric_json={},
                embedding=[0.1] * 10,
                source=QuestionSource.bank,
            )
        )
        with pytest.raises(Exception):  # noqa: B017 — DB 드라이버 예외 종류에 의존하지 않고 차원 위반이 거부되는지만 본다
            db.commit()


def test_rag14_graph_never_returns_opening_question_as_followup_candidate():
    """그래프의 검색 노드는 opening 카테고리를 반드시 제외한다(DEF-007 재발 방지) — 질의와 가장 유사해도 제외."""
    from app.services.llm_engine import TurnLLMOutput

    with SessionLocal() as db:
        _add(db, "간단히 자기소개 해 주세요.", QuestionCategory.opening)
        tech = _add(db, "협업 중 갈등 해결 경험을 말씀해 주세요.", QuestionCategory.behavioral)
        res = turn_graph.run_followup_graph(
            db,
            query_text="자기소개",
            user_message="u",
            min_similarity=None,
            on_persona_leak=lambda t: None,
            turn_fallback_text="폴백",
            generate=lambda s, u: TurnLLMOutput(speak_text="그 경험은 어땠나요?"),
        )
        assert all(c.category != QuestionCategory.opening for c in res.candidates)
        assert res.candidates == [] or res.candidates[0].id == tech.id
