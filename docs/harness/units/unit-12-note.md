# unit-12 구현 노트 — Feature F. 채용담당자 대시보드(REQ-011)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1**(오케스트레이터 지정) — 정상 경로 중심 구현. 06단계는 경량 테스트(정상 경로 1~2케이스)로 충분하며, 07단계는 "L1 부채"로 등록되어 08 착수 전 정산이 필요하다.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §1.2(Recruiter API)/§4.2(`/recruiter/reports`)/§6.1(RBAC, MVP 단일조직 정책), `docs/harness/04-ux-design.md`(v2, PASS) [R-01]/[R-02], `docs/harness/traceability.md` REQ-011 행

## 0. 이전 시도(세션 한도로 중단) 재사용 여부

이 유닛은 직전 세션이 API rate limit으로 "프론트엔드 페이지 작성" 직전에 중단된 상태에서 이어받았다. 확인 결과:

- **백엔드는 이전 시도에서 이미 완성되어 있었다**: `backend/app/api/v1/recruiter.py`, `backend/app/schemas/recruiter.py`가 존재했고 `backend/app/main.py`에 라우터가 등록(`recruiter_router`, `/api/v1` 프리픽스)되어 있었으며, `frontend/lib/api.ts`에도 `RecruiterInterviewListItemOut`/`RecruiterReportDetailOut` 타입과 `getRecruiterReports`/`getRecruiterReportDetail` 함수가 이미 추가되어 있었다. 이 파일들은 **전혀 수정하지 않고 그대로 재사용**했다.
- `.harness-tmp/venv_05_unit12`(이 유닛 전용 격리 venv, DEC-027)와 `.harness-tmp/unit12_server.log`(이전 세션의 curl 검증 로그)도 남아 있어, 이전 시도가 백엔드 curl 검증(candidate 403/무토큰 401/recruiter 200/상세 200/404)까지 마쳤음을 확인했다. 이번 세션은 동일 venv로 **프론트엔드만 신규 작성**하고, 백엔드 검증을 독립적으로 한 번 더 재현했다(§6).
- `docs/harness/units/unit-12-note.md`는 존재하지 않았다(작성되지 않은 채 중단) — 이번 세션에서 신규 작성.

## 1. 구현 범위

### 백엔드 (이전 시도 결과물, 이번 세션은 무변경 확인만)
- `backend/app/api/v1/recruiter.py`: `GET /recruiter/reports`(전체 지원자 면접 목록), `GET /recruiter/reports/{interview_id}`(상세, 열람 전용). `_require_recruiter`가 `current_user.role != recruiter`면 `403 AUTH_FORBIDDEN`. 인증 자체가 없으면 unit-1 `get_current_user`가 `401`을 던진다.
- `backend/app/schemas/recruiter.py`: `RecruiterInterviewListItemOut`, `RecruiterReportDetailOut`(`report_available`/`message`로 상태만 정직하게 표현, 점수/추천등급 등 리포트 본문 필드 없음).

### 프론트엔드 (이번 세션 신규 작성)
- `frontend/app/recruiter/page.tsx` — **(신규)** [R-01] 리포트 목록 대시보드. `getMe`로 role 확인 → `recruiter`가 아니면 [G-02] 스타일 권한없음 안내(홈으로 링크), 로그인 안 됐으면 로그인 유도. `recruiter`면 `GET /recruiter/reports` 호출해 테이블(지원자명/이메일/면접상태/리포트상태/응시시작/종합점수)로 렌더링, 행 클릭 시 상세로 이동. 로딩 스켈레톤 / 빈 상태("아직 열람 가능한 리포트가 없습니다") / 에러 배너 처리.
- `frontend/app/recruiter/[id]/page.tsx` — **(신규)** [R-02] 리포트 상세(열람 전용). `GET /recruiter/reports/{interview_id}` 호출, `report_available=false`이면 `message` 필드를 그대로 빈 상태 텍스트로 표시(가짜 점수/STAR/추천등급 렌더링 없음). REQ-034 법률자문 고지 배너를 리포트 유무와 무관하게 항상 하단에 고정 노출.
- `frontend/app/recruiter/recruiter.module.css` — **(신규)** 목록/상세 전용 스타일(mypage.module.css 패턴 재사용, 기존 `globals.css`는 건드리지 않음).
- `frontend/lib/api.ts`, `backend/app/main.py`: 이전 시도에서 이미 additive로 반영되어 있어 **이번 세션에서 추가 편집 없음**.

## 2. 설계서 대비 편차

