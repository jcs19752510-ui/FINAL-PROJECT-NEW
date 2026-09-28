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
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.evaluation_report import EvaluationReport, OverallRecommendation, PassFailRecommendation
from app.models.interview import Interview, InterviewStatus, ReportStatus
from app.models.question import Question, QuestionCategory
from app.models.rubric_template import RubricTemplate
from app.models.transcript import InputMode, Speaker, Transcript
from app.services import interview_prompts, rag_engine
from app.services.celery_app import celery_app
from app.services.llm_engine import (
    LlmGenerationError,
    ReportParsingFailed,
    TurnLLMOutput,
    available_input_tokens,
    count_tokens,
    generate_report_response,
    generate_turn_response,
    report_max_tokens,
)
from app.services.prompt_safety import log_persona_leak_detected
from app.services.rubric_defaults import SYSTEM_DEFAULT_RUBRIC_TEMPLATE_ID
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

# 리포트 생성(Feature E)은 턴 처리 이력 창(_HISTORY_WINDOW=8)과 달리 전체 대화를
# 입력으로 삼는다(03-design §4.4 "TRANSCRIPTS 전체"). 답변 5회 제한(2026-09-21
# 사용자 요청) 도입 이후 세션당 최대 약 11~12개 턴으로 자연히 짧아졌으나, 그래도
# 각 줄은 turn 처리와 동일한 컨텍스트 보호 원칙(DEF-005)을 적용해 잘라낸다.
_REPORT_MAX_LINE_CHARS = 500


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
    interview_id: uuid.UUID, system_prompt: str, user_message: str, rag_candidates: list[Question]
) -> TurnLLMOutput:
    """DEF-003/004/DEC-035 Q1: 검증(질문형·플레이스홀더 없음·한국어 비율·시스템
    프롬프트 문구 미포함) → 실패 시 1회 재시도 → 그래도 실패하면 질문은행 폴백.

    `generate_turn_response()` 자체의 스키마 파싱 재시도(최대 1회)와는 별개의
    상위 레이어 재시도다 — 스키마는 유효하지만 "품질"이 기준 미달인 경우를 잡는다.

    unit-27(REQ-039 감사 로그, 2026-09-22 사용자 승인): 품질 가드 실패 사유 중
    "시스템 프롬프트 유출 마커 포함"에 해당하는 경우만 골라 감사 로그를 남긴다
    (다른 사유— 질문형 아님/플레이스홀더/한국어비율 — 는 REQ-039 범위가 아님).
    """
    output = generate_turn_response(system_prompt, user_message)
    if interview_prompts.validate_followup_speak_text(output.speak_text):
        return output
    if interview_prompts.contains_persona_leak_marker(output.speak_text):
        log_persona_leak_detected(str(interview_id), output.speak_text)

    logger.warning("후속 질문 출력 품질 가드 실패(1차) — 재시도")
    output = generate_turn_response(system_prompt, user_message)
    if interview_prompts.validate_followup_speak_text(output.speak_text):
        return output
    if interview_prompts.contains_persona_leak_marker(output.speak_text):
        log_persona_leak_detected(str(interview_id), output.speak_text)

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
            output = _generate_validated_followup(interview_uuid, system_prompt, user_message, rag_candidates)
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


def _save_evaluation_report(
    db: Session,
    existing: EvaluationReport | None,
    interview_id: uuid.UUID,
    *,
    technical_score: int | None,
    communication_score: int | None,
    cultural_fit_score: int | None,
    overall_recommendation: OverallRecommendation | None,
    pass_fail_recommendation: PassFailRecommendation | None = None,
    star_json: dict | None,
    summary_text: str | None,
    details_json: dict | None,
    rubric_template_id: uuid.UUID | None = None,
    rubric_snapshot_json: dict | None = None,
    criteria_scores_json: list | None = None,
) -> None:
    """`interview_id` UK 제약(1면접=1리포트)이라 최초 생성/재시도(regenerate) 모두
    같은 행을 upsert한다 — `existing`이 있으면 갱신, 없으면 새로 만든다.
    """
    report = existing if existing is not None else EvaluationReport(interview_id=interview_id)
    report.technical_score = technical_score
    report.communication_score = communication_score
    report.cultural_fit_score = cultural_fit_score
    report.overall_recommendation = overall_recommendation
    report.pass_fail_recommendation = pass_fail_recommendation
    report.star_json = star_json
    report.summary_text = summary_text
    report.details_json = details_json
    # v15(03-system-design v4 §4.6 (4), unit-37): 재시도/파싱실패 경로에서도 템플릿
    # 스냅샷은 남긴다(그래야 "어떤 기준으로 채점을 시도했는지"가 기록에 남는다).
    report.rubric_template_id = rubric_template_id
    report.rubric_snapshot_json = rubric_snapshot_json
    report.criteria_scores_json = criteria_scores_json
    if existing is None:
        db.add(report)


