# unit-4 구현 노트 — Feature C. 대화형 인터뷰 엔진: 텍스트 채팅 인터페이스 (REQ-003)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §3(TRANSCRIPTS ERD), §4.2(`POST /interviews/{id}/turns`, opening_question), §4.3(WS 채널 역할 분리, 서버→클라이언트 이벤트 스키마), §6.2(DEC-023 — 생체정보 동의는 음성 전용), `docs/harness/04-ux-design.md`(v2, PASS) [C-06] 면접장(메인), `docs/harness/units/unit-2-note.md`/`unit-3-note.md`(세션 상태머신, job_queue.py 스텁 인터페이스, `_get_own_interview`/`_apply_lazy_expiry` 재사용), `docs/harness/traceability.md` REQ-003 행

## 1. 구현 범위

오케스트레이터 지시대로 **텍스트 턴만** 다룬다. 음성(multipart) 제출·STT·TTS(REQ-004~006)는 unit-5/6 범위, LLM 꼬리질문 생성(REQ-007)은 unit-7 범위이며 이번 유닛은 그 두 하위 컴포넌트가 아직 없다는 전제 위에서 **API 계약과 텍스트 저장 경로만 실제로 완성**한다.

### 백엔드

- `backend/app/models/transcript.py`: 03-design §3.1 ERD `TRANSCRIPTS` 그대로(`interview_id` FK, `turn_index` int, `speaker` enum(ai/user), `input_mode` enum(text/voice), `content_text` text, `audio_ref` nullable, `created_at`). `question_id`는 QUESTIONS 테이블(unit-7 책임)이 아직 없어 unit-2의 `rubric_template_id` 선례를 그대로 따라 FK 제약 없이 nullable 컬럼만 만들었다.
- Alembic `0df1434883f2_v3_transcripts`(down_revision=`fdd74cee7615`)로 `transcripts` 테이블 생성, 실제 PostgreSQL(`final-project-db`)에 적용 완료. (참고: 본 작업 중 다른 병렬 작업 단위가 `8a55fda78a42_v4_deletion_requests`를 내 revision 위에 이어 붙여, 최종 head는 `8a55fda78a42` — 브랜칭 없이 선형 체인 유지 확인함.)
- `backend/app/api/v1/interviews.py`에 추가:
  - `POST /interviews/{id}/turns` — 본인 소유 + lazy expiry 적용 후 `status==live`인 경우만 허용(그 외 409, 만료는 410). 텍스트를 `TRANSCRIPTS(speaker=user, input_mode=text)`로 **실제로 커밋**하고, `job_queue.enqueue_turn_job()`으로 job_id를 발급해 `202 {job_id}` 반환. DEC-023에 따라 텍스트 제출은 `biometric_voice` 동의 검사와 완전히 무관하다(코드에 어떤 동의 검사도 넣지 않음 — 검사 자체가 음성 제출로 이동됐기 때문).
  - `GET /interviews/{id}/transcripts` — **(신규, additive 편차, §2-1 참고)** 대화 이력 조회, `turn_index` 오름차순.
- `backend/app/schemas/transcript.py`: `TurnCreate`(text, 1~4000자), `TranscriptOut`, `TurnAcceptedResponse`.
- `backend/app/services/job_queue.py`: `enqueue_turn_job()` 추가(기존 `enqueue_opening_question_job`/`enqueue_report_generation_job`과 동일한 "정당한 순서상 스텁" 패턴 — job_id만 발급).
- `backend/app/api/v1/ws.py`(신규): `/ws/interviews/{interview_id}` WebSocket 게이트웨이.
  - 인증: 쿼리 파라미터 `?token=`(브라우저 WebSocket API가 커스텀 헤더를 지원하지 않아 §6.1 JWT를 쿼리로 전달) + 본인 소유 세션 확인, 실패 시 `WS_1008_POLICY_VIOLATION`로 연결 거부.
  - `ConnectionManager`(인메모리, 단일 프로세스 전제 DEC-006/007과 정합)로 interview_id별 연결을 관리하고 `broadcast()` 진입점을 노출 — 이 진입점이 미래의 AI Worker(unit-7)가 호출할 유일한 push 경로.
  - 클라이언트→서버는 §4.3 화이트리스트대로 `cancel_queue_wait`만 수신하고 그 외/비-JSON 메시지는 조용히 무시(연결 유지).
- `backend/app/main.py`: `ws_router`를 `/api/v1` 프리픽스 없이 등록(설계서 §4.3 경로가 `/ws/interviews/{id}`이기 때문).

### 프론트엔드

