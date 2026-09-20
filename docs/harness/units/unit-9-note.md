# unit-9 구현 노트 — Feature D. 라이브 코딩 환경: 에디터 + 제출/저장 API (REQ-008)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, 오케스트레이터 지정)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §3.1(CODE_SUBMISSIONS ERD), §4.2(`/interviews/{id}/code-submissions` POST/**GET(신규, DEC-024 갭3)**), §6.3(제출값 새니타이즈, REQ-036과 동일기준), `docs/harness/04-ux-design.md`(v2, PASS) [C-07] 코드 에디터 패널(DEC-008: 코드 실행 Out-of-Scope), `docs/harness/traceability.md` REQ-008 행

## 0. 이전 시도 재사용 여부 (세션 재개 메모)

이 세션은 API rate limit으로 중단된 이전 시도를 이어받았다. 시작 시점에 `git status`/`alembic history`/`alembic current`로 확인한 결과 **백엔드·프런트엔드 산출물이 이미 전부 구현·적용되어 있었다**:

- 백엔드: `backend/app/models/code_submission.py`, `backend/app/schemas/code_submission.py`, `backend/app/api/v1/code_submissions.py`, Alembic `b84a71b986c5_v6_code_submissions`(down_revision=`c1a2f5e9b7d3`, head) — `alembic current` 확인 결과 로컬 DB(`final-project-db`, 포트 5544)에 **이미 적용되어 있었음**(재적용 불필요).
- `backend/app/main.py`에 `code_submissions_router`가 이미 등록되어 있었음.
- 프런트: `frontend/app/interviews/[id]/components/CodeEditorPanel.tsx`(Monaco 에디터, 독립 컴포넌트), `frontend/package.json`/`package-lock.json`에 `@monaco-editor/react@^4.7.0`이 이미 추가·설치되어 있었음(`node_modules/@monaco-editor` 존재 확인).

이번 세션에서 새로 한 작업은 처음부터 다시 구현하는 것이 아니라: (1) 위 산출물이 설계서와 실제로 일치하는지 코드 리뷰, (2) 게이트1(ruff/eslint/tsc) 재실행, (3) 게이트2 체크리스트 재점검, (4) **실제 curl 기반 종단 검증**(회원가입→로그인→면접 생성→코드 제출/조회/권한 경계), (5) 이번 unit-9-note.md와 traceability.md 갱신이다. 코드 변경은 발생하지 않았다(diff 없음).

## 1. 구현 범위

### 백엔드

- `backend/app/models/code_submission.py`: 03-design §3.1 ERD `CODE_SUBMISSIONS` 그대로(`interview_id` FK, `language` string, `content` text, `submitted_at`). 코드 "실행"과 관련된 필드/로직은 전혀 없음(DEC-008).
- `backend/app/schemas/code_submission.py`: `CodeSubmissionCreate`(언어 화이트리스트 11종 + `content` 0~20000자), `CodeSubmissionOut`. `language`는 ERD상 자유 문자열이나 [C-07]의 "언어 선택 드롭다운"이 유한 목록을 전제하므로 API 경계에서 화이트리스트 검증(게이트2 입력값 검증)을 추가했다.
- `backend/app/api/v1/code_submissions.py`: `POST /interviews/{id}/code-submissions`(제출/저장, TRANSCRIPTS와 동일한 append-only 이력 패턴), `GET /interviews/{id}/code-submissions`(신규, DEC-024 갭3 — 세션 재개 시 재조회, `language` 쿼리로 필터링). 소유권 검사(`_get_own_interview`)는 `interviews.py`(unit-2~4 소유, 수정 범위 밖)를 건드리지 않고 이 파일 안에 독립적으로 재구현(consents.py 선례).
- Alembic `b84a71b986c5_v6_code_submissions`(down_revision=`c1a2f5e9b7d3`, 현재 head, 병렬 유닛과 선형 체인 유지 확인). 마이그레이션 파일 상단 주석에 autogenerate가 whiteboard_snapshots를 오탐지 삭제하려 한 것을 수동 제거했다는 기록이 이미 남아 있음(이전 시도의 판단, 이번 세션에서 재확인만 함).

