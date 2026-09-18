# unit-1 구현 노트 — Feature A. 인증/사용자관리 (REQ-001)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요(traceability.md REQ-001 비고 참고).
- 입력: `docs/harness/03-system-design.md`(v2, PASS) §2/§3/§4.1~4.2/§6.1, `docs/harness/04-ux-design.md`(v2, PASS) [C-01]/[C-02], `docs/harness/02-planning.md` §9/§6

## 0. 이번 단위가 함께 만든 프로젝트 기본 골격 (선행 조건, 범위 외 아님)

이 프로젝트는 이번이 최초 코드 작업이라 실제 애플리케이션 골격이 전혀 없었다. 오케스트레이터 지시에 따라 아래를 unit-1의 정당한 선행 조건으로 함께 구성했다(비즈니스 로직은 인증/사용자관리로 한정, 다른 유닛의 로직은 만들지 않음):

- `backend/` — FastAPI 프로젝트 골격(디렉터리 구조, `requirements.txt`/`requirements-dev.txt`, `.env.example`, `docker-compose.yml`, Alembic 마이그레이션 도구)
- `frontend/` — Next.js(App Router, TypeScript) 프로젝트 골격(`package.json`, `tsconfig.json`, `eslint.config.mjs`, 최소 페이지)
- 루트 `.gitignore`에 `backend/.env`, `backend/venv/`, `frontend/node_modules/`, `frontend/.next/` 등 추가

## 1. 구현 범위 (REQ-001)

### 백엔드 (`backend/`)
- `app/models/user.py`: 03-design §3.1 ERD의 `USERS` 테이블 그대로(id/email/password_hash/role/name/created_at/deleted_at). `role`은 Postgres enum(`candidate|recruiter|admin`).
- `app/core/security.py`: 비밀번호 해시(Argon2id, `passlib[argon2]`), JWT 발급/검증(access 15분, refresh 7일 — 03-design §6.1과 일치). 시크릿은 `.env`(`JWT_SECRET_KEY`)에서만 읽음, 하드코딩 없음.
- `app/api/v1/auth.py`:
  - `POST /api/v1/auth/register` — 이메일 중복(409)/비밀번호 8자 미만·이메일 형식 오류(422, Pydantic `EmailStr`+`Field(min_length=8)`)/`role`은 `candidate`/`recruiter`만 허용(그 외 값은 422 — admin 자가등록 차단, 시스템 경계 입력 검증). 04-ux-design [C-01] 플로우대로 **자동 로그인 없이 201만 반환**.
  - `POST /api/v1/auth/login` — 이메일 불일치/비밀번호 불일치를 동일한 `401 AUTH_INVALID_TOKEN`으로 응답(계정 존재 여부 비노출, [C-02] 보안 원칙). 성공 시 `access_token`(JSON) + `refresh_token`(httpOnly 쿠키, path=`/api/v1/auth`).
  - `GET /api/v1/auth/me` — Bearer 토큰 검증 후 본인 정보 반환.
  - `POST /api/v1/auth/refresh` — §2 "설계서 대비 편차" 참고.
- `app/core/errors.py`: 03-design §4.1의 RFC 7807 Problem Details 포맷 공통 처리(`AppError`, 422 검증에러 핸들러).
- Alembic: `v1_initial_users` 리비전으로 `users` 테이블 생성 완료, 실제 PostgreSQL(Docker)에 적용 확인.

### 프론트엔드 (`frontend/`)
- `app/register/page.tsx` — [C-01] 명세대로 이메일/비밀번호/비밀번호확인/이름/역할 라디오/개인정보처리방침 동의 체크박스, 실시간 인라인 유효성(이메일 형식, 8자 이상, 비밀번호 확인 불일치), 제출 중 버튼 비활성+텍스트 변경, 서버 에러(이메일 중복 등) 필드 하단 표시, 네트워크 오류는 상단 배너. 성공 시 `/login?registered=1`로 이동(자동 로그인 아님, 명세 그대로).
- `app/login/page.tsx` — [C-02] 명세대로 이메일/비밀번호, 로딩 버튼, 계정 존재 여부를 노출하지 않는 통합 에러 메시지.
- `app/page.tsx` — 로그인 후 진입할 실제 지원자 홈([C-03])은 unit-2 이후 범위라 존재하지 않으므로, 최소 임시 화면(로그인 상태면 `/auth/me` 조회 결과로 환영 문구+역할+로그아웃, 비로그인 상태면 로그인/회원가입 링크)으로 대체. **이 화면 자체는 04-ux-design에 정의된 화면이 아니며, unit-2([C-03] 지원자 홈)가 이 자리를 대체해야 한다.**
- `lib/api.ts` — 백엔드 호출 래퍼(RFC 7807 에러 파싱), access token은 `sessionStorage`에 저장(§2 편차 참고).
- 디자인 토큰: 04-ux-design §3.1(색상)/§3.2(타이포)의 핵심 값만 `globals.css`에 CSS 변수로 반영. 컴포넌트 라이브러리 전체(§4의 재사용 컴포넌트 명세)는 구현하지 않고 이번 화면에 필요한 만큼만 인라인 스타일로 구현(L1 원칙 — 정상 동작 우선).

