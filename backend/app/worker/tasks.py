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

**unit-7 재작업(DEC-035 응답, "## 재작업(Rework) v2" 섹션 참고)**:
- DEF-001(오프닝 품질): 오프닝은 더 이상 LLM을 거치지 않고 질문은행 원문을
  `speak_text`로 그대로 사용한다(DEC-035 Q1 (a)).
- DEF-002(turn_index 중복): 채번을 `app/services/turn_numbering.py`로 통일했다.
- DEF-003/004(후속 질문 품질/페르소나 낭독): `interview_prompts.validate_followup_speak_text()`로
  검증 → 실패 시 1회 재시도 → 그래도 실패하면 질문은행 폴백.
- DEF-005(긴 답변 컨텍스트 초과): 이력/최신 답변을 LLM에 보내기 전 문자 수 기준으로
  잘라낸다(서버측 잘라내기, DEC-035 Q4).
- DEF-007(RAG 무관 후보): 후속 검색은 opening 카테고리를 제외하고 유사도 임계치
  미달 후보는 버린다.
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
from app.services.turn_numbering import insert_transcript_with_retry
from app.services.ws_publisher import publish_ws_event

logger = logging.getLogger(__name__)

# 03-design §4.4/§5.4 "안전 기본값 폴백" 그대로.
_OPENING_FALLBACK_TEXT = "간단히 자기소개 부탁드립니다."
_TURN_FALLBACK_TEXT = "답변 감사합니다. 다음 질문으로 넘어가겠습니다."

_HISTORY_WINDOW = 8

# DEF-005(unit-7-test.md TC-028): llama-server 컨텍스트(4096 토큰) 초과로 2,500자
# 이상의 답변에서 HTTP 400 → LlmGenerationError → 고정 폴백이 발생했고(1,500자는
# 정상), 그 긴 답변이 이력 창에 남아 이후 턴까지 연쇄 폴백됐다. 실측 경계(1,500자
# 성공/2,500자 실패)에서 여유를 둔 값으로 최신 답변과 이력 각 줄을 잘라낸다 —
# 원본 답변은 이 잘라내기 이전에 이미 TRANSCRIPTS에 전문이 저장되어 있으므로
# (app/api/v1/interviews.py) 데이터 손실은 없다(LLM에 보내는 프롬프트만 축약).
_MAX_ANSWER_CHARS_FOR_LLM = 1500
_MAX_HISTORY_LINE_CHARS = 300
_TRUNCATION_SUFFIX = " …(이하 생략)"

# DEF-007(unit-7-test.md TC-035): 후속 검색이 opening 카테고리를 제외하지 않고
# 유사도 임계치도 없어, 무관한 질문(예: 자기소개 오프닝 문항)이 후속 답변의 top3에
# 섞여 question_id로 기록됐다. 관측값(무관 질의 최고 0.18, 관련 질의 약 0.53) 사이의
# 보수적인 중간값을 컷오프로 택했다 — 상세 근거는 unit-7-note.md 재작업 섹션 참고.
_FOLLOWUP_RAG_MIN_SIMILARITY = 0.30


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


