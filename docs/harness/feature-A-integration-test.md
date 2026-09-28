# 테스트 결과서 (Test Result Report) — Feature A 통합테스트 (인증/회원, REQ-001)

> `templates/test-report-template.md` 사용. 07단계(통합테스트) — unit-1이 남긴
> "L1 부채"(traceability.md REQ-001 비고)를 이번에 정산한다.

## 1. 개요
- 테스트 대상: Feature A(인증/회원) 전체 — `backend/app/api/v1/auth.py`(register/login/me),
  `frontend/app/{register,login}/page.tsx`, `frontend/app/page.tsx`(홈)
- 테스트 유형: 통합(07단계)
- 적용 Tier: High(프로젝트 선언값)
- 테스트 목적: unit-1-test.md(06단계, L1 경량판)가 정상 경로 2케이스만 검증하고 명시적으로
  제외했던 에러 경로 4종(이메일 중복 409, role 422, 비밀번호 422, 로그인 401)과, "브라우저
  자동화 도구 부재"로 계속 보류돼 있던 인수조건 6(회원가입→로그인→홈 실제 화면 흐름)을
  이번에 처음으로 실측 검증한다.
- 관련 산출물: `docs/harness/units/unit-1-note.md`/`unit-1-test.md`, `docs/harness/traceability.md`
  REQ-001, `docs/harness/decisions.md` DEC-083
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: unit-1-test.md §2가 "06단계가 독립 재현하지 않은 상태"로 명시했던 항목 전부
  (이메일 중복, role 422, 비밀번호 422, 로그인 401, 프론트 화면 흐름) + 인증 없는 접근(401,
  Feature B와 공유하는 `get_current_user` 의존성이지만 인증 자체는 Feature A 소관이라
  이번 07에서 함께 확인)