## 2. 설계서/디자인서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `POST /api/v1/auth/refresh` 엔드포인트를 신설 | 03-design §6.1이 "refresh 7일, httpOnly 쿠키"라고 명시했으나 §4.2 API 표에는 refresh 엔드포인트가 없음 — JWT를 쓰면서 refresh 쿠키를 발급만 하고 실제로 갱신할 경로가 없는 것은 설계 의도와 맞지 않는 결손으로 판단. 두 가지 이상의 실질적으로 다른 해석이 갈리는 사안이 아니라(표준 JWT refresh 관례가 사실상 하나) 규칙A 질문 대상은 아니라고 보고 관례대로 구현. 회전(rotation) 없이 access token만 재발급하는 최소 구현 | 낮음(엔드포인트 추가일 뿐 기존 계약 변경 없음) |
| 2 | 쿠키 `secure` 플래그를 `COOKIE_SECURE` 환경변수로 제어(기본 true, 로컬 dev `.env`는 false) | 03-design §6.4가 운영환경은 TLS(Nginx 종단)를 전제하므로 `secure=True`가 맞지만, 로컬 개발 서버는 http라 브라우저가 Secure 쿠키를 저장하지 않아 로그인 자체가 로컬에서 깨짐. 실제로 로그인 스모크테스트 중 발견 | 낮음(환경변수 하나) |
| 3 | 초기 Alembic 마이그레이션에 `users` 테이블만 포함(03-design §3.3은 "ERD 전체를 하나의 v1_initial_schema로" 명시) | ERD 전체(9개 테이블)를 만들면 unit-1 범위를 넘어 다른 unit(2~18)의 데이터 모델을 미리 구현하는 셈이 되어 "범위 외 변경 금지" 원칙과 충돌. Alembic은 리비전을 계속 쌓을 수 있으므로 각 유닛이 자신의 테이블을 자기 리비전에서 추가하는 방식으로 진행(03-design §3.3 "이후 변경은 유닛 단위로 순차 revision" 문장과도 부합). 최초 리비전명은 설계서 문구와 구분하기 위해 `v1_initial_users`로 명명 | 낮음(향후 리비전 계속 추가 가능, 데이터 유실 없음) |
| 4 | access token을 프론트엔드 `sessionStorage`에 저장 | [C-03] 지원자 홈이 아직 없어 로그인 상태를 유지할 곳이 없음 — 최소한의 "로그인됨" 표시를 위해 임시로 채택. **알려진 트레이드오프**: httpOnly가 아니므로 XSS 시 토큰 탈취 위험이 refresh 쿠키보다 높음. unit-2([C-03])에서 정식 세션/상태관리(예: BFF 프록시, React Context+메모리 저장 등)로 교체 필요 — 09단계 보안검증에서 재확인 요망 | 낮음(프론트만 교체) |
| 5 | 회원가입 화면의 "개인정보 처리방침 동의" 체크박스는 프론트 전용 UI일 뿐 서버에 저장하지 않음 | 04-ux-design [C-01]이 이를 "계정가입 표준 약관(REQ-029 생체정보 동의와 별개)"으로 명시했고, 이 동의를 서버에 기록하는 API/테이블은 03-design 어디에도 없음(CONSENTS 테이블은 `biometric_voice`/`ai_interview_notice` 전용). 범위 밖 API를 임의로 추가하지 않음 | 낮음 |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **브라우저 실제 클릭 테스트 불가**: 이 세션은 MCP(Playwright 등)를 연동하지 않았다(DEC-001). 따라서 폼 클릭/포커스이동/스크린리더 등 실제 브라우저 상호작용은 검증하지 못했다 — `next build`(타입체크+정적생성 성공), `next lint`(0 에러), 개발서버 기동 후 `curl`로 `/`, `/login`, `/register` 200 응답만 확인했다. 06단계에서 가능하면 브라우저 기반 확인을 권장(L1이라 필수는 아님).
- **PostgreSQL 실제 사용 가능 여부**: 로컬에 PostgreSQL 서버가 직접 설치되어 있지 않았으나(`psql`/`pg_ctl` 없음), **Docker는 설치되어 있고(Docker Desktop) 최초 미기동 상태였던 것을 이번 세션에서 직접 기동**했다. `backend/docker-compose.yml`로 PostgreSQL 16 컨테이너(포트 5544, 볼륨 영속화)를 띄우고, 그 위에서 Alembic 마이그레이션과 회원가입/로그인/me/refresh 전체 API를 **실제 PostgreSQL against 실제 SQL**로 동작 확인했다(SQLite 대체는 필요 없었음 — 아래 §5 참고). 06단계도 동일하게 `cd backend && docker compose up -d` 후 진행하면 된다.
- **JWT_SECRET_KEY**: 로컬 `.env`는 이번 세션이 `secrets.token_urlsafe(48)`로 생성한 랜덤 값을 사용 중(커밋 안 됨). 06/07단계도 각자 `.env`를 만들어야 하며 `.env.example`을 참고할 것.
- **refresh 엔드포인트는 신규(§2-1)** — 03-design에 없던 편차이므로 06단계 테스트 케이스 설계 시 "명세에 없는 엔드포인트"로 혼동하지 말 것.

