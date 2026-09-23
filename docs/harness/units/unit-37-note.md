# unit-37 구현 노트 — 루브릭 템플릿 기반 항목별 채점 (REQ-010/012 원안 일치, 규칙 F 재작업)

- 작성: 2026-09-23, 본 세션(05 역할)
- 배경: unit-10/11(정적 검토판, DEC-053)이 REQ-010(사전 정의 루브릭 템플릿 기반 채점)·REQ-012(평가 근거 노출)에서 FAIL을 냈다(DEF-001~003). 근본 원인은 3단계 설계 공백(누가 템플릿을 지정하는지, 채점에 어떻게 반영하는지 미정의)으로 판단해 규칙 F에 따라 03/04 설계서를 먼저 재작업(v4/v3, 검증 완료)한 뒤 이 유닛에서 구현했다(DEC-054/055).
- 속도 트랙: L3(DEC-031, unit-8/10/11 계열과 동일 원칙 적용)
- 입력: 03-system-design.md v4 §4.6, 04-ux-design.md v3 [C-11]/[R-02] 공통 추가 섹션

## 1. 구현 범위

| 계층 | 파일 | 내용 |
|---|---|---|
| DB | `alembic/versions/e6a1b8f4d2c7_v15_rubric_scoring.py` | `evaluation_reports`에 `rubric_template_id`(FK, ON DELETE SET NULL)·`rubric_snapshot_json`·`criteria_scores_json` 추가. 시스템 기본 템플릿 1행 시드(고정 UUID). 기존 면접 중 템플릿 없는 것도 기본값으로 채움 |
| 상수 | `app/services/rubric_defaults.py` | 시스템 기본 템플릿 UUID(마이그레이션과 애플리케이션 코드가 공유) |
| 모델 | `app/models/evaluation_report.py` | 컬럼 3개 추가 |
| LLM | `app/services/llm_engine.py` | `CriterionScoreLLM`, `ReportLLMOutput.criteria_scores`(선택 필드), `count_tokens()`(`/tokenize` 실측), `available_input_tokens()`, `report_max_tokens(n)`(항목 수 비례), `generate_report_response(max_tokens=...)`, 리포트 전용 제한시간(`settings.llm_report_timeout_seconds`) |
| 프롬프트 | `app/services/interview_prompts.py` | `build_report_system_prompt(has_criteria=)`, `format_criteria_block()`(평가 기준을 user 메시지에 데이터로 전달, 인젝션 경계 문구 포함), `format_transcript_for_report()`가 criteria_block 인자 추가 |
| 워커 | `app/worker/tasks.py` | `_resolve_rubric_template`(지정→기본→레거시), `_number_transcript`(`[답변 N]` 번호 매기기 + answer_map), `_budget_transcript_lines`(토큰 예산 초과 시 중간 발화 생략), `_validate_criteria_scores`(서버 검증), `_weighted_overall_score`(가중 평균) |
| API | `app/api/v1/interviews.py::_build_rubric_out` | 응답용 `rubric` 필드 조립(스냅샷+DB 재조회로 발췌 생성) |
| API | `app/api/v1/recruiter.py::assign_rubric_template` | `PUT /recruiter/interviews/{id}/rubric-template` — 큐 상한 확인(503) 포함 |
| 큐 | `app/services/job_queue.py::queue_length()` | Redis `LLEN`으로 `ai_pipeline` 큐 길이 확인(§4.6 (2) 남용 제한 전용) |
| 스키마 | `app/schemas/interview.py`, `app/schemas/rubric_template.py`, `app/schemas/recruiter.py` | `RubricOut`/`CriterionScoreOut`/`RubricAnswerOut`, `RubricTemplateAssignIn/Out` |
| 프런트 | `components/RubricEvidenceSection.tsx`(신규), `app/interviews/[id]/report/page.tsx`, `app/recruiter/[id]/page.tsx` | 04 [C-11]/[R-02] 공통 섹션 + [R-02] 템플릿 변경 컨트롤(화면 내 확인 문구, 브라우저 `confirm()` 미사용) |

## 2. 구현 중 발견·수정한 실측 결함 (05 단계, 즉시 조치)

1. **리포트가 이 PC에서 항상 실패했다.** 기준선 E2E 실측 결과, 턴 처리와 리포트가 LLM 제한시간(25초)을 공유해 리포트(수백 토큰)가 항상 타임아웃됐다. 리포트 전용 제한시간(`LLM_REPORT_TIMEOUT_SECONDS`, 기본 300초)으로 분리해 해결(03 §4.6 (3)에 이미 반영됨, 설계 검증 통과 후 구현).
2. **`criteria_scores` 필드 완전 누락(신규 발견, 05단계).** 1.5B 모델이 JSON 자체는 유효하게 만들면서 `criteria_scores` 필드를 통째로 빠뜨리는 경우가 실측 3회 중 1회 발생했다(이름 표기 문제가 아니라 필드 누락 — 기존 파싱 재시도로는 안 걸러짐). 해결: 검증 후 전 항목이 미채점이면 1회 재생성을 시도하고, 그래도 비면 "점수 없음"으로 정직하게 저장(점수를 지어내지 않음, §4.6 (3) 원칙 그대로). `tasks.py::process_report_generation_job` 참고.
3. **항목 이름 앞뒤 공백.** 모델이 두 번째 항목부터 `" 의사소통"`처럼 공백을 붙이는 경우가 있어, `_validate_criteria_scores`에서 `.strip()`으로 비교(이미 반영, 결함이라기보다 정상적인 방어 코드).
4. **작업 감시(job_watchdog) 오탐(신규 발견, 코드 리뷰).** 리포트 전용 제한시간을 300초로 늘렸는데 `job_watchdog.py`의 감시 타임아웃은 턴 기준 150초로 고정돼 있었다 — 정상 진행 중인 리포트가 150초를 넘기면 "유실"로 오판돼 사용자에게 잘못된 실패 알림(WS `error`)이 갈 뻔했다(`report_status`는 여전히 `queued`인데 화면은 실패로 보임). `register_job()`에 `timeout_seconds` 파라미터를 추가하고 `enqueue_report_generation_job`이 `llm_report_timeout_seconds + 60초` 여유를 넘기도록 고쳤다. 실제 워커 중단으로 재현하지는 않았고 코드 리뷰로 발견·수정했다(unit-37-test.md TC-016 참고).

## 3. 설계 대비 확인

- `answer_map`을 `rubric_snapshot_json`에 저장해 이후 삭제 요청(REQ-030)으로 대화가 지워져도 번호-원문 대응이 깨지지 않게 했다(설계 §4.6 (4) 그대로).
- 기존 3축 점수(`technical_score` 등)는 계속 채워진다(레거시 호환, 파싱 실패 폴백 시 대체 지표로도 쓰임).
- 종합 점수는 항목 채점이 1개 이상이면 가중 평균, 없으면 3축 평균(레거시)로 자동 전환된다.

## 4. 06 단위테스트 인계

- 결과서: `unit-37-test.md`. 이 PC에서 **실제로 백엔드/DB/Redis/LLM/워커/프런트를 기동해 실측**했다(개발 서버가 아니라 이 세션이 직접 구축한 환경, DEC-055).
- 브라우저(Playwright)로 화면까지는 이번 유닛에서 확인하지 못했다 — API/데이터 계층은 완전 실측, 화면은 타입체크·린트·코드 대조까지만(§8 후속 항목 참고).
