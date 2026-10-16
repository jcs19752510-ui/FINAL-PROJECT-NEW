# Backend — AI 모의면접 플랫폼 (FastAPI)

unit-1(REQ-001: 회원가입/로그인/역할관리), unit-2(REQ-002: 면접 세션 생성/시작/종료) 범위. 03-system-design.md §2/§3/§4/§6 기준.

## 로컬 실행 방법

1. PostgreSQL 기동 (Docker Compose)
   ```bash
   cd backend
   docker compose up -d
   ```
   기본값: `localhost:5544`, DB `final_project`, 계정 `final_app`/`final_app_pw` (docker-compose.yml 참고).

   Docker가 없다면: 로컬에 PostgreSQL 16을 직접 설치하고 `.env`의 `DATABASE_URL`을 맞게 수정한다.

2. 파이썬 가상환경 및 의존성 설치
   ```bash
   python -m venv .venv
   source .venv/Scripts/activate   # Windows Git Bash
   pip install -r requirements-dev.txt
   ```

3. 환경변수 설정
   ```bash
   cp .env.example .env
   # JWT_SECRET_KEY를 실제 랜덤 값으로 교체할 것 (하드코딩 금지)
   ```

4. 데이터베이스 마이그레이션
   ```bash
   PYTHONPATH=. alembic upgrade head
   ```

5. 개발 서버 실행
   ```bash
   PYTHONPATH=. uvicorn app.main:app --reload --port 8000
   ```

6. 동작 확인
   ```bash
   curl http://127.0.0.1:8000/api/v1/health
   ```

## 린트

```bash
ruff check app
```

## API (unit-1 범위)

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/api/v1/auth/register` | POST | 회원가입 (role: candidate/recruiter) |
| `/api/v1/auth/login` | POST | 로그인, access token(JSON) + refresh token(httpOnly 쿠키) 발급 |
| `/api/v1/auth/refresh` | POST | refresh 쿠키로 access token 재발급 (설계서에 없어 관례로 추가 — unit-1-note.md 참고) |
| `/api/v1/auth/me` | GET | 내 정보 조회 (Bearer 토큰 필요) |
| `/api/v1/interviews` | POST | 면접 세션 생성(candidate 전용, status=scheduled) |
| `/api/v1/interviews/{id}/start` | POST | 세션 시작(`ai_interview_notice` 동의 필요, 본인 세션만) — opening_question job enqueue(스텁) |
| `/api/v1/interviews/{id}/end` | POST | 세션 종료(본인 세션만) — report_generation job enqueue(스텁), report_status=queued |

에러 응답은 RFC 7807 Problem Details 형식(03-system-design.md §4.1).

`POST /consents` API는 아직 없다(unit-14/15 범위). `/start` 테스트를 위한 동의 등록은
로컬 개발 중에만 DB에 직접 INSERT한다(`docs/harness/units/unit-2-note.md` §3 참고).

## Google 로그인 설정 (2026-10-16, 추가 로그인 방식)

기존 이메일/비밀번호 로그인은 그대로 두고, 채용 지원 포털(`frontend-apply`) 로그인 화면 하단에
"Google로 계속하기" 버튼을 추가했다. Google은 **신원 확인만** 담당하고, 회원·권한·세션은 이 서비스의
기존 JWT(액세스 토큰 + httpOnly 리프레시 쿠키)가 그대로 관리한다.

### 동작 흐름
1. 버튼 → `GET /api/v1/auth/google/start` : state·nonce·PKCE 생성, 일회용 state를 Redis에 10분간 보관, 서명된 단기
   httpOnly 쿠키(`g_oauth`, path `/api/v1/auth/google`) 설정 후 Google 인증 화면으로 리다이렉트.
2. Google → `GET /api/v1/auth/google/callback` : state 검증(재사용 거부) → 서버에서 code 교환 →
   ID Token 서명·`iss`·`aud`·`exp`·`nonce` 검증 → `email_verified=true` 확인 →
   `user_identities`(provider+sub)로 회원 조회, 없으면 **candidate** 로 신규 가입 → 기존과 같은 리프레시 쿠키 발급 →
   `{프런트}/login/google?status=ok` 로 리다이렉트. (실패는 `?error=<코드>`)
3. 프런트 `/login/google` 이 기존 `POST /auth/refresh` 로 액세스 토큰을 받아 `/resume` 으로 이동. 토큰은 URL에 실리지 않는다.

### 정책
- 신규 가입 역할은 항상 `candidate`. 구글 경로로 recruiter/admin 이 만들어지거나 승격되지 않는다.
- users 에 이미 있는 이메일(대소문자 무시)은 **자동 병합하지 않는다** → "이미 가입된 이메일입니다" 안내.
- `users` 테이블은 변경하지 않았다. 구글 가입자의 `password_hash` 에는 아무도 모르는 임의 값의 해시가 들어가므로
  비밀번호 로그인은 기존과 동일한 401 이 된다. 구글 연결 정보는 새 테이블 `user_identities` 에만 저장한다.
- Google 토큰(access/id/refresh)은 저장하지 않는다. 수집 범위는 `openid email profile`.
- 탈퇴(`deleted_at`) 계정은 구글로도 로그인할 수 없다.

### 1) Google Cloud Console 에서 직접 할 일 — https://console.cloud.google.com/
1. 프로젝트 생성(또는 기존 프로젝트 선택).
2. **API 및 서비스 → OAuth 동의 화면**: 앱 이름·지원 이메일 입력, 범위는 `openid`, `email`, `profile` 만(민감/제한 범위 불필요).
   게시 상태가 "테스트"이면 테스트 사용자로 등록한 계정만 로그인된다. 일반 공개 전 앱 검증 요구사항을 공식 문서로 확인한다.
3. **사용자 인증 정보 → OAuth 클라이언트 ID 만들기**, 애플리케이션 유형 **웹 애플리케이션**.
4. **승인된 JavaScript 원본**: 프런트 오리진(로컬 `http://localhost:3002`, 운영 `https://<도메인>`).
5. **승인된 리디렉션 URI**: 백엔드 콜백(로컬 `http://localhost:8001/api/v1/auth/google/callback`,
   운영 `https://<도메인>/api/v1/auth/google/callback`). 서버의 `GOOGLE_REDIRECT_URI` 와 **한 글자도 다르면 안 된다**.