### 프론트엔드

- `frontend/app/interviews/[id]/components/CodeEditorPanel.tsx`(신규, 독립 컴포넌트): [C-07] 언어 선택 드롭다운(11개), Monaco 에디터(`@monaco-editor/react`, `vs-dark` 테마), 저장 상태 표시(저장됨/저장 중/미저장/저장 실패), 제출 버튼, 언어 전환 시 `GET`으로 해당 언어 최신 제출본 복원. `unit-4`가 소유한 `page.tsx`/`lib/api.ts`를 import하지 않고 fetch 호출과 타입을 자체 완결(오케스트레이터 지시 "독립 컴포넌트" 경계 준수). 실제 면접장 화면에 탭으로 배선(마운트)하는 작업은 이번 유닛 범위 밖 — 추후 통합 유닛이 `page.tsx`에서 이 컴포넌트를 import해 사용해야 한다.

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `GET /interviews/{id}/code-submissions`를 03-design §4.2 원 표(POST만 명시)에 추가로 신설 | [C-07] "저장 상태 표시"와 세션 재개([C-12]) 시 최신 코드 복원이 구조적으로 GET을 요구하며, `traceability.md`에도 "DEC-024 갭3"으로 이미 GET 신설이 승인되어 있다(unit-3/4의 additive GET 선례와 동일 근거) | 낮음(순수 추가 GET) |
| 2 | `content`(제출 코드)를 렌더링 시점 새니타이즈(§6.3/REQ-036) 없이 원문 그대로 저장 | §6.3 새니타이즈는 "렌더링 시점" 방어(추후 recruiter 대시보드가 이 값을 HTML로 보여줄 때 적용)이며, 이번 유닛은 그 렌더링 화면을 만들지 않는다(오케스트레이터 지시 범위: 에디터+저장 API만). 저장 시점에는 원문 보존이 맞다 — 이 값을 나중에 HTML로 렌더링하는 화면(recruiter 대시보드 등)을 만드는 유닛이 §6.3 화이트리스트 새니타이즈를 반드시 적용해야 한다 | 낮음(렌더링 유닛이 출력 시점에 이스케이프만 추가하면 됨) |
| 3 | `CodeEditorPanel`이 실제 면접장 화면(`/interviews/[id]/page.tsx`)에 배선되어 있지 않음(코드는 존재하나 어디서도 import되지 않음) | 오케스트레이터 지시가 "독립 컴포넌트"로 한정했고, `page.tsx`는 unit-4 소유 파일이라 이번 유닛의 수정 범위 밖이다 | 낮음(추후 통합 유닛이 import 한 줄 + 탭 전환 상태만 추가하면 됨) |
| 4 | `content` 최대 길이 20000자, 언어 화이트리스트 11종은 설계서에 명시되지 않은 구현 세부값 | 시스템 경계 입력 검증(게이트2)을 위해 이 유닛에서 보수적으로 확정(unit-4 `TurnCreate` 선례와 동일 근거) | 낮음(값 조정만 필요, 계약 구조 변경 없음) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **선행 조건**: `POST /interviews/{id}/code-submissions`는 세션 상태(scheduled/live/completed 등)를 검사하지 않는다 — 설계서/UX 명세 어디에도 코드 제출을 특정 세션 상태로 제한하라는 규정이 없어(면접 종료 후에도 코드 내용을 열람/보완 저장할 수 있어야 한다는 [C-07] 취지와도 부합), 소유권만 확인하면 어떤 상태의 세션에도 저장 가능하다. 06단계가 "왜 409가 안 나오냐"고 오판하지 않도록 명시한다.
- **언어 화이트리스트 불일치 위험**: 프런트 `LANGUAGE_OPTIONS`(CodeEditorPanel.tsx)와 백엔드 `ALLOWED_LANGUAGES`(code_submission.py)는 값이 반드시 동일해야 한다(둘 다 11종: python/javascript/typescript/java/c/cpp/csharp/go/rust/sql/plaintext). 어긋나면 프런트 드롭다운에서 고른 값이 서버에서 422로 거부된다.
- **`CodeEditorPanel`은 화면에 아직 연결되어 있지 않다**: 06단계가 브라우저로 이 컴포넌트를 직접 열어볼 진입 경로가 없다(§2-3). 컴포넌트 자체의 브라우저 렌더링/상호작용 검증은 Storybook류 없이 코드 리뷰 + API 계약 curl 검증으로 갈음했다. 06단계가 브라우저 자동화로 실제 클릭/입력을 검증하려면 임시로 어떤 페이지에서든 이 컴포넌트를 마운트해야 한다.
- **PostgreSQL/venv**: `docker compose`의 `final-project-db`(포트 5544) 컨테이너를 그대로 재사용. 이번 유닛 전용 격리 venv `.harness-tmp/venv_05_unit9`(DEC-027)를 사용했다 — 다른 유닛과 공유하지 않음.
- **append-only 이력**: 같은 언어로 여러 번 제출하면 매번 새 행이 쌓인다(TRANSCRIPTS와 동일 패턴). `GET`은 `submitted_at desc`로 정렬되므로 첫 번째 항목이 항상 최신본이다.