- `frontend/app/interviews/[id]/page.tsx`(신규): [C-06] 면접장의 **텍스트 턴 범위**만 구현 — 채팅 타임라인(AI/사용자 버블), 텍스트 입력창+전송(4000자 제한, 실시간 카운터), 초기 진입 시 `GET /interviews/{id}` + `GET /interviews/{id}/transcripts`로 세션 상세/이력 로드, WebSocket 연결로 `stage_update`/`turn_result`/`error` 수신.
- `frontend/lib/api.ts`: `InterviewOut`/`InterviewDetailOut`/`TranscriptOut`/`TurnAcceptedResponse` 타입, `getInterview`/`listTranscripts`/`submitTextTurn`/`interviewWsUrl` 추가.
- `frontend/app/globals.css`: `.interview-room` 계열 클래스(04-ux-design §3 토큰 그대로 재사용, 별도 신규 토큰 추가 없음).

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `GET /interviews/{id}/transcripts`를 03-design §4.2 표에 없음에도 신규 구현 | [C-06]의 "로딩(초기 진입) — 이전 대화 이력 로드" 상태(04-ux-design §2 [C-06])가 구조적으로 요구하는 조회 API인데, 03-design §4.2 표 어디에도 대화 이력을 되읽는 GET이 없다. unit-3이 `GET /interviews/{id}`를 동일한 논리(구조적으로 필요 + 해석이 갈리지 않음)로 additive 신설한 선례를 그대로 따름 — 명명 규칙도 형제 엔드포인트(`/code-submissions`, `/whiteboard`)와 동일하게 맞췄다 | 낮음(순수 추가 GET, 제거해도 기존 계약 영향 없음) |
| 2 | AI 응답 생성(꼬리질문 LLM 호출)이 전혀 동작하지 않음 — `job_queue.enqueue_turn_job()`이 job_id만 발급하는 스텁 | 오케스트레이터 지시대로, LLM(unit-7)이 아직 없다. `POST /turns`는 사용자의 텍스트 답변을 실제로 `TRANSCRIPTS`에 저장하고 202 계약을 완성하는 것까지가 이번 유닛의 책임이며, 그 뒤 AI Worker가 큐를 소비해 WS로 `stage_update`→`turn_result`를 push하는 것은 unit-7 범위다. `job_queue.py`/`ws.py` 양쪽 모듈 docstring에 이 경계를 명시했다 | 낮음(호출부 변경 없이 job_queue.py 내부와 ws.py의 broadcast 호출부만 추가하면 됨) |
| 3 | WebSocket 이벤트가 이 유닛에서는 절대 도착하지 않음(스텁 경계 2와 동일 원인) — 06단계가 실제 `stage_update`/`turn_result` 수신을 기대하는 테스트를 설계하면 영원히 오지 않는다 | 위와 동일 | 해당 없음(정보성 경고) |
| 4 | `POST /turns`에 `biometric_voice` 동의 검사를 전혀 넣지 않음 | 03-design v2 §4.2/§6.2(DEC-023)가 **명시적으로** 이 검사를 "음성(multipart) 제출일 때만" 적용하라고 확정했으므로, 텍스트 전용인 이번 유닛에서는 검사 코드 자체를 넣지 않는 것이 설계서와 100% 일치하는 구현이다(빠뜨린 것이 아니라 의도적 제외) | 낮음(unit-5가 음성 경로에 별도로 추가) |
| 5 | 턴 응답에 `turn_index`를 반환하지 않음(202 응답은 `job_id`만) | 03-design §4.2 예시가 "`202 {job_id}`"로만 명시했고, unit-2의 "설계 예시보다 넓은 응답 필드는 additive로 허용"과 반대로 이번엔 **좁게(설계 예시 그대로)** 구현했다 — 이유는 `turn_index`가 실제로는 서버 커밋 시점에 확정되므로 응답에 넣는 것 자체는 가능했으나, 오케스트레이터 지시("API 계약은 설계서대로 완성")를 문자 그대로 따르는 것이 이번엔 더 안전하다고 판단(다른 필드 확장이 06단계의 계약 검증에 혼란을 줄 수 있어 최소화) | 낮음(추가 필드이므로 나중에 넣어도 하위호환 유지) |
| 6 | 프런트 `interview-room` 화면은 [C-06] 구성요소 전체가 아니라 텍스트 채팅 부분만 구현 — 음성 녹음 버튼, 웹캠 프리뷰, 코드/화이트보드 패널 전환, 대기열 취소(`cancel_queue_wait` 전송 UI)는 없음 | 각각 unit-5(음성)/unit-16(웹캠)/unit-9(코드)/unit-17(화이트보드) 책임이거나, 실제 큐가 없어(§2-2/3) 취소할 대상 자체가 없는 기능이라 화면에 노출하지 않았다(있지도 않은 기능을 보여주는 것이 오히려 오해를 유발) | 낮음(각 담당 유닛이 같은 페이지에 패널만 추가하면 됨) |
| 7 | [C-03]~[C-05](면접 목록/사전고지/장치점검) 화면이 없어 `/interviews/[id]`로 진입하는 정상 경로 자체가 프런트에 없음 | unit-2/3이 이미 "API 전용" 범위로 Feature B 프런트를 만들지 않았고, 이번 유닛도 Feature C(REQ-003)로 범위가 좁혀져 있어 그 앞단 화면들을 만드는 것은 범위 외 확장이 된다. 검증은 API로 세션을 만들고 URL을 직접 열람하는 방식으로 수행했다(§4 참고) | 낮음(Feature B/H 담당 유닛이 완성되면 자연스럽게 링크만 추가하면 됨) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **CONSENTS/세션 준비**: unit-2와 동일하게 `ai_interview_notice` 동의를 DB에 직접 INSERT해야 `/start`를 태울 수 있다(unit-2-note.md §3 SQL 재사용). `biometric_voice` 동의는 이번 유닛의 어떤 테스트에도 필요 없다(텍스트 전용이므로).
- **AI 응답은 절대 오지 않는다**: `POST /turns` 후 WebSocket으로 `stage_update`/`turn_result`를 기다리는 테스트는 이번 유닛 범위에서 실패한다(§2-2/3 스텁 경계). 06단계 인수조건(§5)은 "사용자 턴이 저장되고 202가 온다"까지만 검증하도록 범위를 좁혔다.
- **프런트 접근 경로**: 로그인 후 `/interviews/{id}`로 직접 이동해야 화면이 보인다(§2-7). `sessionStorage`에 `access_token`이 있어야 하므로, 06단계가 브라우저로 검증하려면 먼저 `/login`으로 로그인해 토큰을 저장한 뒤 주소창에 인터뷰 id를 붙여 이동해야 한다.
- **그레이스풀 디그레이드 타이밍**: 턴 제출 후 12초(`AI_WAIT_TIMEOUT_MS`, 프런트 구현 세부값 — 설계서에 명시된 값 아님) 안에 WS 이벤트가 없으면 "AI 응답 엔진은 아직 준비 중입니다" 안내로 전환되고 입력이 다시 열린다. 06단계가 이 화면을 열어놓고 12초 이상 기다리면 이 문구가 뜨는 것이 **정상 동작**이다(버그 아님).
- **PostgreSQL/venv**: unit-1~3과 동일하게 `docker compose up -d`(`final-project-db`, 포트 5544)와 `.harness-tmp/venv_05_unit1` 재사용. 새 패키지 추가 없음(`uvicorn[standard]`에 이미 포함된 `websockets`로 WS 구현).
- **병렬 작업 알림**: 이번 유닛 작업 중 다른 작업 단위(REQ-014/015/016 계열로 추정, `ops.py`/`consents.py`/`deletion_request.py`/`frontend/app/admin/`)가 동시에 진행되어 `backend/app/main.py`, `backend/alembic/env.py`, `frontend/app/globals.css`, `frontend/lib/api.ts`에 추가 변경이 함께 반영되어 있다. 이 유닛(unit-4)이 만든 변경은 위 §1에 열거한 파일/구간뿐이며, 그 외 항목은 다른 작업 단위의 산출물이니 06단계가 unit-4 범위를 검증할 때는 §1/§5만 기준으로 삼으면 된다. Alembic 체인은 `fdd74cee7615 → 0df1434883f2(본 유닛) → 8a55fda78a42(다른 유닛)`로 선형이며 브랜칭 없음을 확인했다.

