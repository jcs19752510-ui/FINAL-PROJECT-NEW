"""AI Worker(Celery) 태스크 — LLM 응답 생성 → TTS 합성 파이프라인 (REQ-007,
03-system-design.md §1.3/§4.3/§4.4/§5.4, DEC-019).

`celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline`
로 기동되는 단일 워커 프로세스에서 실행된다.

**범위 경계(오케스트레이터 지시 그대로)**: STT(unit-5)/TTS(unit-6)는 이미 각자
유닛에서 실제로 동작하도록 구현되어 있다. unit-5는 "AI Worker가 실제로 생기면
그때 STT 호출부를 워커 태스크로 옮기면 된다"는 전제로 API 요청 핸들러 내 동기
실행을 선택했지만(unit-5-note.md §2-1), 이번 유닛의 오케스트레이터 지시는
명시적으로 "job_queue.enqueue_turn_job()이 실제로 워커에서 처리되어 LLM 응답
생성 → TTS 합성까지 이어지는 파이프라인을 연결하라"이며 STT 이관은 언급하지
않았다 — 사용자 턴은 API가 이미 TRANSCRIPTS에 커밋한 뒤 이 태스크를 큐에 넣으므로
(§4.2 `/turns` 핸들러), 이 태스크는 "사용자 턴이 이미 저장된 시점부터" 시작한다.
STT 호출부를 이 태스크로 옮기는 리팩터링은 범위 외 변경으로 보고 하지 않았다
(unit-7-note.md §2 참고).
"""
import logging
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.interview import Interview, InterviewStatus
from app.models.question import Question, QuestionCategory
from app.models.transcript import InputMode, Speaker, Transcript
from app.services import interview_prompts, rag_engine
from app.services.celery_app import celery_app
from app.services.llm_engine import LlmGenerationError, TurnLLMOutput, generate_turn_response
from app.services.tts_engine import TtsSynthesisError, synthesize_speech_file
from app.services.ws_publisher import publish_ws_event

logger = logging.getLogger(__name__)

# 03-design §4.4/§5.4 "안전 기본값 폴백" 그대로.
_TURN_FALLBACK_TEXT = "답변 감사합니다. 다음 질문으로 넘어가겠습니다."
_OPENING_FALLBACK_TEXT = "간단히 자기소개 부탁드립니다."

_HISTORY_WINDOW = 8


def _publish_stage(interview_id: uuid.UUID, job_id: str, stage: str) -> None:
    publish_ws_event(interview_id, {"type": "stage_update", "job_id": job_id, "stage": stage})


def _publish_error(interview_id: uuid.UUID, job_id: str, code: str, message: str) -> None:
    publish_ws_event(interview_id, {"type": "error", "job_id": job_id, "code": code, "message": message})


def _publish_turn_result(
    interview_id: uuid.UUID,
    job_id: str,
    user_transcript: Transcript | None,
    ai_transcript: Transcript,
    audio_url: str | None,
    control: str,
) -> None:
    # 03-design §4.3 "job_id와 DB 레코드의 관계": turn_result 이벤트에 새로 생성된
    # TRANSCRIPTS.id를 함께 반환해, 클라이언트가 이후 job_id가 아닌 transcript.id
    # 기준으로 참조하게 한다. opening_question job은 대응하는 user 턴이 없으므로
    # user_transcript_id가 null이다(§4.3 명시된 유일한 예외 케이스).
    publish_ws_event(
        interview_id,
        {
            "type": "turn_result",
            "job_id": job_id,
            "transcript": user_transcript.content_text if user_transcript else None,
            "ai_text": ai_transcript.content_text,
            "audio_url": audio_url,
            "control": {"action": control},
            "user_transcript_id": str(user_transcript.id) if user_transcript else None,
            "ai_transcript_id": str(ai_transcript.id),
        },
    )


def _synthesize_or_none(text: str) -> str | None:
    """TTS 실패를 전체 job 실패로 만들지 않는 그레이스풀 디그레이드(unit-7 편차,
    unit-7-note.md §2 참고) — 텍스트 응답은 이미 확보되어 있으므로, 음성 합성만
    실패했다고 사용자가 AI 응답 자체를 못 받게 하지 않는다.
    """
    try:
        return synthesize_speech_file(text)
    except TtsSynthesisError:
        logger.warning("TTS 합성 실패 — 텍스트만 전달(audio_url=None)", exc_info=True)
        return None


def _next_turn_index(interview_id: uuid.UUID, db) -> int:
    from sqlalchemy import func

    return db.scalar(select(func.count()).select_from(Transcript).where(Transcript.interview_id == interview_id))