def _truncate_for_llm(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + _TRUNCATION_SUFFIX


def _bank_fallback_output(rag_candidates: list[Question]) -> TurnLLMOutput:
    """DEF-003/004 가드가 재시도 후에도 실패하면 질문은행 원문으로 폴백한다
    (질문은행 문항은 전부 질문형이라 가드를 거치지 않고도 안전하다).
    """
    if rag_candidates:
        return TurnLLMOutput(speak_text=rag_candidates[0].content, control="next_question")
    return TurnLLMOutput(speak_text=_TURN_FALLBACK_TEXT, control="next_question")


def _generate_validated_followup(
    system_prompt: str, user_message: str, rag_candidates: list[Question]
) -> TurnLLMOutput:
    """DEF-003/004/DEC-035 Q1: 검증(질문형·플레이스홀더 없음·한국어 비율·시스템
    프롬프트 문구 미포함) → 실패 시 1회 재시도 → 그래도 실패하면 질문은행 폴백.

    `generate_turn_response()` 자체의 스키마 파싱 재시도(최대 1회)와는 별개의
    상위 레이어 재시도다 — 스키마는 유효하지만 "품질"이 기준 미달인 경우를 잡는다.
    """
    output = generate_turn_response(system_prompt, user_message)
    if interview_prompts.validate_followup_speak_text(output.speak_text):
        return output

    logger.warning("후속 질문 출력 품질 가드 실패(1차) — 재시도")
    output = generate_turn_response(system_prompt, user_message)
    if interview_prompts.validate_followup_speak_text(output.speak_text):
        return output

    logger.warning("후속 질문 출력 품질 가드 실패(재시도 후) — 질문은행 폴백")
    return _bank_fallback_output(rag_candidates)


@celery_app.task(name="app.worker.tasks.process_opening_question_job", bind=True)
def process_opening_question_job(self, interview_id: str) -> None:
    """`POST /interviews/{id}/start` 성공 직후 enqueue되는 job (§4.3 DEC-024 갭8).

    **DEF-001/DEC-035 Q1 (a) 재작업**: 오프닝은 더 이상 LLM을 거치지 않는다. 1.5B
    모델이 오프닝 질문을 무시하고 지원자를 사칭한 자기소개를 지어내거나 미치환
    플레이스홀더를 낭독하는 결함이 9/9 표본에서 실측됐다(unit-7-test.md TC-003).
    질문은행(`category=opening`)에서 선정한 문항 원문을 그대로 `speak_text`로
    사용하고, TTS만 거친다. `question_id`는 그 선정된 질문은행 항목을 가리킨다.
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

        if opening_question is not None:
            output = TurnLLMOutput(speak_text=opening_question.content, control="none")
        else:
            logger.warning("질문은행에 opening 카테고리 항목이 없어 고정 폴백 사용: %s", interview_id)
            output = TurnLLMOutput(speak_text=_OPENING_FALLBACK_TEXT, control="none")

        _publish_stage(interview_uuid, job_id, "tts")
        audio_url = _synthesize_or_none(output.speak_text)

        ai_transcript = insert_transcript_with_retry(
            db,
            interview_uuid,
            lambda turn_index: Transcript(
                interview_id=interview_uuid,
                question_id=opening_question.id if opening_question else None,
                turn_index=turn_index,
                speaker=Speaker.ai,
                input_mode=InputMode.text,
                content_text=output.speak_text,
                audio_ref=audio_url,
            ),
        )

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
    (1) 최근 대화 맥락 + RAG 검색 → (2) LLM 꼬리질문 생성(품질 가드 포함, DEF-003/004) →
    (3) TTS 합성 → (4) `TRANSCRIPTS(speaker=ai)` 저장 → (5) WS `turn_result` push
    순으로 처리한다.
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
            f"{'면접관' if t.speaker == Speaker.ai else '지원자'}: "
            f"{_truncate_for_llm(t.content_text, _MAX_HISTORY_LINE_CHARS)}"
            for t in history
        ]
        latest_answer = _truncate_for_llm(user_transcript.content_text, _MAX_ANSWER_CHARS_FOR_LLM)
        user_message = (
            "[대화 이력]\n" + "\n".join(history_lines) +
            f"\n\n[지원자의 최신 답변]\n{latest_answer}"
        )

        rag_candidates = rag_engine.search_similar_questions(
            db,
            query_text=user_transcript.content_text,
            exclude_categories={QuestionCategory.opening},
            top_k=3,
            min_similarity=_FOLLOWUP_RAG_MIN_SIMILARITY,
        )

        try:
            system_prompt = interview_prompts.build_followup_system_prompt(rag_candidates)
            output = _generate_validated_followup(system_prompt, user_message, rag_candidates)
        except LlmGenerationError:
            logger.warning("turn LLM 생성 실패 — 안전 기본값 폴백", exc_info=True)
            output = TurnLLMOutput(speak_text=_TURN_FALLBACK_TEXT, control="next_question")

        _publish_stage(interview_uuid, job_id, "tts")
        audio_url = _synthesize_or_none(output.speak_text)

        matched_question: Question | None = rag_candidates[0] if rag_candidates else None
        ai_transcript = insert_transcript_with_retry(
            db,
            interview_uuid,
            lambda turn_index: Transcript(
                interview_id=interview_uuid,
                question_id=matched_question.id if matched_question else None,
                turn_index=turn_index,
                speaker=Speaker.ai,
                input_mode=InputMode.text,
                content_text=output.speak_text,
                audio_ref=audio_url,
            ),
        )

        _publish_turn_result(interview_uuid, job_id, user_transcript, ai_transcript, audio_url, output.control)
    except Exception:  # noqa: BLE001 — 워커 태스크 최상위 경계, 예외를 삼키지 않고 에러 이벤트로 알림
        logger.exception("turn job 처리 중 예외 발생: interview=%s transcript=%s", interview_id, transcript_id)
        _publish_error(interview_uuid, job_id, "AI_SERVICE_TIMEOUT", "AI 응답 생성 중 오류가 발생했습니다.")
    finally:
        db.close()