- 제외 범위 및 사유: refresh 엔드포인트(unit-1-test.md §2가 이미 "정상 경로 인수조건
  목록에 없어 범위 밖"으로 명시) — 이번 07에서도 동일 사유로 제외.

## 3. 테스트 환경
- 실행 환경: Windows, 로컬 backend(uvicorn, `.claude/launch.json` "backend" 구성, 포트
  8000, Claude Browser pane의 `preview_start`로 기동), PostgreSQL 16/Redis(Docker,
  `final-project-db`/`final-project-redis`, 세션 시작 시 이미 Up 상태)
- 프론트엔드 화면 흐름(TC-A06)만 별도로 `frontend`(Next.js dev server, 포트 3000, 동일
  `preview_start`)를 추가 기동하고 Claude 내장 브라우저(Browser pane)로 실제 클릭/입력을
  수행했다 — 이 프로젝트 역사상 처음으로 "브라우저 자동화 도구 부재"(unit-1-note.md §3,
  DEC-001) 제약이 풀린 시점.
- 테스트 데이터: `itA-<suffix>@example.com`(백엔드 API 직접 호출용), `browser-e2e-itA2@example.com`
  (브라우저 E2E 전용) — 전부 이번 테스트가 신규 생성, 종료 후 DB에서 삭제
- 전제 조건: unit-1-test.md의 06 PASS(정상 경로) 그대로 승계, 이번 07은 그 나머지(에러
  경로+화면 흐름)만 추가로 커버한다(중복 검증 금지 원칙, `.claude/agents/07-integration-tester.md`)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-A01 | 이메일 중복 가입 (unit-1 인수조건 2) | `itA-*` 계정 이미 가입 | 같은 이메일로 `POST /auth/register` 재호출 | `409` | `409`, `{"code":"VALIDATION_ERROR","detail":"이미 가입된 이메일입니다."}` | PASS | |
| TC-A02 | role 잘못된 값 | 없음 | `POST /auth/register` `role="admin"` | `422` | `422`, `literal_error`, `"Input should be 'candidate' or 'recruiter'"` | PASS | admin 자가등록이 스키마 레벨(`Literal["candidate","recruiter"]`)에서 원천 차단됨을 실측 확인 |
| TC-A03 | 비밀번호 정책 위반(7자) | 없음 | `POST /auth/register` `password="short1"` | `422` | `422`, `string_too_short`, `"at least 8 characters"` | PASS | |
| TC-A04 | 로그인 실패(잘못된 비밀번호) | 계정 존재 | `POST /auth/login` 오답 비밀번호 | `401` | `401`, `{"code":"AUTH_INVALID_TOKEN","detail":"이메일 또는 비밀번호가 올바르지 않습니다."}` | PASS | |
| TC-A05 | 인증 토큰 없이 보호된 리소스 접근 | 없음 | `POST /interviews`(Authorization 헤더 없음) | `401` | `401`, `{"code":"AUTH_INVALID_TOKEN","detail":"인증 토큰이 필요합니다."}` | PASS | Feature B 엔드포인트로 확인하지만 검증 대상은 Feature A의 인증 의존성(`get_current_user`) 자체 |
| TC-A06 | 프론트 화면 흐름: 회원가입→로그인→홈 (unit-1 인수조건 6) | frontend(3000)/backend(8000) 기동 | 실제 브라우저: `/register` 폼 입력(이메일/비밀번호/비밀번호확인/이름/역할=지원자/약관동의)→제출 → `/login?registered=1` 리다이렉트 확인 → 이메일/비밀번호 입력→제출 → `/`(홈) 리다이렉트 확인 | 회원가입 성공 후 로그인 화면, 로그인 성공 후 "OOO님, 환영합니다" 홈 화면, 콘솔 에러 0건(HMR 관련 노이즈 제외) | 정확히 그대로 재현: `/login?registered=1`에 "회원가입이 완료되었습니다" 배너 표시 확인 → 로그인 후 `/`에 "Browser E2E님, 환영합니다" 렌더링 확인. 네트워크 로그로 `register`(201)→`login`(200)→`me`(200)→`interviews`(200) 순서 확인 | PASS | ⚠ 부수 발견(DEF-A1, 아래 6절) |

## 5. 커버리지
- unit-1-note.md §4 인수조건 1~6 전부 커버(1·4·5는 unit-1-test.md 06단계가 이미 PASS,
  2·3·에러경로 4종·6은 이번 07단계가 신규 커버) — REQ-001 인수조건 100% 실측 완료.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-A1 | `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL`이 실제 `.claude/launch.json` "backend" 구성 포트(8000)가 아니라 이전 세션(unit-1-test.md 06단계, 2026-09-19)이 임시로 썼던 포트 8010을 그대로 가리키고 있어, TC-A06 최초 시도 시 모든 API 호출이 `ERR_CONNECTION_REFUSED`로 실패("네트워크 오류가 발생했습니다" 배너)했다 | 브라우저로 `/register` 제출 → 네트워크 탭에서 `http://localhost:8010/...` 요청이 연결 거부로 실패하는 것을 확인 | Low(소스 코드 결함 아님, 로컬 환경설정 파일의 값 불일치 — DEC-066과 동일 계열: 코드가 아니라 로컬 환경 구성 문제) | Fixed | `frontend/.env.local`을 `http://localhost:8000/api/v1`로 정정 후 frontend dev server 재기동(Next.js는 `NEXT_PUBLIC_*` 값을 기동 시점에 굽기 때문에 재기동 필수) → 재시도 시 TC-A06 정상 PASS(네트워크 로그로 8000 포트 요청 200/201 확인) |

- 그 외 결함 없음 — TC-A01~A06 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 스크래치 결과 파일(세션 스크래치패드, 저장소 밖) —
  프로젝트 `.harness-tmp/`에는 아무것도 생성하지 않음(DB 직접 호출/브라우저 조작만 수행)
- 신규 생성한 DB 레코드: `itA-*@example.com`, `browser-e2e-itA2@example.com` 계정 —
  테스트 종료 직후 전부 DELETE로 정리, 재조회로 0건 확인
- 기동한 프로세스: `preview_start("backend")`, `preview_start("frontend")` — 둘 다
  `preview_stop`으로 종료 확인
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `frontend/.env.local`(DEF-A1 수정, 원래도 로컬 전용 파일이라
  git 추적 대상 아님 — `.gitignore` 확인), `docs/harness/*`(이 문서·decisions.md·
  traceability.md) 외 코드 변경 없음
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- refresh 엔드포인트는 여전히 미검증(§2 제외범위, 인수조건 목록 자체에 없음 — 리스크
  아님, 범위 정의상 해당 없음).
- `frontend/.env.local`은 gitignore된 로컬 파일이라 이 세션이 고친 값이 다른 개발자
  PC/CI에는 반영되지 않는다 — 팀 전체가 겪는 문제라면 `.env.example` 등 저장소 추적
  대상에 올바른 기본값을 문서화하는 것을 권장(이번 범위 밖, 후속 참고사항).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). REQ-001의 "L1 부채"를
  정산한다 — `traceability.md` REQ-001 행의 "L1 부채" 비고를 제거하고 통합테스트
  컬럼에 이 문서를 기록.

## 10. 내부 검증 (최소 2회)
- 1차(커버리지 확인): unit-1-note.md §4 인수조건 1~6이 TC-A01~06(+unit-1-test.md
  기존 TC-001/002)에 전부 1:1로 매핑되는지 재확인 — 누락 없음.
- 2차(다른 업무단위와의 경계 재검토, 08단계 대비): TC-A05는 Feature B의 엔드포인트를
  빌려 썼지만 검증 대상은 Feature A의 `get_current_user` 의존성이라는 점을 재확인 —
  이 경계가 08(전체 시스템 테스트)에서 "Feature A 실패가 Feature B 전체를 무너뜨리는가"
  판단의 기초 자료가 된다. DEF-A1(포트 불일치)이 코드가 아니라 로컬 설정 파일 문제임을
  재확인해 심각도를 Low로 유지(과대 평가 방지 — 근거는 6절).
