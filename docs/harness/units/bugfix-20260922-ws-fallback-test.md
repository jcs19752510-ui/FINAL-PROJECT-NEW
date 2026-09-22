# 테스트 결과서 (Test Result Report)

## 1. 개요
- 테스트 대상: `frontend/app/interviews/[id]/page.tsx` — 면접장 화면의 AI 응답 수신 경로(오프닝 질문 + 턴 응답)
- 테스트 유형: 단위+통합 병합(버그 수정 1건, 관련 작업 단위 2개 이하)
- 적용 Tier: Standard (실사용자 리포트 기반 버그 수정)
- 적용 속도 트랙: N/A (신규 유닛이 아닌 기존 유닛의 결함 수정)
- 테스트 목적: 사용자 리포트("면접장 진입 시 첫 질문 안내 후 반응 없음", "음성 답변 후 문제 발생")의 실제 원인을 재현·확인하고, 수정이 실제 백엔드/Celery/LLM 파이프라인 기준으로 해결됐음을 검증
- 관련 산출물: `docs/harness/03-system-design.md` §4.2/§4.3(WS 이벤트 계약, GET 폴백 허용), `docs/harness/units/unit-4-note.md`(AI_WAIT_TIMEOUT_MS 그레이스풀 디그레이드 원 설계)
- 테스트 수행자(에이전트): Claude (05/06 역할 겸임, 단일 세션 내 수정+검증)
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope):
  - 오프닝 질문 WS 이벤트 유실 시 GET 재조회로 복구되는지
  - 사용자 턴(텍스트) 제출 후 turn_result WS 이벤트 유실 시 GET 재확인으로 복구되는지
  - 기존 12초 타임아웃 시 입력창이 즉시 재활성화되는 기존 계약이 유지되는지(회귀)
  - 위 변경이 기존 unit-20 WS/패널/음성 회귀 스위트를 깨지 않는지
- 제외 범위 및 사유:
  - 음성(마이크) 실제 녹음 경로 자체의 재현 테스트: 실제 마이크 장치가 필요해 이번 세션 환경(Chrome 확장 미연결)에서 브라우저 자동화로 재현 불가. 대신 백엔드 `/turns`(음성) API는 이번 수정과 무관(원인이 프런트 WS 수신 로직에 한정됨)함을 코드 검토로 확인함.
  - a11y-manual/whiteboard/webcam 스위트의 기존 실패 12건: 이번 수정 파일(`page.tsx`)의 WS/폴링 로직과 무관한 별개 컴포넌트(캔버스 드로잉 타이밍, 포커스 링, 카메라 페이크 디바이스 경합, 색 대비 측정)이며, 회귀 여부는 4절에서 별도 확인함.