## 4. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app alembic/env.py` → **통과(에러 0건)**(다른 병렬 유닛이 추가한 파일 포함 전체 기준으로도 통과 확인).
- 프론트엔드: `npm run lint` 전체 실행 시 다른 병렬 유닛의 `frontend/app/admin/ops/page.tsx`에서 1건(`react-hooks/set-state-in-effect`) 발생 — **이 유닛(unit-4)이 만든 파일이 아니므로 범위 밖**. unit-4 소유 파일만 한정해 `npx eslint "app/interviews/[id]/page.tsx" lib/api.ts` 실행 시 **에러 0건**. `npx tsc --noEmit`(프로젝트 전체) **에러 0건**, `npm run build`(Next.js 프로덕션 빌드) **성공**(`/interviews/[id]`가 동적 라우트로 정상 포함됨).

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 모든 편차와 사유 기록. 나머지(TRANSCRIPTS 스키마, 202 계약, WS 이벤트 JSON 스키마, DEC-023 텍스트 예외)는 03-design §3/§4.2/§4.3/§6.2, 04-ux-design [C-06] 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — 세션 없음(404), 소유권 없음(403), 인증 없음(401), 상태 불일치(409), 만료(410), 입력값 부적합(422)까지 명시적 `AppError`/Pydantic 검증으로 처리. WS 쪽도 인증 실패(정책위반 close), JSON 파싱 실패(무시하고 연결 유지), 화이트리스트 외 메시지(무시)를 모두 명시적으로 처리하며 예외를 조용히 삼키는 `except: pass`류 코드는 없음(WS broadcast의 `except Exception`은 죽은 연결 하나를 로그 남기고 제거하는 의도된 방어 코드).
- [x] 시스템 경계(사용자 입력) 검증 — `TurnCreate.text`는 Pydantic으로 1~4000자 강제(실제 curl로 빈 문자열/누락/4001자 케이스 검증, §6). WS 수신 메시지도 JSON 파싱 실패/타입 화이트리스트 검사를 거친다. path param `interview_id`는 FastAPI가 UUID로 강제 검증.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음(기존 JWT 설정 재사용).
- [x] 신규 외부 의존성 실존 확인 — 신규 패키지 추가 없음. WS 구현은 이미 `requirements.txt`의 `uvicorn[standard]`가 끌어오는 `websockets`(설치 확인: `pip show websockets` → 17.1)를 그대로 사용했다.
- [x] 범위 외 변경 없음 — 음성/STT/TTS/LLM/코드에디터/화이트보드/recruiter 대시보드는 만들지 않았다. `CONSENTS` 검사도 DEC-023이 명시한 그대로 텍스트 경로에 넣지 않았다(§2-4). 다른 병렬 작업 단위의 파일(§3 "병렬 작업 알림")은 건드리지 않았다.

