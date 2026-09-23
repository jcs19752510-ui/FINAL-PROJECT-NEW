# 테스트 결과서 (Test Result Report) — unit-10 (REQ-009 STAR 리포트 생성) · 소급 정적 검토판

## 1. 개요
- 테스트 대상: 모듈(작업단위) unit-10. 리포트 생성 전 계층 — `POST /interviews/{id}/end`의 enqueue, `process_report_generation_job`, `generate_report_response`/`ReportLLMOutput`/`StarOutput`, `GET /interviews/{id}/report`, `POST /interviews/{id}/report/regenerate`, `frontend/app/interviews/[id]/report/page.tsx`
- 테스트 유형: 단위
- 적용 Tier: High(DEC-002)
- 적용 속도 트랙: L3(DEC-031)
- 테스트 목적: 하네스 절차 없이 구현된 REQ-009 코드(unit-10-note.md §0)가 03 설계서 §4.2/§4.4와 04 [C-10]/[C-11]을 충족하는지 확인하고, 추적 매트릭스를 실제 상태로 바로잡는다.
- 관련 산출물: `docs/harness/units/unit-10-note.md`, 03-system-design.md §3·§4.2·§4.4·§5.4, 04-ux-design.md [C-10]/[C-11], `docs/harness/decisions.md` DEC-031/053/054
- 테스트 수행자(에이전트): 본 세션(오케스트레이터, 06 역할)
- 테스트 일시: 2026-09-23

> **이 결과서의 한계(맨 먼저 읽을 것):** 이번 세션 PC에서는 코드를 실행할 수 없다(Python 미설치, Docker 미기동, GPU 없음, `backend/var/` 모델·바이너리 없음, DEC-053).
> 그래서 이 결과서의 새 케이스는 모두 **정적 검토(코드 읽기·grep)**다. "실행 결과"라고 적은 것은 **기존 개발 서버에서 이미 실측된 기록을 인용한 것**이며, 이번에 다시 실행하지 않았다.
> 이 결과서만으로는 L3 정식 06의 "실행 검증"을 충족하지 못한다. 따라서 **판정은 PASS가 아니다**(9절).

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope):
  - 설계 계약 대조: 상태 전이(none/queued/ready/failed), HTTP 응답 코드, 재시도 조건, 파싱 실패와 호출 실패의 구분, 권한(본인+recruiter 열람, 재시도는 본인만)
  - 출력 검증: 점수 범위, 추천 등급 화이트리스트, STAR 뭉침 대응
  - 렌더링 보안(REQ-036), 면책 문구(REQ-031) 동반 노출
  - 장애·경계 조건: 긴 대화, 워커 중단