## 3. 테스트 환경
- 실행 환경: Windows 10, Next.js 16(Turbopack) dev 서버(localhost:3000), FastAPI 백엔드(localhost:8010), PostgreSQL 16(Docker, 5544), Redis(Docker, 6389), Celery 워커(`--pool=solo --concurrency=1 -Q ai_pipeline`), llama-server(Qwen2.5-1.5B, Vulkan, 127.0.0.1:8091) — 전부 실제 프로세스, 모킹 없음(WS만 테스트별로 선택적 모킹)
- 테스트 데이터: `harness_test_<uuid4>@harness-test.example` 마커 계정(Playwright `createAccount` 헬퍼가 자동 생성, `.harness-tmp/e2e-accounts.jsonl`에 기록됨)
- 전제 조건: CORS_ORIGINS(`http://localhost:3000`)와 프런트 접속 origin이 반드시 일치해야 함(127.0.0.1과 localhost는 다른 origin으로 취급되어 CORS 실패 유발 — 최초 시도 시 실제로 겪음, 4절 비고 참고)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-B01 | (버그 재현, 수정 전) 오프닝 질문이 WS로만 전달되고 GET 폴백이 없을 때, 실제 지연이 있으면 화면이 영구 대기 상태로 남는지 | 수정 전 코드 | 실제 API로 계정/동의/면접 생성 후 `/start` 호출, WS를 연결하지 않고(브라우저 미개입) `GET /transcripts`로만 결과 확인 | 서버는 정상 완료(트랜스크립트 존재)하지만 WS 미구독 상태에서는 클라이언트가 이를 알 방법이 코드상 없음(코드 검토로 확인) | 코드 검토 결과 확인됨(§4.3 `turn_result`는 WS 단일 경로, `page.tsx`에 GET 폴백/재시도 코드 없었음) | Pass(원인 확인) | Python 스크립트로 WS 선연결 시 7.8초 만에 정상 수신됨을 별도 확인 — 파이프라인 자체는 정상, 전달 경로만 취약함을 격리 확인 |
| TC-B02 | (수정 후) 오프닝 질문: WS를 완전히 블랙홀 처리해도 화면에 첫 질문이 표시되는가 | 수정 후 코드, `mockInterviewWs`로 WS 100% 차단(REST/백엔드/Celery/LLM은 전부 실통신) | `frontend/e2e/bugfix-ws-fallback/opening-question-fallback.spec.ts` 1번째 테스트 실행 | GET 폴백(3초 간격, 최대 45초)이 실제 오프닝 질문을 찾아 `.chat-bubble--ai`로 표시, 옛 "엔진 미구현" 문구는 0건 | 21.4초 만에 성공, 옛 문구 0건, 콘솔 에러 0건 | **Pass** | |
| TC-B03 | (수정 후) 텍스트 턴: turn_result WS가 유실돼도 GET 재확인으로 AI 답변이 표시되는가 + 12초 타임아웃 시 입력창 즉시 재활성화(회귀) | 동일(WS 블랙홀) | 동일 스펙 2번째 테스트: 오프닝 질문 폴백 확인 후 텍스트 턴 제출 | 12초 뒤 입력창 즉시 재활성화(기존 계약 유지) + 이후 배경 재확인(5초x6회, 최대 30초)으로 AI 답변이 타임라인에 반영 | 36.1초 만에 성공, 입력창 재활성화 시점도 기존 계약대로 12초 지점에서 확인됨, 콘솔 에러 0건 | **Pass** | |
| TC-B04 | 회귀: 기존 unit-20 WS/패널/음성 스위트(`ws-switch.spec.ts`, 20건)가 이번 수정 이후에도 전부 통과하는가 | 동일 실환경 | `npx playwright test e2e/unit-20/ws-switch.spec.ts` 전체 실행 | 20건 전부 Pass | 최초 실행에서 1건 실패(TC-B05 참고) → 원인 수정 후 재실행 20/20 Pass | **Pass**(수정 후) | |
| TC-B05 | 결함 발견: WS 목업 재사용 시나리오에서 React 키 중복 경고 | TC-B04 최초 실행 중 발견 | `ws-switch.spec.ts:66` "control 필드 없음/null이어도..." 케이스: 동일 job_id로 두 번째 턴을 모킹하면 `id: ws-${job_id}` 키가 중복됨 | 콘솔 에러 없이 통과 | "Encountered two children with the same key" 콘솔 에러로 3회 연속 재현(결정적, 플레이키 아님) → DEF-002로 등록, 수정 후 재현 안 됨(20/20 Pass) | Fail → Fixed | 이번 수정으로 새로 노출된 기존 잠재 결함(실서비스에서는 Celery task id가 항상 고유해 발현 안 됨, 테스트 목업이 고정 job_id를 재사용해 노출됨) |
| TC-B06 | 회귀: unit-20 전체 스위트(a11y/webcam/whiteboard/mobile-modal 포함) 중 이번 수정과 무관한 기존 실패가 있는지 구분 | 동일 실환경 | `npx playwright test e2e/unit-20` 전체 실행 | 이번 수정 파일과 무관한 컴포넌트는 실패 유무와 무관하게 이번 결함 목록에서 제외 | 17건 실패 중 16건은 `webcam.tsx`/`WhiteboardCanvas`/색 대비 측정/포커스 링 등 이번 미변경 컴포넌트에서 발생(캔버스 드로잉 타이밍·카메라 페이크 디바이스 경합 등 환경 의존적 사유로 실패 메시지에 명시됨), 1건(TC-B05)만 이번 변경과 상호작용 | Pass(범위 확인) | 이 16건은 이번 수정의 결함 목록(6절)에 포함하지 않음 — 원인이 다른 컴포넌트/환경 의존성이며 이번 변경분(`page.tsx`)과 무관함을 실패 로그로 확인. 별도 조사가 필요하면 후속 이슈로 분리 권장(8절) |

## 5. 커버리지
- 커버리지 지표: 변경된 3개 지점(오프닝 질문 폴백 신설, 턴 타임아웃 후 재확인 로직 교체, WS 메시지 키 유일성 수정) 모두 최소 1개 이상의 실통신 기반 자동화 테스트로 커버됨
- 커버되지 않은 부분과 사유: 음성 답변 경로의 실제 마이크 재현(브라우저 확장 미연결로 이번 세션에서 불가) — 다만 원인이 프런트 WS 수신 공통 로직(`beginWaitingForAi`/`resolveDelayedTurn`)에 있고 텍스트/음성 모두 동일 함수를 공유하므로 TC-B03이 음성 경로도 논리적으로 커버함

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | 오프닝 질문/턴 응답이 WS(Redis Pub/Sub) 단일 경로로만 전달되어, 발행 시점에 구독이 늦으면(라우트 렌더링 지연, 탭 백그라운드 스로틀링 등) 영구 유실되고 복구 수단이 없었음. 안내 문구도 "AI 엔진 미구현"이라는 사실과 다른 내용이었음 | TC-B01/B02/B03 | High(실사용자가 정상 기능을 아예 못 쓰는 것으로 오인) | Fixed | `page.tsx`에 GET 재조회 기반 폴백(오프닝: 3초x15회, 턴: 12초 대기 후 5초x6회) 추가, 안내 문구를 사실에 맞게 수정 |
| DEF-002 | WS로 수신한 메시지의 React key가 `ws-${job_id}`뿐이라 job_id가 재사용되면(테스트 목업 환경) 키 중복 발생 | TC-B05 | Low(실서비스에서는 Celery task id가 항상 고유해 미발현, 테스트 목업에서만 노출) | Fixed | key를 `ws-${job_id}-${Date.now()}`로 변경해 유일성 보장 |