## 4. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check .`(backend 디렉터리 기준, `pyproject.toml`의 `exclude = ["alembic/versions"]` 적용) → **통과(에러 0건)**. 마이그레이션 파일 단독으로 `ruff check <파일>`을 돌리면 `UP035`/`I001`/`UP007` 5건이 뜨지만, 이는 프로젝트 전체 알렘빅 마이그레이션 파일들이 공통으로 갖는 autogenerate 템플릿 스타일이며 `pyproject.toml`이 `alembic/versions`를 명시적으로 lint 제외 대상으로 설정해 두었으므로 실제 프로젝트 lint 명령(`ruff check .`) 기준으로는 문제 없음.
- 프론트엔드: `npx eslint "app/interviews/[id]/components/CodeEditorPanel.tsx"` → **에러 0건**. `npx tsc --noEmit`(프로젝트 전체) → **에러 0건**.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 편차와 사유 전부 기록. 나머지(ERD 컬럼, POST 계약, [C-07] 저장 상태 UI, DEC-008 실행 없음)는 03-design §3.1/§4.2, 04-ux-design [C-07] 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — 세션 없음(404), 소유권 없음(403), 인증 없음(401), 입력값 부적합(422, 언어 화이트리스트/길이)까지 명시적 `AppError`/Pydantic 검증. 프런트도 GET 실패 시 안내 배너 + 빈 템플릿으로 대체(예외를 조용히 삼키지 않음), POST 실패 시 에러 메시지 노출 + 로컬 콘텐츠 보존.
- [x] 시스템 경계(사용자 입력) 검증 — `language`는 화이트리스트, `content`는 0~20000자 강제, path param `interview_id`는 FastAPI UUID 강제 검증. 실제 curl로 잘못된 언어(cobol) → 422 확인.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — `@monaco-editor/react@^4.7.0`은 `package-lock.json`에 `resolved: https://registry.npmjs.org/@monaco-editor/react/-/react-4.7.0.tgz`로 실제 npm 레지스트리 URL이 기록되어 있고 `node_modules/@monaco-editor`에 실제로 설치되어 있음을 확인(가짜 패키지명 아님).
- [x] 범위 외 변경 없음 — 채팅/웹캠/화이트보드/동의/운영자/대시보드/음성 관련 파일은 열람만 하고 수정하지 않았다. `interviews.py`/`page.tsx`/`lib/api.ts`도 건드리지 않았다(소유권 검사를 자체 파일 내에 독립 구현).