def _resolve_rubric_template(interview: Interview, db: Session) -> RubricTemplate | None:
    """v15(03-system-design v4 §4.6 (3) "템플릿 결정 순서") — 면접에 지정된 템플릿 →
    (없거나 FK가 `ON DELETE SET NULL`로 비워졌으면) 시스템 기본 → (그것도 없으면,
    이론상 발생하지 않지만) None(레거시 3축만).
    """
    if interview.rubric_template_id is not None:
        template = db.get(RubricTemplate, interview.rubric_template_id)
        if template is not None:
            return template
    return db.get(RubricTemplate, SYSTEM_DEFAULT_RUBRIC_TEMPLATE_ID)


def _number_transcript(transcripts: list[Transcript]) -> tuple[list[str], dict[int, str]]:
    """§4.6 (3) "답변 번호" — 지원자 발화에만 [답변 N]을 매긴다(N=1부터, 시간순).
    `answer_map`은 번호→TRANSCRIPTS.id 대응표(§4.6 (4) `rubric_snapshot_json.answer_map`
    의 원본) — 이후 입력 예산으로 일부 발화를 줄여도 번호와 id는 바뀌지 않는다.
    """
    lines: list[str] = []
    answer_map: dict[int, str] = {}
    n = 0
    for t in transcripts:
        text = _truncate_for_llm(t.content_text, _REPORT_MAX_LINE_CHARS)
        if t.speaker == Speaker.ai:
            lines.append(f"면접관: {text}")
        else:
            n += 1
            answer_map[n] = str(t.id)
            lines.append(f"[답변 {n}] 지원자: {text}")
    return lines, answer_map


def _budget_transcript_lines(
    lines: list[str], system_prompt: str, criteria_block: str, output_tokens: int
) -> list[str]:
    """§4.6 (3) "입력 길이 예산" — 예산을 넘으면 첫 줄(오프닝 질문)과 최근 발화만
    남기고 가운데를 "(중간 발화 N개 생략)"으로 줄인다. 토큰 수는 llama-server
    `/tokenize`로 실측한다(글자 수 추정 금지, 03-system-design v4 §4.6 (3)).
    """
    if len(lines) <= 3:
        return lines
    budget = available_input_tokens(output_tokens)
    keep = len(lines) - 1  # 마지막 몇 줄을 유지할지(첫 줄 제외)
    while keep > 2:
        if keep >= len(lines) - 1:
            candidate = lines
        else:
            omitted = len(lines) - 1 - keep
            candidate = [lines[0], f"(중간 발화 {omitted}개 생략)"] + lines[-keep:]
        message = interview_prompts.format_transcript_for_report(candidate, criteria_block)
        total = count_tokens(system_prompt) + count_tokens(message)
        if total <= budget:
            return candidate
        keep -= 2  # 질문+답변 한 쌍 단위로 줄인다
    omitted = len(lines) - 1 - 2
    return [lines[0], f"(중간 발화 {omitted}개 생략)"] + lines[-2:]


def _validate_criteria_scores(
    raw_scores: list, criteria: list[dict], answer_map: dict[int, str]
) -> list[dict]:
    """§4.6 (3) "서버 검증" — LLM 출력을 그대로 믿지 않는다. 템플릿에 없는 이름은
    버리고, 템플릿에 있는데 모델이 빠뜨린 항목은 점수 없이 채워 넣는다(점수를
    지어내지 않는다).
    """
    by_name = {}
    for item in raw_scores:
        criterion = (item.criterion or "").strip()
        if not any(c["name"] == criterion for c in criteria):
            continue  # 템플릿에 없는 이름 — 채택하지 않음
        if item.score is None or not (1 <= item.score <= 5):
            continue  # 범위 밖 점수는 미채점과 동일하게 취급
        valid_refs = sorted({ref for ref in item.answer_refs if ref in answer_map})
        by_name[criterion] = {
            "criterion": criterion,
            "score": item.score,
            "evidence": (item.evidence or "")[:300] or "평가 근거 부족",
            "answer_refs": valid_refs,
        }
    result = []
    for c in criteria:
        result.append(by_name.get(c["name"], {
            "criterion": c["name"], "score": None, "evidence": "평가 근거 부족", "answer_refs": [],
        }))
    return result


