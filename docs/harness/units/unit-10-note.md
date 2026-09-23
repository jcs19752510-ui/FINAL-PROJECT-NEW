# unit-10 구현 노트 — STAR 기반 리포트 생성 로직 (REQ-009) · 소급 작성

- 작성: 2026-09-23, 본 세션(오케스트레이터가 05 역할로 **소급 문서화**, DEC-053)
- 대상 REQ: REQ-009([Must] STAR 구조 기반 상세 피드백 리포트 자동 생성, 02-planning §4.2)
- 속도 트랙: **L3**(DEC-031 — unit-8/10/11은 L3 예외. 06·07 정식, 규칙 B 원문, Tier=High)
- 입력: 03-system-design.md §3(EVALUATION_REPORTS)·§4.2(`/end`, `/report`, `/report/regenerate`)·§4.4(리포트 생성 구조화 출력 계약)·§5.4, 04-ux-design.md [C-10]/[C-11]

## 0. 이 노트가 "소급"인 이유 (중요)

이 유닛의 코드는 **이미 2026-09-21~22에 구현·커밋되어 있었다.** 하지만 하네스 절차(05 노트 → 06 결과서 → traceability 갱신)를 거치지 않아서, `traceability.md`에는 REQ-009가 계속 "Not Started"로 남아 있었다(규칙 H·D 공백. DEC-037/050과 같은 유형).

- 구현 커밋: `18d5ceb`(2026-09-22 12:08, 리포트 생성 전 계층 — 마이그레이션 v10, 모델, 워커 태스크, API, 지원자 리포트 화면 신설). 프런트 화면 docstring에는 "사용자 요청(2026-09-21)으로 신설"이라고 적혀 있다.
- 후속 변경: `a182388`(2026-09-22 21:24, unit-23 합격/불합격 참고의견 필드 추가), `2def886`(2026-09-23, unit-23~36 묶음).
- 당시 실측 근거: `bugfix-20260922-event-loop-hang-test.md` TC-H04/H05. **기존 개발 서버에서** 실계정으로 면접 5턴 → 종료 → 리포트 생성(점수·STAR·추천의견) → 지원자/채용담당자 조회까지 실제로 성공했다.

이 노트는 **코드를 새로 작성하지 않았다.** 현재 저장소 코드를 읽고 설계서와 대조해 "무엇이 어떻게 구현되어 있는지"를 기록한 것이다.

## 1. 구현 범위 (현재 코드 기준)

| 계층 | 파일 | 내용 |
|---|---|---|
| DB | `backend/alembic/versions/9c91a685f9df_v10_evaluation_reports.py` | `evaluation_reports` 테이블 신설(`interview_id` UK = 면접 1건당 리포트 1건) |
| 모델 | `backend/app/models/evaluation_report.py` | 3축 점수(int, nullable), `overall_recommendation` 3등급 enum(REQ-031), `pass_fail_recommendation`(unit-23), `star_json`(JSONB), `summary_text`(폴백), `details_json`(JSONB) |
| API | `backend/app/api/v1/interviews.py` | `POST /{id}/end` → `report_status=queued` + `report_generation` job enqueue. `GET /{id}/report`: none→409 / queued→202 `{status:"processing"}` / failed→409 `REPORT_GENERATION_FAILED` / ready→200. `POST /{id}/report/regenerate`: `failed`일 때만 허용, 세션 소유자만 |
| 권한 | `interviews.py::_get_report_viewable_interview` | 지원자 본인 + recruiter 전원(03 §6.1 단일조직 MVP 정책). 재시도는 본인만 |
| 워커 | `backend/app/worker/tasks.py::process_report_generation_job` | 전체 TRANSCRIPTS를 시간순으로 정렬하고 줄마다 500자로 자른 뒤 LLM 호출 → 성공 시 upsert + `overall_score`=3축 평균(소수 1자리) → `ready` + WS `report_ready` |
| LLM | `backend/app/services/llm_engine.py::generate_report_response` | `max_tokens=700`, 파싱 실패 시 1회 재시도. 그래도 실패하면 `ReportParsingFailed(raw_text)`를 던지고, 서버 호출 실패는 `LlmGenerationError`로 구분 |
| 스키마 | `llm_engine.py::ReportLLMOutput`, `StarOutput` | 점수 `Field(ge=1, le=5)`, 추천 등급 `Literal` 화이트리스트. `StarOutput`은 모델이 STAR를 문자열 하나로 뭉쳐 보내면 `situation`에 담아 준다(2026-09-21 실측 결함 대응) |
| 프롬프트 | `backend/app/services/interview_prompts.py::_REPORT_PERSONA` | 한국어 전용, "최종 판정자 아님", 대화 속 조작 요청 무시(REQ-035 방향), 순수 JSON 강제 |
| 화면 | `frontend/app/interviews/[id]/report/page.tsx` | [C-11]. 3초 간격 폴링(WS 대신 — 03 §4.3이 허용한 폴백), STAR 4개 구간 표시, `star` 없으면 `summary_text`를 문단으로 표시, 실패 시 재시도 버튼, 면책 문구 고정. `dangerouslySetInnerHTML` 미사용(REQ-036) |
| 채용담당자 | `backend/app/api/v1/recruiter.py`, `frontend/app/recruiter/[id]/page.tsx` | `_report_to_out`을 재사용하는 얇은 래퍼(REQ-011, unit-12 규칙 F 후속) |

## 2. 설계 대비 판단

- §4.4의 세 가지 경로가 모두 코드에 있다. 확인 방법은 코드 읽기다.
  - **파싱 실패** → `summary_text` 폴백, `ready` 유지
  - **호출 실패** → `failed`
  - **정상** → `star_json`
- §4.2의 상태별 응답 코드(202/409/200)와 재시도 조건(`failed`일 때만)은 설계서 문구와 일치한다.
- 설계와 다르거나 설계가 정하지 않은 부분:
  1. WS `report_ready` 대신 폴링을 쓴다. 03 §4.3이 허용한 폴백이라 결함은 아니다.
  2. **대화 전체 길이에 상한이 없다.** 줄마다 500자로 자르기만 한다. llama-server 컨텍스트는 4096 토큰인데 합계를 막는 장치가 없다 → unit-10-test.md U10-DEF-001.
  3. **워커가 처리 도중 죽으면 `report_status`가 `queued`에 머문다.** job_watchdog는 WS error만 발행하고 상태를 `failed`로 바꾸지 않는다. 그런데 재시도는 `failed`일 때만 되므로 사용자가 복구할 방법이 없다 → U10-DEF-002.

## 3. 알려진 제약

- `_REPORT_MAX_TOKENS=700`은 실측 근거 없이 정한 값이라고 코드 주석에 적혀 있다.
- LLM은 Qwen2.5-1.5B(DEC-025/035)라서 STAR 4개 구간이 늘 깔끔하게 나뉘지는 않는다(2026-09-21 실측).

## 4. 06(단위 테스트) 인계 사항

- 06 결과서: `unit-10-test.md`. **이번 세션 PC에서는 실측이 불가능하다**(DEC-053: GPU·Python·Docker·모델 없음). 정적 검토와 기존 실측 기록 인용으로 작성하고, 개발 서버에서 돌릴 실측 절차를 결과서 §8에 남긴다.
- 재사용 가능한 테스트 코드: 저장소 `backend/tests/`에 리포트 테스트가 아직 없다(test-infra.md §6 원칙상 추가 대상). 실측할 때 `backend/tests/reports/`에 보존할 것.