## 6. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용. 이전 시도가 만들어 둔 격리 venv `.harness-tmp/venv_05_unit9` 재사용(패키지 이미 설치됨, DEC-027 준수 — 다른 유닛 venv와 공유하지 않음).
2. `alembic current` → `b84a71b986c5 (head)` 확인, 로컬 DB에 `code_submissions` 테이블이 이미 적용되어 있어 재마이그레이션 불필요.
3. `ruff check .`(backend) 통과, `npx eslint`/`npx tsc --noEmit`(frontend) 통과.
4. `uvicorn app.main:app --port 8019`로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인 → `POST /interviews`(scheduled 상태 그대로)
   - `POST /code-submissions {language: python, content: "print(1)"}` → `201`, 저장된 필드 확인
   - 같은 언어로 두 번째 제출(`print(2)`) → `201`(새 행으로 append)
   - `GET /code-submissions`(필터 없음) → 최신순으로 2건 모두 반환(`print(2)`가 첫 번째)
   - `GET /code-submissions?language=javascript`(제출 이력 없는 언어) → `200 []`
   - `POST /code-submissions {language: cobol}`(화이트리스트 외) → `422 VALIDATION_ERROR`
   - 인증 토큰 없이 `GET /code-submissions` → `401`
   - 존재하지 않는 interview id로 `GET` → `404`
   - 다른 candidate 계정 토큰으로 남의 세션 `GET /code-submissions` 시도 → `403 AUTH_FORBIDDEN`(수평 권한 상승 방지 확인)
5. 검증 후 uvicorn(포트 8019) 프로세스 종료 확인. 테스트로 만든 candidate 계정 2건·interview 1건·code_submissions 2건은 DB에서 직접 DELETE로 정리(`unit9test%` 이메일 패턴). `git status` 재확인 결과 이번 세션에서 새로 만든 코드 변경 없음(이전 시도 산출물 그대로, 문서만 갱신).

## 7. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 로그인한 candidate가 자신이 생성한 면접 세션에 `POST /interviews/{id}/code-submissions`로 `{"language":"python","content":"print(1)"}`를 보내면 `201`과 함께 `id`/`interview_id`/`language`/`content`/`submitted_at`이 포함된 응답이 반환된다.
2. 같은 세션·같은 언어로 다시 제출하면 새 행이 추가로 쌓이고(덮어쓰지 않음), `GET /interviews/{id}/code-submissions`는 `submitted_at` 내림차순으로 정렬되어 첫 번째 항목이 가장 최근 제출본이다.
3. `GET /interviews/{id}/code-submissions?language=<제출 이력 없는 언어>`는 `200`과 함께 빈 배열 `[]`을 반환한다(에러 아님).
4. 화이트리스트에 없는 `language`(예: `"cobol"`)로 제출하면 `422`가 반환되고 DB에 아무것도 저장되지 않는다.
5. 인증 토큰 없이 호출하면 `401`, 존재하지 않는 `interview_id`면 `404`가 반환된다.
6. 세션 소유자가 아닌 다른 candidate 계정으로 같은 세션의 `code-submissions`를 조회/제출하면 `403 AUTH_FORBIDDEN`이 반환된다.
7. (범위 외, 정보성) `CodeEditorPanel.tsx`는 독립 컴포넌트로 존재하나 아직 어떤 페이지에도 배선되어 있지 않다 — 06단계가 브라우저로 직접 접근할 진입 경로가 없다는 점을 실패로 판정하지 않는다(§2-3, §3 참고). 컴포넌트 코드 리뷰(언어 드롭다운 11종, 저장 상태 라벨, Monaco 에디터 마운트, GET/POST 호출부)로 [C-07] 명세 충족 여부만 확인한다.