@celery_app.task(name="app.worker.tasks.process_opening_question_job", bind=True)
def process_opening_question_job(self, interview_id: str) -> None:
    """`POST /interviews/{id}/start` 성공 직후 enqueue되는 job (§4.3 DEC-024 갭8).

    STT 단계 없이 LLM→TTS만 수행하고, `TRANSCRIPTS(speaker=ai, turn_index=0)`로
    저장한다. `question_id`는 RAG(질문은행 `category=opening`)로 선정된 항목.
    """
    job_id = self.request.id
    interview_uuid = uuid.UUID(interview_id)
    db = SessionLocal()
    try:
        interview = db.get(Interview, interview_uuid)
        if interview is None or interview.status != InterviewStatus.live:
            logger.warning("opening_question job 스킵 — 세션 상태 불일치: %s", interview_id)
            return

        _publish_stage(interview_uuid, job_id, "llm")

        opening_candidates = rag_engine.search_similar_questions(
            db, query_text="면접 시작 오프닝 자기소개", category=QuestionCategory.opening, top_k=1
        )
        opening_question = opening_candidates[0] if opening_candidates else None

        try:
            if opening_question is None:
                raise LlmGenerationError("질문은행에 opening 카테고리 항목이 없습니다.")
            system_prompt = interview_prompts.build_opening_system_prompt(opening_question)
            output = generate_turn_response(
                system_prompt, "(면접을 시작합니다. 지원자에게 인사와 함께 오프닝 질문을 자연스럽게 전달하세요.)"
            )
        except LlmGenerationError:
            logger.warning("opening_question LLM 생성 실패 — 안전 기본값 폴백", exc_info=True)
            output = TurnLLMOutput(speak_text=_OPENING_FALLBACK_TEXT, control="none")

        _publish_stage(interview_uuid, job_id, "tts")
        audio_url = _synthesize_or_none(output.speak_text)

        ai_transcript = Transcript(
            interview_id=interview_uuid,
            question_id=opening_question.id if opening_question else None,
            turn_index=0,
            speaker=Speaker.ai,
            input_mode=InputMode.text,
            content_text=output.speak_text,
            audio_ref=audio_url,
        )
        db.add(ai_transcript)
        db.commit()
        db.refresh(ai_transcript)

        _publish_turn_result(interview_uuid, job_id, None, ai_transcript, audio_url, output.control)
    except Exception:  # noqa: BLE001 — 워커 태스크 최상위 경계, 예외를 삼키지 않고 에러 이벤트로 알림
        logger.exception("opening_question job 처리 중 예외 발생: %s", interview_id)
        _publish_error(interview_uuid, job_id, "AI_SERVICE_TIMEOUT", "첫 질문 준비 중 오류가 발생했습니다.")
    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.process_turn_job", bind=True)
def process_turn_job(self, interview_id: str, transcript_id: str) -> None:
    """`POST /interviews/{id}/turns` 성공(사용자 턴 커밋 완료) 직후 enqueue되는 job.

    사용자 턴은 이미 `TRANSCRIPTS`에 저장되어 있다(§4.2, unit-4/5). 이 태스크는
    (1) 최근 대화 맥락 + RAG 검색 → (2) LLM 꼬리질문 생성 → (3) TTS 합성 →
    (4) `TRANSCRIPTS(speaker=ai)` 저장 → (5) WS `turn_result` push 순으로 처리한다.
    """
    job_id = self.request.id
    interview_uuid = uuid.UUID(interview_id)
    transcript_uuid = uuid.UUID(transcript_id)
    db = SessionLocal()
    try:
        interview = db.get(Interview, interview_uuid)
        user_transcript = db.get(Transcript, transcript_uuid)
        if interview is None or user_transcript is None or interview.status != InterviewStatus.live:
            logger.warning(
                "turn job 스킵 — 세션/턴 상태 불일치: interview=%s transcript=%s", interview_id, transcript_id
            )
            return

        _publish_stage(interview_uuid, job_id, "llm")

        history_stmt = (
            select(Transcript)
            .where(Transcript.interview_id == interview_uuid)
            .order_by(Transcript.turn_index.desc())
            .limit(_HISTORY_WINDOW)
        )
        history = list(reversed(db.scalars(history_stmt).all()))
        history_lines = [
            f"{'면접관' if t.speaker == Speaker.ai else '지원자'}: {t.content_text}" for t in history
        ]
        user_message = (
            "[대화 이력]\n" + "\n".join(history_lines) +
            f"\n\n[지원자의 최신 답변]\n{user_transcript.content_text}"
        )

        rag_candidates = rag_engine.search_similar_questions(
            db, query_text=user_transcript.content_text, top_k=3
        )

        try:
            system_prompt = interview_prompts.build_followup_system_prompt(rag_candidates)
            output = generate_turn_response(system_prompt, user_message)
        except LlmGenerationError:
            logger.warning("turn LLM 생성 실패 — 안전 기본값 폴백", exc_info=True)
            output = TurnLLMOutput(speak_text=_TURN_FALLBACK_TEXT, control="next_question")

        _publish_stage(interview_uuid, job_id, "tts")
        audio_url = _synthesize_or_none(output.speak_text)

        matched_question: Question | None = rag_candidates[0] if rag_candidates else None
        ai_transcript = Transcript(
            interview_id=interview_uuid,
            question_id=matched_question.id if matched_question else None,
            turn_index=_next_turn_index(interview_uuid, db),
            speaker=Speaker.ai,
            input_mode=InputMode.text,
            content_text=output.speak_text,
            audio_ref=audio_url,
        )
        db.add(ai_transcript)
        db.commit()
        db.refresh(ai_transcript)

        _publish_turn_result(interview_uuid, job_id, user_transcript, ai_transcript, audio_url, output.control)
    except Exception:  # noqa: BLE001 — 워커 태스크 최상위 경계, 예외를 삼키지 않고 에러 이벤트로 알림
        logger.exception("turn job 처리 중 예외 발생: interview=%s transcript=%s", interview_id, transcript_id)
        _publish_error(interview_uuid, job_id, "AI_SERVICE_TIMEOUT", "AI 응답 생성 중 오류가 발생했습니다.")
    finally:
        db.close()