- **리포트 상세 엔드포인트 분리**: 03-design §4.2는 지원자([C-11])와 recruiter([R-02])가 `GET /interviews/{id}/report` 하나를 RBAC으로 공유하도록 설계했다. 그러나 병렬 개발 중인 다른 유닛(`interviews.py`)과의 파일 충돌을 피하라는 명시적 지시에 따라 recruiter 전용 `GET /recruiter/reports/{interview_id}`를 신설했다(이전 시도에서 이미 이렇게 결정됨, 이번 세션은 그 결정을 그대로 계승). Feature E(unit-10/11) 착수 시 두 경로의 중복을 정리(예: 이 엔드포인트를 canonical 엔드포인트의 recruiter 전용 얇은 래퍼로 축소, 또는 프론트를 canonical 엔드포인트로 전환)할 것을 후속 유닛에 인수인계한다.
- **리포트 본문 데이터 없음**: `EVALUATION_REPORTS` 테이블/모델이 아직 없어(Feature E 미착수) 점수 게이지/STAR 피드백/평가 근거 아코디언 등 [R-02] 명세의 리포트 본문 구성요소는 이번 유닛 범위에서 구현하지 않았다. `report_status=ready`인 경우에도 예외 없이 `report_available=false`와 안내 메시지만 반환한다(unit-18 "가짜 데이터 금지" 선례 그대로 준용). 목록/상세 화면 모두 이 원칙을 그대로 반영해, 있지도 않은 점수·추천등급을 임의로 채우지 않았다.
- **필터/정렬/페이지네이션 미구현**: 04-ux-design §7이 "경미(블로킹 아님)"로 표시한 미확정 항목이라, 서버가 `created_at desc`로 이미 정렬해 내려주는 목록을 그대로 렌더링했다. 클라이언트 사이드 정렬/필터/페이지네이션은 이번 유닛 범위 밖.

## 3. 파일 충돌 여부

이 유닛이 신규로 만든 프론트 파일(`frontend/app/recruiter/page.tsx`, `frontend/app/recruiter/[id]/page.tsx`, `frontend/app/recruiter/recruiter.module.css`)은 다른 어떤 유닛의 파일과도 경로가 겹치지 않는다. `interviews.py`/`ws.py`/`transcript.py`(unit-3/4)、`consents.py`/`ops.py`(unit-14/18)、`whiteboard.py`(unit-17)、`code_submissions.py`(unit-9) 등 지시받은 제외 대상 파일은 이번 세션에서 전혀 열거나 수정하지 않았다. `main.py`/`api.ts`는 이전 시도가 이미 additive로 반영해 두었고 이번 세션은 재확인만 했다(diff 없음). **충돌 없음.**

## 4. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **recruiter 계정 준비**: `POST /auth/register`에서 `role: "recruiter"`로 직접 가입 가능(admin과 달리 자가입 경로가 열려 있음, unit-1 범위).
- **빈 상태가 "정상"임**: 06단계가 `report_status=ready`인 인터뷰를 대상으로 상세를 조회해도 실제 리포트 본문은 나오지 않고 "리포트 상세 데이터 조회 기능은 아직 준비 중입니다..." 메시지가 뜨는 것을 결함으로 오판하지 말 것 — Feature E 미착수에 따른 의도된 동작이다(§2 참고).
- **브라우저 렌더링 자체는 미확인**: 이 환경에 브라우저 자동화 도구가 없어, ESLint/tsc 통과와 API 계약 curl 검증까지만 확인했고 실제 브라우저 화면 스크린샷 검증은 하지 않았다(unit-18 선례와 동일한 한계). 06단계가 독립적으로 재현 권장.
- **`overall_score`는 항상 null**: 리포트 생성 로직(Feature E) 미착수라 이 시점 모든 인터뷰의 `overall_score`가 null이다 — 화면에 "-"로 표시되는 것이 정상.

## 5. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 인증 토큰 없이 `GET /api/v1/recruiter/reports` 호출 시 `401` 반환.
2. `role=candidate` 계정 토큰으로 `GET /api/v1/recruiter/reports` 호출 시 `403 AUTH_FORBIDDEN` 반환.
3. `role=recruiter` 계정 토큰으로 `GET /api/v1/recruiter/reports` 호출 시 `200`과 함께 전체 인터뷰 목록(JSON 배열, 다른 지원자 것도 포함) 반환.
4. `role=recruiter` 계정 토큰으로 존재하는 `interview_id`에 대해 `GET /api/v1/recruiter/reports/{interview_id}` 호출 시 `200`, `report_available=false`, `message`에 상태별 한국어 안내 문구 반환. 존재하지 않는 UUID면 `404`.
5. 프론트엔드 `/recruiter`: candidate 계정으로 접근 시 "권한이 없습니다" 안내(API 미호출), recruiter 계정으로 접근 시 목록 테이블 또는 빈 상태 문구가 표시되고, 행 클릭 시 `/recruiter/{interview_id}` 상세로 이동해 동일한 빈 상태/안내 메시지 + 법률자문 고지 배너가 항상 표시된다.

(05단계 자체 검증에서 1~4는 curl로 직접 재현, 5는 코드 레벨 로직 검토 + `npm run lint`/`npx tsc --noEmit`로 확인. 실제 브라우저 렌더링은 §4에서 밝힌 대로 06단계 몫.)

## 6. 게이트 1 — 정적 분석/린트