## 6. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용, `.harness-tmp/venv_05_unit1` 재사용.
2. `alembic revision --autogenerate -m "v3_transcripts"` → `0df1434883f2`(down_revision=`fdd74cee7615`) 생성 → `alembic upgrade head` 적용 확인. 이후 다른 병렬 유닛이 `8a55fda78a42`를 그 위에 이어붙여 최종 head가 됨 — `alembic current`/`alembic heads` 모두 `8a55fda78a42 (head)` 단일 head로 일치 확인(브랜칭 없음).
3. `ruff check app alembic/env.py` 통과.
4. `uvicorn app.main:app --port 8024`(이후 프런트 연동 검증 시 `--port 8000`으로 재기동)로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인 → `POST /interviews` → 동의 INSERT → `/start` → `202 live`
   - `scheduled`(시작 전) 상태에서 `/turns` 시도 → `409 VALIDATION_ERROR` 확인
   - live 상태에서 한글 텍스트(멀티바이트, 파일 기반 요청으로 쉘 인코딩 이슈 우회) 턴 제출 → `202 {job_id}`, ASCII 텍스트 턴 추가 제출 → `202`
   - `GET /transcripts` → `turn_index` 0,1 순서로 두 턴 모두 정확히 반환 확인
   - 빈 문자열/필드 누락/4001자 텍스트 → 각각 `422 VALIDATION_ERROR`(Pydantic 메시지 포함) 확인
   - 토큰 없이 `/turns` → `401`, 존재하지 않는 interview id → `404`
   - 다른 candidate 토큰으로 남의 세션에 `/turns`/`/transcripts` 시도 → 둘 다 `403 AUTH_FORBIDDEN`
   - `/end`로 completed 전환 후 `/turns` → `409 VALIDATION_ERROR`
   - 별도 세션에서 `started_at`을 25시간 전으로 조작(unit-3 선례와 동일한 SQL) 후 `/turns` → `410 SESSION_EXPIRED` 확인
   - Python `websockets` 클라이언트로 `/ws/interviews/{id}`: (a) 정상 토큰+본인 세션 연결 후 `cancel_queue_wait`/화이트리스트 외 타입/비-JSON 메시지 전송 → 연결 유지 확인, (b) 토큰 없이 연결 → 핸드셰이크 거부(`InvalidStatus`) 확인, (c) 잘못된 토큰 → 거부 확인, (d) 다른 candidate의 유효 토큰으로 본인 것이 아닌 세션에 연결 → 거부 확인
   - 서버 로그(`uvicorn_05_unit4*.log`)에 기대하지 못한 스택트레이스/예외 없음을 grep으로 확인
