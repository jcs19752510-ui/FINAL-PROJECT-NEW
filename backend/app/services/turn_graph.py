"""면접장 꼬리질문 처리 그래프 — RAG + LangChain + LangGraph (2026-10-12, 사용자 지시).

기존 `worker/tasks.py`의 `_generate_validated_followup`(검증 → 1회 재시도 → 질문은행
폴백)과 그 앞의 질문은행 검색, LLM 실패 시 안전 기본값 분기를 **동작 그대로** LangGraph
`StateGraph`의 노드/엣지로 옮긴 것이다. 새 기능이 아니라 같은 정책의 구조 변경이다.

    retrieve ─▶ generate ─▶ validate ─┬─ 통과 ──────────────▶ END
                    ▲                 ├─ 실패(재시도 남음) ──┘
                    │                 └─ 실패(재시도 소진) ─▶ bank_fallback ─▶ END
                    └─ LLM 호출 실패 ─────────────────────▶ llm_failure_default ─▶ END

- RAG: `QuestionBankRetriever`(LangChain `BaseRetriever`)가 `rag_engine`의 pgvector
  검색(MMR 포함)을 그대로 감싼다 — 검색 로직 자체는 바꾸지 않는다.
- LangChain: `langchain_orchestrator.generate_turn_via_langchain`이 llama-server를
  `ChatOpenAI`로 호출한다(서버 기동/GPU→CPU 폴백은 `llm_engine`의 검증된 로직 재사용).
- 에이전트형(도구 호출) 구조는 쓰지 않는다 — 모델이 Qwen2.5 1.5B라 함수 호출이 불안정하다.
  순서가 고정된 그래프만 사용하며 체크포인터도 쓰지 않는다(상태는 DB의 TRANSCRIPTS가 정본).
- 전환 스위치: `settings.llm_orchestration` ("graph" | "legacy"). legacy는 기존 코드 경로.
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, StateGraph
from pydantic import ConfigDict
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionCategory
from app.services import interview_prompts, rag_engine
from app.services.llm_engine import LlmGenerationError, TurnLLMOutput

logger = logging.getLogger(__name__)

# 기존 `_generate_validated_followup`과 동일: 최초 1회 + 품질 가드 실패 시 재시도 1회 = 최대 2회 생성.
MAX_GENERATIONS = 2


class QuestionBankRetriever(BaseRetriever):
    """질문은행(pgvector) 검색을 LangChain Retriever 인터페이스로 감싼다.

    LLM에는 `Document.page_content`(질문 텍스트)만 읽기 전용으로 전달된다. 그래프가
    `question_id` 기록과 폴백에 쓸 수 있도록 원본 `Question` 객체를 `last_questions`에도 둔다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    db: Any
    category: QuestionCategory | None = None
    exclude_categories: set[QuestionCategory] | None = None
    top_k: int = 3
    min_similarity: float | None = None
    last_questions: list = []

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list[Document]:
        questions = rag_engine.search_similar_questions(
            self.db,
            query_text=query,
            category=self.category,
            exclude_categories=self.exclude_categories,
            top_k=self.top_k,
            min_similarity=self.min_similarity,
        )
        self.last_questions = list(questions)
        return [
            Document(
                page_content=q.content,
                metadata={"question_id": str(q.id), "category": q.category.value},
            )
            for q in questions
        ]


class FollowupState(TypedDict, total=False):
    query_text: str
    user_message: str
    candidates: list  # list[Question]
    system_prompt: str
    output: TurnLLMOutput
    valid: bool
    generations: int
    used_bank_fallback: bool
    llm_failed: bool
    trace: list[str]


@dataclass
class FollowupResult:
    output: TurnLLMOutput
    candidates: list[Question]
    generations: int
    used_bank_fallback: bool
    llm_failed: bool
    trace: list[str] = field(default_factory=list)


def _timed(name: str, fn: Callable[[FollowupState], dict]) -> Callable[[FollowupState], dict]:
    """노드별 소요 시간을 로그로 남기고 trace에 노드 이름을 쌓는다(응답 시간 예산 점검용)."""

    def wrapper(state: FollowupState) -> dict:
        started = time.perf_counter()
        update = fn(state)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("followup_graph node=%s elapsed_ms=%.0f", name, elapsed_ms)
        return {**update, "trace": [*state.get("trace", []), name]}

    return wrapper