- 제외 범위 및 사유:
  - **실제 실행(HTTP·LLM·DB)**: 이번 PC에 실행 환경이 없음(DEC-053). 개발 서버에서 돌릴 실측 절차는 8절에 적었다.
  - 루브릭 점수·평가 근거(REQ-010/012): unit-11 결과서 범위.
  - 07 통합(Feature E 전체): 06이 PASS가 아니므로 착수 조건 미충족(규칙 D).

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro, Git Bash/PowerShell. 코드 읽기와 grep만 사용. 런타임 없음.
- 검토 기준 코드: `PROD` 브랜치 HEAD `05f8d1a`(2026-09-23 13:06). 리포트 관련 파일은 `18d5ceb` → `a182388` → `2def886` 이후 변경 없음.
- 인용한 기존 실측 기록: 개발 서버(i5-1135G7/GTX1650Ti, DEC-013)에서 수행된 `bugfix-20260922-event-loop-hang-test.md` TC-H04/H05, `unit-23-test.md` TC-003~009
- 전제 조건: 없음(정적 검토)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | `/end` → `queued` + job enqueue (§4.2) | 코드 HEAD | `interviews.py::end_interview` 읽기 | live만 종료, `report_status=queued` 커밋 후 enqueue | 코드와 일치(live 아니면 409, commit 후 `enqueue_report_generation_job`) | Pass(정적) | |
| TC-002 | 상태별 GET 응답 (§4.2) | 〃 | `get_report` 읽기 | none→409, queued→202 processing, failed→409 `REPORT_GENERATION_FAILED`, ready→200 | 4개 분기 모두 일치 | Pass(정적) | |
| TC-003 | 재시도 조건 (§4.2 갭5) | 〃 | `regenerate_report` 읽기 | `failed`일 때만 → queued + 재enqueue, 그 외 409 | 일치. 소유자만 가능(`_get_own_interview`) | Pass(정적) | |
| TC-004 | 권한 경계(열람) | 〃 | `_get_report_viewable_interview` 읽기 | 본인 또는 recruiter만 열람, 그 외 403, 없으면 404 | 일치 | Pass(정적) | 03 §6.1 단일조직 MVP 정책 |
| TC-005 | 파싱 실패 폴백 (§4.4) | 〃 | `generate_report_response` + 워커 `except ReportParsingFailed` 읽기 | 1회 재시도 후 `summary_text`=원문, `ready` 유지, 점수 null | 일치 | Pass(정적) | 표시 품질 문제는 DEF-003 |
| TC-006 | 호출 실패 → failed (§4.4) | 〃 | 워커 `except LlmGenerationError` 읽기 | `failed` + WS error | 일치 | Pass(정적) | |
| TC-007 | 점수·등급 화이트리스트 | 〃 | `ReportLLMOutput` 읽기 | 점수 1~5 범위, 추천 등급 3종 Literal | 일치(`Field(ge=1, le=5)`, `Literal[...]`) | Pass(정적) | unit-23 TC-009에서 범위 밖 값 거부 실측(인용) |
| TC-008 | STAR 뭉침 대응 | 〃 | `StarOutput._coerce_flat_string` 읽기 | 문자열 하나면 situation에 담아 검증 통과 | 일치 | Pass(정적) | 2026-09-21 실측 결함 대응분 |
| TC-009 | 렌더링 XSS 방어(REQ-036) | 〃 | `grep -rn dangerouslySetInnerHTML frontend/app` | 리포트 화면 사용 0건 | 0건 | Pass(정적) | unit-27 결과와 같음 |
| TC-010 | 면책 문구 동반(REQ-031) | 〃 | `ReportOut.disclaimer`, `report/page.tsx` 읽기 | 모든 응답·화면에 고정 문구 | 일치(`REPORT_DISCLAIMER`, 배너 렌더) | Pass(정적) | |
| TC-011 | 긴 면접의 컨텍스트 초과(경계값) | 〃 | 워커 입력 조립부 + `llm_engine._CONTEXT_SIZE` 읽기 | 입력 전체 길이 상한이 있어야 함 | 줄당 500자만 자르고 합계 상한 없음. 컨텍스트 4096 − 출력 700 | **Fail(정적)** | DEF-001 |
| TC-012 | 처리 중 워커 중단(예외·복구) | 〃 | `job_watchdog.py` + 재시도 조건 대조 | 유실 job은 `failed`로 전이되거나 사용자 복구 경로가 있어야 함 | watchdog은 WS error만 발행, 상태는 `queued`에 머묾 → 재시도 409, 화면은 무한 폴링 | **Fail(정적)** | DEF-002 |
| TC-013 | 파싱 실패 원문 노출 | 〃 | 폴백 경로 + 화면 `summary_text` 렌더 읽기 | 사람이 읽을 요약만 표시 | LLM 원문(깨진 JSON일 수 있음)을 그대로 표시. 리포트 출력에는 REQ-039 유출 검사 미적용 | **Fail(정적)** | DEF-003 |
| TC-014 | 정상 경로 E2E(지원자) | 기존 개발 서버 | **인용**: event-loop-hang-test TC-H04 | 면접 5턴 → 종료 → ready, 점수·STAR·추천 반환 | `ready`, `overall_score=4.0`, STAR 4필드·추천·면책 정상(2026-09-22) | Pass(인용) | 이번에 재실행 안 함 |
| TC-015 | 정상 경로 E2E(채용담당자) | 〃 | **인용**: TC-H05 | 같은 리포트 열람 | 200, `report_available:true`, 같은 데이터(2026-09-22) | Pass(인용) | 이번에 재실행 안 함 |