def _weighted_overall_score(criteria_scores: list[dict], criteria: list[dict]) -> float | None:
    """§4.6 (3) "종합 점수" — 채점된 항목의 가중 평균(가중치 합이 0이면 단순 평균).
    채점된 항목이 하나도 없으면 None(호출부가 레거시 3축 평균으로 대체).
    """
    weight_by_name = {c["name"]: c.get("weight", 0) for c in criteria}
    scored = [(s["score"], weight_by_name.get(s["criterion"], 0)) for s in criteria_scores if s["score"] is not None]
    if not scored:
        return None
    weight_sum = sum(w for _, w in scored)
    if weight_sum <= 0:
        return round(sum(s for s, _ in scored) / len(scored), 1)
    return round(sum(s * w for s, w in scored) / weight_sum, 1)


@celery_app.task(name="app.worker.tasks.process_report_generation_job", bind=True)
def process_report_generation_job(self, interview_id: str) -> None:
    """`POST /interviews/{id}/end`(및 실패 후 `/report/regenerate`) 직후 enqueue되는
    job (Feature E, REQ-009/010/012, 03-design §4.2/§4.4).

    전체 `TRANSCRIPTS`를 입력으로 리포트 생성 LLM 호출 → `EVALUATION_REPORTS` upsert →
    `INTERVIEWS.report_status`를 `ready`/`failed`로 전이 → WS `report_ready`/`error`
    발행까지 수행한다. 파싱 실패(§4.4 "완전한 job 실패와는 구분")와 서버 호출 자체
    실패(완전한 job 실패)를 구분해 처리한다.
    """
    job_id = self.request.id
    interview_uuid = uuid.UUID(interview_id)
    db = SessionLocal()
    try:
        interview = db.get(Interview, interview_uuid)
        if interview is None or interview.status != InterviewStatus.completed:
            logger.warning("report_generation job 스킵 — 세션 상태 불일치: %s", interview_id)
            return

        transcripts = db.scalars(
            select(Transcript).where(Transcript.interview_id == interview_uuid).order_by(Transcript.turn_index)
        ).all()
        lines, answer_map = _number_transcript(transcripts)

        template = _resolve_rubric_template(interview, db)
        criteria: list[dict] = list(template.criteria_json) if template is not None else []
        criteria_block = interview_prompts.format_criteria_block(criteria)
        system_prompt = interview_prompts.build_report_system_prompt(has_criteria=bool(criteria))
        max_tokens = report_max_tokens(len(criteria))
        budgeted_lines = _budget_transcript_lines(lines, system_prompt, criteria_block, max_tokens)
        user_message = interview_prompts.format_transcript_for_report(budgeted_lines, criteria_block)

        rubric_snapshot = (
            {
                "template_id": str(template.id),
                "name": template.name,
                "criteria": criteria,
                "answer_map": {str(k): v for k, v in answer_map.items()},
            }
            if template is not None
            else None
        )

        existing = db.scalar(select(EvaluationReport).where(EvaluationReport.interview_id == interview_uuid))

        try:
            output = generate_report_response(system_prompt, user_message, max_tokens=max_tokens)
        except ReportParsingFailed as exc:
            # §4.4 파싱 실패 폴백: star_json/점수 없이 원문을 summary_text에 저장하되
            # report_status는 그대로 ready로 표시한다(리포트 자체는 존재). 템플릿
            # 스냅샷은 "어떤 기준으로 채점을 시도했는지" 기록으로 그대로 남긴다.
            _save_evaluation_report(
                db,
                existing,
                interview_uuid,
                technical_score=None,
                communication_score=None,
                cultural_fit_score=None,
                overall_recommendation=None,
                pass_fail_recommendation=None,
                star_json=None,
                summary_text=exc.raw_text,
                details_json=None,
                rubric_template_id=template.id if template is not None else None,
                rubric_snapshot_json=rubric_snapshot,
                criteria_scores_json=None,
            )
            interview.report_status = ReportStatus.ready
            interview.overall_score = None
            db.commit()
            publish_ws_event(
                interview_uuid, {"type": "report_ready", "job_id": job_id, "interview_id": interview_id}
            )
            return
        except LlmGenerationError:
            # 서버 호출 자체 실패(타임아웃 등) — §4.4 "완전한 job 실패"에 해당, failed로 표시.
            logger.warning("report_generation LLM 호출 실패 — report_status=failed", exc_info=True)
            interview.report_status = ReportStatus.failed
            db.commit()
            _publish_error(interview_uuid, job_id, "REPORT_GENERATION_FAILED", "리포트 생성에 실패했습니다.")
            return

        # §4.6 (3) "부분 실패 격리": criteria_scores 검증에서 문제가 생겨도 STAR/3축
        # 점수 등 나머지 리포트는 그대로 저장한다.
        criteria_scores_json: list[dict] | None = None
        weighted_score: float | None = None
        if criteria:
            try:
                criteria_scores_json = _validate_criteria_scores(output.criteria_scores, criteria, answer_map)
                # 실측 결함(2026-09-23, unit-37 기준선): 1.5B 모델이 JSON 자체는
                # 유효하게 만들면서도 `criteria_scores` 필드를 통째로 빠뜨리는 경우가
                # 3회 중 1회 관측됐다(이름 표기가 아니라 필드 누락 — 파싱은 성공하므로
                # generate_report_response의 파싱 재시도로는 걸러지지 않는다). 이
                # 경로에서만 한 번 더 생성을 시도하고, 그래도 비어 있으면 기존 원칙대로
                # "점수 없음"으로 저장한다(점수를 지어내지 않음).
                if not any(s["score"] is not None for s in criteria_scores_json):
                    logger.warning("criteria_scores 전부 미채점 — 1회 재생성 시도")
                    try:
                        retry_output = generate_report_response(system_prompt, user_message, max_tokens=max_tokens)
                        retry_scores = _validate_criteria_scores(retry_output.criteria_scores, criteria, answer_map)
                        if any(s["score"] is not None for s in retry_scores):
                            output = retry_output
                            criteria_scores_json = retry_scores
                    except (ReportParsingFailed, LlmGenerationError):
                        logger.warning("criteria_scores 재생성 실패 — 미채점 상태로 계속 진행", exc_info=True)
                weighted_score = _weighted_overall_score(criteria_scores_json, criteria)
            except Exception:  # noqa: BLE001 — 항목별 채점만 실패로 격리, 리포트 전체는 계속 저장
                logger.warning("criteria_scores 검증 중 예외 — 항목별 채점 없이 계속 진행", exc_info=True)
                criteria_scores_json = None

        legacy_score = round(
            (output.technical_accuracy + output.communication_clarity + output.cultural_fit) / 3, 1
        )
        overall_score = weighted_score if weighted_score is not None else legacy_score
        _save_evaluation_report(
            db,
            existing,
            interview_uuid,
            rubric_template_id=template.id if template is not None else None,
            rubric_snapshot_json=rubric_snapshot,
            criteria_scores_json=criteria_scores_json,
            technical_score=output.technical_accuracy,
            communication_score=output.communication_clarity,
            cultural_fit_score=output.cultural_fit,
            overall_recommendation=OverallRecommendation(output.overall_recommendation),
            pass_fail_recommendation=PassFailRecommendation(output.pass_fail_recommendation)
            if output.pass_fail_recommendation
            else None,
            star_json=output.star.model_dump(),
            summary_text=None,
            details_json=output.details,
        )
        interview.report_status = ReportStatus.ready
        interview.overall_score = overall_score
        db.commit()
        publish_ws_event(interview_uuid, {"type": "report_ready", "job_id": job_id, "interview_id": interview_id})
    except Exception:  # noqa: BLE001 — 워커 태스크 최상위 경계, 예외를 삼키지 않고 에러 이벤트로 알림
        logger.exception("report_generation job 처리 중 예외 발생: %s", interview_id)
        try:
            interview = db.get(Interview, interview_uuid)
            if interview is not None:
                interview.report_status = ReportStatus.failed
                db.commit()
        except Exception:  # noqa: BLE001 — 상태 갱신 자체가 실패해도 워커를 죽이지 않음
            logger.exception("report_status=failed 갱신 중 추가 예외 발생: %s", interview_id)
        _publish_error(interview_uuid, job_id, "REPORT_GENERATION_FAILED", "리포트 생성 중 오류가 발생했습니다.")
    finally:
        db.close()