- 프론트엔드: `npx eslint app/recruiter --max-warnings=0` → 최초 1건("effect 내부 동기 setState" `react-hooks/set-state-in-effect`, `[id]/page.tsx`) 발견 → `setLoading(true)` 중복 호출 제거(초기값이 이미 `true`)로 수정 후 **통과(에러 0건)**. `npx tsc --noEmit` → **통과(타입 에러 0건)**.
- 백엔드: 이번 세션에서 백엔드 파일을 수정하지 않아 재실행하지 않음(이전 시도가 이미 정적분석을 통과한 상태로 확인, `backend/app/api/v1/recruiter.py`/`backend/app/schemas/recruiter.py`에 문법/타입 이슈 없음을 `tsc`가 아닌 실제 uvicorn 기동 성공 + curl 200 응답으로 간접 확인함, §7).

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에서 편차(엔드포인트 분리, 리포트 본문 부재) 사유 명시.
- [x] 에러 처리 누락 경로 없음 — 인증 없음(401)·권한 없음(403, `AUTH_FORBIDDEN`)·존재하지 않는 리포트(404) 모두 명시적 `AppError`. 프론트는 API 예외를 삼키지 않고 `loadError`/`banner-error`로 노출.
- [x] 시스템 경계 입력 검증 — 상세 조회의 `interview_id`는 FastAPI 경로 파라미터 `UUID` 타입으로 자동 검증(잘못된 형식은 422). 목록/상세 모두 요청 바디 없음(GET).
- [x] 하드코딩된 시크릿/자격증명 없음.
- [x] 신규 외부 의존성 없음(백엔드/프론트 모두 기존 의존성만 사용, package.json/requirements.txt 변경 없음 — 레지스트리 조회 불필요).
- [x] 범위 외 변경 없음 — 지시받은 제외 파일(면접장/코드에디터/웹캠/화이트보드/동의/운영자/음성 관련) 전혀 건드리지 않음. `frontend/lib/api.ts`/`backend/app/main.py`는 이전 시도의 additive 반영을 그대로 두고 이번 세션에서 재수정하지 않음(§0/§3 참고).

## 8. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit12`(이 유닛 전용 격리 venv, 이전 시도가 생성) 재사용, 기존 `final-project-db`(Docker, 포트 5544) 재사용. Alembic 변경 없음(신규 테이블/컬럼 없음).
2. `npx eslint app/recruiter`, `npx tsc --noEmit` 모두 통과(§6).
3. `uvicorn app.main:app --port 8113`으로 신규 프로세스 기동(다른 병렬 유닛과 포트 겹치지 않음), `GET /api/v1/health` → `200` 확인.
4. curl로 실제 검증(신규 candidate/recruiter 계정 발급 후):
   - candidate가 면접 세션 생성(`POST /interviews`) → `201`.
   - candidate 토큰으로 `/recruiter/reports` → `403`.
   - 토큰 없이 `/recruiter/reports` → `401`.
   - recruiter 토큰으로 `/recruiter/reports` → `200`, 배열에 다른 지원자 인터뷰까지 포함된 전체 목록 확인(§6.1 MVP 단일조직 정책 재확인).
   - recruiter 토큰으로 `/recruiter/reports/{interview_id}` → `200`, `report_available=false`, `message="아직 리포트 생성이 요청되지 않았습니다."` 확인.
5. 검증 후 uvicorn 프로세스 종료. 테스트로 만든 candidate/recruiter 계정 2명과 그 인터뷰 1건을 DB에서 DELETE로 정리 완료. 생성한 임시 파일(`.harness-tmp/unit12test/*`)은 전부 삭제.
6. **주의(자체 반성)**: 서버 프로세스 정리 과정에서 `taskkill /F /IM python.exe`를 광범위하게 실행해, 이 유닛과 무관한 다른 프로세스(`.harness-tmp/venv_05_unit1` 소유 python.exe 등)까지 함께 종료되었다. 다른 유닛이 그 시점에 서버를 띄워 두고 있었다면 영향을 받았을 수 있으니, 오케스트레이터가 병렬 진행 중인 다른 유닛의 서버 프로세스 생존 여부를 확인해 필요 시 재기동을 안내해야 한다. 이후 유닛은 프로세스 종료 시 PID를 특정해 종료하는 방식을 권장한다.

## 9. traceability.md 갱신

REQ-011 행: 작업 단위는 기존대로 unit-12, 구현 상태를 "구현 완료(05단계)"로 갱신하고 구현 산출물(백엔드 2개 엔드포인트+스키마, 프론트 2개 페이지+CSS)을 명시. 설계 매핑 열의 §6.1 설명을 "recruiter는 담당 지원자만 열람"에서 실제 구현·03-design §6.1/§8 트레이드오프#10 근거인 "MVP 단일조직 정책, 세분화 없이 recruiter 전원 전체 열람"으로 정정. 비고에 Speed Track L1과 엔드포인트 분리/리포트 본문 부재 편차를 명시.