> 동시성/부하: 리포트 job은 GPU 큐 `--pool=solo` 직렬 처리(DEC-019)라 단위 범위의 동시성 케이스는 없다. 부하는 08 범위.

## 5. 커버리지
- 커버리지 지표: **기능(설계 계약 항목) 커버리지** 15개 케이스. §4.2 리포트 관련 3개 엔드포인트의 전 분기 + §4.4 3개 경로 + 경계 2건 + 보안 2건. **라인/브랜치 커버리지는 측정 불가**(실행 환경 없음).
- 커버되지 않은 부분과 사유:
  - 전 케이스의 **실제 실행**: 이번 PC 환경 부재(DEC-053). TC-014/015만 기존 실측 인용이다.
  - 프런트 폴링·재시도 버튼의 브라우저 동작: 미실행
  - `report_ready` WS 이벤트: 화면이 폴링을 쓰므로 소비처 없음(설계 허용). 발행 자체는 미실행

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | 리포트 입력(대화 전체)에 합계 길이 상한이 없다. 긴 면접은 컨텍스트(4096 토큰, 출력 700 예약)를 넘겨 llama-server 오류 → `failed`가 되고, **재시도해도 같은 입력이라 계속 실패**할 수 있다 | (개발 서버) 한국어 답변 약 500자 × 10턴 이상으로 면접 후 종료 → `/report` 확인. 정적 근거: `tasks.py` 입력 조립부에 합계 제한 없음 | **잠정 High**(정적 추정, **미실측** — 한 번 발생하면 재시도로도 복구되지 않는 영구 실패라 High로 분류. 실측에서 임계 턴 수가 실사용 범위(약 10턴) 밖으로 확인되면 Medium으로 재분류) | Open | 수정 안 함(DEC-053 범위). 후보: 앞부분 요약 또는 최근 N턴만 사용, 토큰 예산 계산 |
| DEF-002 | 워커가 처리 중 죽으면 `report_status`가 `queued`에 머문다. 리포트 job도 `job_queue.register_job`으로 watchdog 감시 대상이지만, watchdog은 STARTED 후 150초(`_STARTED_TIMEOUT_SECONDS`)가 지나면 WS `error`만 발행하고 DB 상태는 바꾸지 않는다. 리포트 화면은 WS를 쓰지 않고 폴링만 해서 이 오류도 받지 못한다. 재시도는 `failed`에서만 되고 화면은 3초마다 끝없이 폴링한다(상한 없음) → 사용자가 복구할 방법이 없다 | (개발 서버) `/end` 직후 워커 프로세스 종료 → 재기동 → `/report` 계속 202, `/regenerate` 409 | Medium(정적, 미실측) | Open | 수정 안 함. 후보: watchdog이 report job 유실 시 `failed`로 전이, 화면 폴링 상한 |
| DEF-003 | 파싱 실패 폴백이 LLM 원문을 그대로 `summary_text`로 사용자에게 보여준다(깨진 JSON 조각일 수 있음). 턴 응답과 달리 리포트 출력에는 시스템 프롬프트 유출 검사(REQ-039)가 없다 | (개발 서버) LLM 응답을 스키마 위반으로 모킹 → 화면 확인 | Medium(정적) | Open | 수정 안 함. 후보: 원문은 서버 로그에만 두고 사용자에게는 안내 문구, 또는 유출 마커 검사 적용 |

