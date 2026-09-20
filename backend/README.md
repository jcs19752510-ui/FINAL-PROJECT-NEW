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