## 4. 6단계 인수조건 (Acceptance Criteria) — L1 경량 테스트용, 정상 경로 위주

1. `POST /api/v1/auth/register`에 `{email, password(8자 이상), name, role: "candidate"}` 유효 요청 시 `201`과 함께 `password_hash`가 응답에 포함되지 않은 `UserOut`(id/email/name/role/created_at)이 반환된다.
2. 동일 email로 재요청 시 `409 VALIDATION_ERROR`가 반환된다(회원 재사용 방지 정상 경로).
3. `role: "recruiter"`로 가입한 사용자도 1과 동일하게 성공한다.
4. 가입한 계정으로 `POST /api/v1/auth/login`에 올바른 email/password를 보내면 `200`과 함께 `access_token`(JWT, 3-segment) + `Set-Cookie: refresh_token=...; HttpOnly`가 반환된다.
5. 발급받은 `access_token`으로 `GET /api/v1/auth/me`를 호출하면 `200`과 함께 로그인한 사용자 본인의 정보(email/role 일치)가 반환된다.
6. 프론트엔드: `/register`에서 위 1번 입력을 폼으로 제출하면 `/login?registered=1`로 이동한다. `/login`에서 유효한 자격증명 제출 시 `/`로 이동하고, 홈 화면에 로그인한 사용자의 이름/역할이 표시된다.

(에러 경로 중 이번 05단계 자체 검증에서 이미 실행 확인한 것: 이메일 중복 409, 잘못된 role 422, 8자 미만 비밀번호 422, 로그인 비밀번호 불일치 401, 토큰 없음/위조 토큰 401 — 06단계가 그대로 재사용해도 됨.)

## 5. 게이트 1 — 정적 분석/린트

이 프로젝트에는 기존 lint/type-check 설정이 없었으므로(그린필드), 이번 단위에서 기본 설정을 함께 만들었다.