- 결함 0건이 아닌 근거: TC-011~013(정적 검토)

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: **해당 없음** — venv, 임시 DB, 서버 프로세스를 하나도 만들지 않았다(정적 검토만). 만든 파일은 저장소 문서(이 결과서, 노트, 검증 로그)뿐이다.
- `.harness-tmp/` 하위에서만 생성했는가: [x] 예(생성물 없음) / [ ] 아니오
- 정리(삭제) 완료 여부: 정리 대상 없음. 세션 시작 시 `automation/harness-janitor.sh` 결과: "잔여 임시 아티팩트 없음"
- 정리 후 `git status` 실행 결과:
```
 M docs/harness/decisions.md
 M docs/harness/traceability.md
?? docs/harness/units/unit-10-note.md
?? docs/harness/units/unit-10-test.md
?? docs/harness/units/unit-11-note.md
?? docs/harness/units/unit-11-test.md
?? docs/harness/verify-log_unit-10-test.md
?? docs/harness/verify-log_unit-11-test.md
```
(2026-09-23, 모든 문서 작성 후 실제 실행한 `git status --short` 원문. 이번 작업 산출물 8건뿐이고 코드 변경은 없다. `.harness-tmp/`는 존재하지 않음 — `ls: cannot access '.harness-tmp'`)
- 강제 중단이 있었는가: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - **모든 판정이 정적 검토 기반이다.** 코드 경로를 잘못 읽었을 가능성은 실행으로만 배제할 수 있다.
  - DEF-001의 실제 임계 턴 수(몇 턴부터 실패하는지)는 토크나이저 실측이 있어야 알 수 있다.
- 후속 조치가 필요한 항목 — **개발 서버에서 돌릴 실측 절차**(test-infra.md 규약 준수, 테스트 코드는 `backend/tests/reports/`에 보존):
  1. TC-001~006 재실행: 계정 팩토리로 candidate/recruiter 생성 → 동의 → 면접 생성·시작 → 텍스트 3턴 → `/end` → `/report` 폴링(202→200) → recruiter 열람 → 타 지원자 403
  2. TC-005/006 재현: LLM 호출부를 모킹해 파싱 실패(→ ready + summary_text)와 호출 실패(→ failed → regenerate 202 → ready)를 검증
  3. DEF-001 재현: 긴 답변 10턴 이상 → 리포트 결과 확인
  4. DEF-002 재현: 처리 중 워커 종료 → 상태 확인
  5. 프런트: Playwright로 리포트 화면 폴링 → 표시 → 실패 시 재시도 버튼 확인
  6. **실행 후 규칙 K-6 헬스체크 필수**(부하성 폴링 포함 시)
  - 결함 수정 방향은 사용자 결정 대기(DEC-054)

## 9. 결론 및 판정
- [ ] PASS — 다음 단계 진행 가능
- [ ] CONDITIONAL PASS — 조건:
- [x] FAIL — 사유 및 재작업 요청 사항:
  1. **L3 정식 06의 실행 검증이 없다.** 이번 PC에서는 실행할 수 없었다(DEC-053). 8절 실측 절차를 개발 서버에서 수행해야 한다.
  2. 정적 검토로 결함 3건(High 1, Medium 2)을 발견했다. 수정 방향은 사용자 결정 대기(DEC-054).
  - 참고: 정상 경로 자체는 기존 개발 서버 실측(TC-014/015)에서 동작이 확인됐다. "리포트가 전혀 안 된다"는 뜻이 아니라, **하네스 기준의 완료 조건을 충족하지 못했다**는 뜻이다.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약(작성자 관점): 결함 3건 발견·수정(v0→v1).
  - 7절 `git status`를 실제 출력 대신 예상 목록으로 적음
  - 10절 요약을 검증 전에 미리 적음
  - DEF-002 원인 근거(watchdog 150초 동작, 화면 폴링) 누락
- 2차 검증 결과 요약(처음 받는 심사자 관점): 결함 1건(DEF-001을 실측 없이 High로 확정). "잠정 High" + 재분류 기준으로 수정(v1→v2). FAIL 판정이 과한지 검토 후 유지.
- 3차 검증 결과 요약: 결함 0건, 최종(실제 `git status` 반영, traceability 일치 확인).
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-10-test.md`