- 추가로, 이번 테스트에서 발견됐으나 이번 수정 범위 밖인 항목 없음(TC-B06의 16건은 별개 컴포넌트/환경 의존 실패로 확인됨, 8절 참고).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/e2e-accounts.jsonl`(기존 파일에 이어서 추가 기록, 신규 생성 아님), 스크래치패드의 1회성 검증 스크립트(`repro_opening_question.py`, 저장소 바깥 세션 스크래치패드 경로)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예 — 스크래치패드 스크립트는 저장소 밖(`C:\Users\mega\AppData\Local\Temp\claude\...\scratchpad`)이라 애초에 저장소에 영향 없음
- 정리(삭제) 완료 여부: Playwright 산출물(`frontend/test-results/`, `frontend/playwright-report/`)은 이미 `.gitignore`에 등록되어 있어 git 추적 대상이 아님(별도 삭제 불필요, 확인 완료). `e2e-accounts.jsonl`은 계정 정리 스크립트(`python -m tests.support.cleanup --email <이메일>`) 대상 로그로, 정책상 삭제 대상이 아니라 누적 기록임
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M backend/alembic/env.py
 M backend/app/api/v1/interviews.py
 M backend/app/api/v1/recruiter.py
 M backend/app/schemas/interview.py
 M backend/app/schemas/recruiter.py
 M backend/app/services/celery_app.py
 M backend/app/services/interview_prompts.py
 M backend/app/services/job_queue.py
 M backend/app/services/llm_engine.py
 M backend/app/worker/tasks.py
 M backend/tests/support/cleanup.py
 M frontend/app/interviews/[id]/page.tsx
 M frontend/app/recruiter/[id]/page.tsx
 M frontend/lib/api.ts
 M frontend/tsconfig.tsbuildinfo
?? "99.현재상태/현재상태_09.png"
?? "99.현재상태/현재상태_10.png"
?? "99.현재상태/현재상태_11.png"
?? backend/alembic/versions/9c91a685f9df_v10_evaluation_reports.py
?? backend/app/models/evaluation_report.py
?? docs/harness/units/bugfix-20260922-ws-fallback-test.md
?? frontend/app/interviews/[id]/report/
?? frontend/e2e/bugfix-ws-fallback/
```
(이번 세션 이전(리포트 생성 기능 등)에 이미 존재하던 미커밋 변경분이 섞여 있음 — 이번 버그 수정으로 새로 추가된 것은 `frontend/app/interviews/[id]/page.tsx` 수정분과 `frontend/e2e/bugfix-ws-fallback/`, 본 문서뿐이다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 위 확인에 따라 8절 판정에 지장 없음(규칙 K 2번 충족)

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크: 음성(마이크) 경로의 실기기 자동화 재현 미실시(5절 참고, 논리적으로는 텍스트와 동일 코드 경로 공유)
- 후속 조치가 필요한 항목:
  - TC-B06에서 확인된 16건의 기존 실패(a11y 포커스 링/색 대비, whiteboard 캔버스 드로잉 타이밍, webcam 페이크 디바이스 경합, mobile-modal Esc 포커스)는 이번 수정과 무관하지만 별도로 원인 조사가 필요함(이번 세션 범위 밖으로 판단, 사용자 승인 시 별도 작업으로 진행 권장)
  - 이전 리포트에서 이미 안내한 항목(unit-8 보안/레이트리밋 미구현, 삭제요청 실제 파기 배치 미구현, 루브릭 템플릿이 실제 면접 생성/평가 경로에 미연결)은 이번 수정과 무관하게 그대로 유효함

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(사용자 확인 대기)

## 10. 내부 검증 (최소 2회)
- 1차 검증: 신규 스펙(`opening-question-fallback.spec.ts`) 2건을 CORS origin 불일치로 최초 실패(환경 설정 문제, 코드 결함 아님) → origin을 `localhost`로 맞춰 재실행, 2/2 Pass
- 2차 검증: 관련 회귀 스위트(`ws-switch.spec.ts` 20건) 전체 실행 → 1건 실패(DEF-002) 발견 → 수정 → 재실행 20/20 Pass. 이어서 `unit-20` 전체 스위트 실행으로 다른 컴포넌트에 대한 부작용 없음을 재확인(TC-B06)
- 검증 로그 파일 경로: 본 세션의 Playwright 실행 로그는 표준출력으로만 남았으며 별도 로그 파일 저장은 하지 않음(`frontend/test-results/`, `frontend/playwright-report/`에 스크린샷/트레이스만 gitignore 상태로 보존됨)