- 백엔드: `ruff`(lint) 신규 도입, `backend/pyproject.toml`에 설정(`select = ["E","F","I","UP","B"]`, `B008`은 FastAPI `Depends(...)` 관용 패턴이라 예외 처리). `ruff check app alembic/env.py` **통과(에러 0건)**.
- 프론트엔드: `eslint`(Next.js 16 flat config, `eslint-config-next`) 신규 도입. `npm run lint` **통과(에러/경고 0건)**. `npm run build`(TypeScript 타입체크 포함) **통과**.
- 별도 타입체커(mypy 등)는 백엔드에 아직 없음 — 05단계 범위에서는 ruff만 도입, 필요시 이후 유닛에서 추가 검토.

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — REQ-001/§4.2 auth 엔드포인트, §6.1 JWT/Argon2id, [C-01]/[C-02] 화면 명세와 대조 완료. 편차는 §2에 전부 기록.
- [x] 에러 처리 누락 경로 없음 — 이메일 중복/검증실패/로그인실패/토큰없음/토큰위조/refresh없음/refresh만료 각각 명시적 `AppError` 처리, 예외를 조용히 삼키는 코드 없음(모든 `except`는 명시적으로 401/422/409로 변환).
- [x] 시스템 경계(사용자 입력) 검증 — `RegisterRequest`/`LoginRequest`(Pydantic, `EmailStr`+길이제약+`role` Literal), 프론트도 동일 규칙 이중 검증(서버가 최종 권위, 클라이언트는 UX 보조).
- [x] 하드코딩된 시크릿/자격증명 없음 — `JWT_SECRET_KEY`/DB 자격증명 전부 `.env`(gitignore 처리, `.env.example`만 커밋). `docker-compose.yml`의 DB 비밀번호는 로컬 전용 개발 컨테이너 기본값이며 운영 배포 시 반드시 교체 필요(README에 명시하지 않은 부분은 10단계 배포테스트에서 재확인 권고).
- [x] 신규 외부 의존성 실존 확인 — 아래 §7.
- [x] 범위 외 변경 없음 — unit-2 이후 기능(면접 세션/대화엔진/리포트 등) 코드/테이블 미작성. 유일한 "선행 조건성" 확장은 오케스트레이터가 이번 프롬프트에서 명시적으로 허용한 프로젝트 골격(디렉터리/의존성/DB연결/마이그레이션 도구)뿐.

## 7. 신규 외부 의존성 실존 확인 (실제 설치 시도)

모두 `.harness-tmp/venv_05_unit1`(격리 venv, 검증 전용) / `frontend/node_modules`(npm)에 실제로 설치해 확인함 — 존재하지 않는 패키지명을 지어내지 않았음.

- Python(`backend/requirements.txt`): `fastapi 0.115.14`, `uvicorn`, `sqlalchemy 2.0.54`, `alembic 1.13.3`, `psycopg[binary] 3.2.13`, `pydantic 2.13.5`, `pydantic-settings 2.15.0`, `email-validator`, `python-jose 3.3.0`, `passlib[argon2] 1.7.4`, `argon2-cffi 23.1.0`, `python-multipart 0.0.32` — 전부 PyPI에서 정상 설치됨. 개발용 `ruff 0.16.8`도 확인.
- Node(`frontend/package.json`): `next 16.3.5`, `react`/`react-dom 19.3.0`, `eslint 9.x`, `eslint-config-next 16.3.5`, TypeScript 관련 `@types/*` — `npm install` 성공, 0 vulnerabilities, `npm run build`/`npm run lint` 정상 동작까지 확인.

## 8. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. Docker Desktop 기동 → `docker compose up -d`(backend/)로 PostgreSQL 16 컨테이너(포트 5544) 기동.
2. `alembic revision --autogenerate -m "v1_initial_users"` → `alembic upgrade head` 로 `users` 테이블 생성 확인.
3. `uvicorn app.main:app`로 FastAPI 기동 후 `curl`로 다음을 실제 확인: 헬스체크 200 / 회원가입 201(한글 이름 포함, UTF-8) / 중복이메일 409 / 잘못된 role 422 / 8자 미만 비밀번호 422 / 로그인 실패 401(오답 비밀번호) / 로그인 성공 200(access_token+refresh 쿠키) / `/me` 200(정상 토큰) 및 401(토큰 없음/위조 토큰) / `/refresh` 200(쿠키로 access token 재발급) / recruiter 역할 가입·조회 정상.
4. `npm run build`(Turbopack, 타입체크 포함) 성공, `npm run lint` 0건, `npm run dev` 기동 후 `/`, `/login`, `/register` 전부 HTTP 200 확인.
5. 검증 후 생성한 서버 프로세스(uvicorn, next dev)는 종료했고, PostgreSQL 컨테이너는 다음 유닛/06단계가 이어서 쓸 수 있도록 유지(실행 방법은 `backend/README.md`).
6. `.harness-tmp/venv_05_unit1`은 이번 검증 전용 가상환경이며, 06단계 이후에는 각 단계가 규칙K에 따라 자체 격리 환경을 새로 만들거나 이 venv를 재사용해도 무방함(재생성 가능한 산출물).

## 9. traceability.md 갱신

REQ-001 행: 구현 상태를 "구현 완료(05단계) — 06단위테스트 대기"로 갱신, 비고에 L1 트랙/부채 상태 및 본 노트 경로 링크 추가.