def build_followup_graph(
    *,
    retriever: QuestionBankRetriever,
    generate: Callable[[str, str], TurnLLMOutput],
    on_persona_leak: Callable[[str], None],
    turn_fallback_text: str,
):
    """그래프를 구성해 컴파일한다. 외부 의존(검색/LLM/감사로그)은 전부 주입받아 테스트 가능하다."""

    def retrieve(state: FollowupState) -> dict:
        retriever.invoke(state["query_text"])
        candidates = list(retriever.last_questions)
        system_prompt = interview_prompts.build_followup_system_prompt(candidates)
        return {"candidates": candidates, "system_prompt": system_prompt, "generations": 0}

    def generate_node(state: FollowupState) -> dict:
        try:
            output = generate(state["system_prompt"], state["user_message"])
        except LlmGenerationError:
            logger.warning("turn LLM 생성 실패 — 안전 기본값 폴백", exc_info=True)
            return {"llm_failed": True, "generations": state["generations"] + 1}
        return {"output": output, "llm_failed": False, "generations": state["generations"] + 1}

    def validate(state: FollowupState) -> dict:
        output = state["output"]
        if interview_prompts.validate_followup_speak_text(output.speak_text):
            return {"valid": True}
        if interview_prompts.contains_persona_leak_marker(output.speak_text):
            on_persona_leak(output.speak_text)
        logger.warning("후속 질문 출력 품질 가드 실패(%d회차)", state["generations"])
        return {"valid": False}

    def bank_fallback(state: FollowupState) -> dict:
        logger.warning("후속 질문 출력 품질 가드 실패(재시도 후) — 질문은행 폴백")
        candidates = state["candidates"]
        if candidates:
            output = TurnLLMOutput(speak_text=candidates[0].content, control="next_question")
        else:
            output = TurnLLMOutput(speak_text=turn_fallback_text, control="next_question")
        return {"output": output, "used_bank_fallback": True}

    def llm_failure_default(state: FollowupState) -> dict:
        return {
            "output": TurnLLMOutput(speak_text=turn_fallback_text, control="next_question"),
            "used_bank_fallback": False,
        }

    def after_generate(state: FollowupState) -> str:
        return "llm_failure_default" if state.get("llm_failed") else "validate"

    def after_validate(state: FollowupState) -> str:
        if state["valid"]:
            return END
        if state["generations"] < MAX_GENERATIONS:
            return "generate"
        return "bank_fallback"

    graph = StateGraph(FollowupState)
    graph.add_node("retrieve", _timed("retrieve", retrieve))
    graph.add_node("generate", _timed("generate", generate_node))
    graph.add_node("validate", _timed("validate", validate))
    graph.add_node("bank_fallback", _timed("bank_fallback", bank_fallback))
    graph.add_node("llm_failure_default", _timed("llm_failure_default", llm_failure_default))
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_conditional_edges("generate", after_generate, ["validate", "llm_failure_default"])
    graph.add_conditional_edges("validate", after_validate, ["generate", "bank_fallback", END])
    graph.add_edge("bank_fallback", END)
    graph.add_edge("llm_failure_default", END)
    return graph.compile()


def run_followup_graph(
    db: Session,
    *,
    query_text: str,
    user_message: str,
    min_similarity: float | None,
    on_persona_leak: Callable[[str], None],
    turn_fallback_text: str,
    generate: Callable[[str, str], TurnLLMOutput] | None = None,
) -> FollowupResult:
    """운영 진입점. `generate`를 생략하면 LangChain 경로(`generate_turn_via_langchain`)를 쓴다."""
    if generate is None:
        from app.services.langchain_orchestrator import generate_turn_via_langchain

        generate = generate_turn_via_langchain

    retriever = QuestionBankRetriever(
        db=db,
        exclude_categories={QuestionCategory.opening},
        top_k=3,
        min_similarity=min_similarity,
    )
    compiled = build_followup_graph(
        retriever=retriever,
        generate=generate,
        on_persona_leak=on_persona_leak,
        turn_fallback_text=turn_fallback_text,
    )
    final = compiled.invoke({"query_text": query_text, "user_message": user_message, "trace": []})
    return FollowupResult(
        output=final["output"],
        candidates=final["candidates"],
        generations=final["generations"],
        used_bank_fallback=bool(final.get("used_bank_fallback")),
        llm_failed=bool(final.get("llm_failed")),
        trace=final["trace"],
    )