6. 발급된 클라이언트 ID / 비밀번호를 아래 환경변수로 넣는다(비밀번호를 채팅·코드·로그에 붙여 넣지 않는다).
운영은 HTTPS 도메인이 필수이고 `COOKIE_SECURE=true` 여야 한다.

### 2) 환경변수
백엔드 `backend/.env` (`.env.example` 참고):
```
GOOGLE_LOGIN_ENABLED=true
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8001/api/v1/auth/google/callback
GOOGLE_ALLOWED_RETURN_ORIGINS=http://localhost:3002
```
프런트 `frontend-apply` (빌드 시점 변수, 기본 꺼짐 — 꺼져 있으면 로그인 화면이 이전과 완전히 같다):
```
NEXT_PUBLIC_GOOGLE_LOGIN_ENABLED=true
```
CORS(`CORS_ORIGINS`)에 프런트 오리진이 이미 들어 있어야 한다(`/auth/refresh` 호출용).

### 3) DB 마이그레이션 (새 테이블 `user_identities` 만 추가)
```
cd backend
pg_dump ... > backup.sql        # 운영/개발 DB 는 적용 전에 백업
alembic upgrade head            # a1f4c9d2e7b3 (v22_user_identities)
```

### 4) 로컬 실행
```
cd backend && alembic upgrade head && uvicorn app.main:app --port 8001
cd frontend-apply && NEXT_PUBLIC_GOOGLE_LOGIN_ENABLED=true npm run dev -- -p 3002
```

### 5) 테스트
```
# 기존 이메일/비밀번호 인증이 바뀌지 않았음을 증명하는 기준선 테스트 (서버 기동 필요)
API_BASE_URL=http://127.0.0.1:<포트> python -m pytest tests/auth_baseline -v
# Google 로그인 (외부 Google 은 모킹, DB·Redis 는 실제 사용, 서버 기동 불필요)
python -m pytest tests/google_login -v
```
실제 Google 왕복(수동 통합 테스트): 위 환경변수를 채우고 로그인 화면에서 버튼 → Google 계정 선택 →
`/resume` 도달, `users`/`user_identities` 에 1행씩 생성됐는지, 같은 계정으로 재로그인 시 행이 늘지 않는지 확인.

### 6) 롤백
1. `GOOGLE_LOGIN_ENABLED=false` (경로 404, 버튼 숨김 — 가장 빠른 방법) 후 재기동.
2. 필요하면 `alembic downgrade -1` (새 테이블만 삭제, users 는 영향 없음).
3. 코드 되돌리기(`git revert`).

### 알려진 한계 / 후속 검토
- 개인정보 삭제 배치(`app/worker/deletion_tasks.py::_purge_full_account`)는 users 행을 하드 삭제하지 않으므로
  `user_identities`(구글 이메일·sub)도 남는다. 삭제 정책에 맞추려면 이 함수에 `user_identities` 삭제를 한 줄 추가해야 한다.
  (이번 작업은 기존 파일 수정 금지 범위라 반영하지 않았다.)
- 속도 제한은 클라이언트 IP(`request.client.host`) 기준이다. 리버스 프록시 뒤에서는 프록시가 실제 IP를 전달하도록
  uvicorn `--proxy-headers`/`FORWARDED_ALLOW_IPS` 설정이 필요하다.
- Google 공개 인증서는 로그인마다 조회한다(타임아웃 10초). 트래픽이 많아지면 캐시를 도입한다.