5. 프런트: `npm run lint`(unit-4 소유 파일 한정 무결점), `npx tsc --noEmit`(프로젝트 전체 무결점), `npm run build`(성공, `/interviews/[id]` 동적 라우트 포함) 확인. `next dev`로 실행한 뒤 `/interviews/{실제 live 세션 id}`를 curl로 SSR 셸을 받아 초기 로딩 스켈레톤이 서버사이드 렌더링 단계에서 예외 없이 출력됨을 확인(브라우저 자동화 도구가 이 환경에 연결되어 있지 않아, 실제 클릭/타이핑 상호작용은 코드 리뷰 + 백엔드 API 동일 계약의 curl 검증으로 갈음했다 — 이 한계는 06단계가 실제 브라우저로 재검증할 것을 권장).
6. 검증 후 uvicorn(8000/8024)·next dev(3010) 프로세스 종료 확인(재요청 시 연결 거부). 테스트로 만든 candidate 계정·interview·consent·transcript는 DB에서 직접 DELETE로 정리. 생성한 임시 파일(`.harness-tmp/u4*.*`, `.harness-tmp/u4_ws_test.py`, `.harness-tmp/uvicorn_05_unit4*.log`, `.harness-tmp/nextdev_unit4.log`, `frontend/tsconfig.tsbuildinfo`)은 전부 삭제. `git status` 재확인 결과 unit-4가 만든 변경(§1)과 병렬 진행 중이던 다른 작업 단위의 변경만 남고 임시 산출물은 없음 — 규칙 K 준수.

## 7. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. `live` 상태 세션의 소유자가 `POST /interviews/{id}/turns`에 `{"text":"..."}`(1~4000자)를 보내면 `202`와 함께 문자열 `job_id`가 반환되고, `GET /interviews/{id}/transcripts`로 조회하면 방금 보낸 텍스트가 `speaker=user`, `input_mode=text`, `turn_index=0`(해당 세션의 첫 턴인 경우)으로 저장되어 있다.
2. 같은 세션에 두 번째 텍스트 턴을 제출하면 `turn_index=1`로 저장되고, `GET /transcripts`는 `turn_index` 오름차순으로 두 턴을 모두 반환한다.
3. `scheduled`(아직 시작 전) 상태의 세션에 `/turns`를 호출하면 `409 VALIDATION_ERROR`가 반환되고 TRANSCRIPTS에 아무것도 저장되지 않는다.
4. `completed` 상태의 세션에 `/turns`를 호출하면 `409 VALIDATION_ERROR`가 반환된다.
5. `text`가 빈 문자열이거나 필드 자체가 없으면 `422`가 반환되고, 4001자 이상이어도 `422`가 반환된다(4000자는 통과).
6. 세션 소유자가 아닌 다른 candidate 계정으로 `/turns` 또는 `/transcripts`를 호출하면 `403 AUTH_FORBIDDEN`이 반환된다. 인증 토큰 없이 호출하면 `401`, 존재하지 않는 interview id면 `404`가 반환된다.
7. `started_at`이 24시간을 초과한 `live` 세션에 `/turns`를 호출하면 `410 SESSION_EXPIRED`가 반환된다(unit-3의 lazy expiry 로직 재사용 확인).
8. 로그인 상태에서 브라우저로 `/interviews/{live 세션 id}`에 접속하면 로딩 스켈레톤 이후 채팅 화면이 표시되고, 텍스트를 입력해 전송하면 채팅 타임라인에 내 메시지가 즉시(낙관적 UI) 나타나며 입력창이 비워진다. 약 12초 내 AI 응답이 오지 않으면(현재 항상 이 경우) "AI 응답 엔진은 아직 준비 중입니다" 안내가 표시되고 입력창이 다시 활성화된다 — 이는 이번 유닛의 정상 동작이며 결함이 아니다.
9. `POST /interviews/{id}/turns`가 202로 응답한 job_id로 WebSocket `/ws/interviews/{id}`에 연결해도(유효한 토큰+본인 세션) `stage_update`/`turn_result`가 도착하지 않는 것이 **이번 유닛의 정상 동작**이다(AI Worker 미구현, §2-2/3). WS 연결 자체(인증 성공/실패, 화이트리스트 메시지 처리, 연결 유지)만 06단계 검증 대상이다.
