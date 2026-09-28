# 테스트 결과서 (Test Result Report) — Feature B 통합테스트 (면접 세션 상태머신, REQ-002/REQ-013)

> `templates/test-report-template.md` 사용. 07단계(통합테스트) — unit-2/unit-3가 남긴
> "L1 부채"(traceability.md REQ-002/REQ-013 비고)를 이번에 정산한다. unit-19(`GET
> /interviews` 목록, REQ-002 갭)는 이미 06단계에서 L3 정식판(60케이스, 59 PASS/1 FAIL
> → 재검증 PASS 확정, DEC-030 계열)까지 마쳤으므로 이번 07 범위에서 제외한다(중복 검증
> 금지 원칙).

## 1. 개요
- 테스트 대상: Feature B(면접 세션 상태머신) 전체 — `backend/app/api/v1/interviews.py`의
  `POST /interviews`, `POST /interviews/{id}/start`, `POST /interviews/{id}/end`,
  `GET /interviews/{id}`, `POST /interviews/{id}/resume`, `_apply_lazy_expiry`
- 테스트 유형: 통합(07단계)
- 적용 Tier: High(프로젝트 선언값)
- 테스트 목적: unit-2-test.md/unit-3-test.md(06단계, L1 경량판)가 정상 경로만 검증하고
  명시적으로 제외했던 예외/경계 케이스 전부 — 중복 시작/종료(409), 수평 권한 상승(403),
  인증 없음(401), 존재하지 않는 id(404), 세션 만료(410) — 를 하나의 연속된 상태머신
  시나리오로 통합 검증한다(개별 단위가 아니라 "단위 간 상태 전이"에 집중, 07단계 원칙).
- 관련 산출물: `docs/harness/units/unit-2-note.md`/`unit-2-test.md`,
  `unit-3-note.md`/`unit-3-test.md`, `docs/harness/03-system-design.md` §3/§4.1/§4.2,
  `docs/harness/decisions.md` DEC-026(세션 만료 24h)/DEC-084
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: unit-2-test.md §2·unit-3-test.md §2가 "06단계가 독립 재현하지 않은 상태"로
  명시했던 항목 전부 — 중복 시작 409, 중복 종료 409, completed 상태 resume 409, 수평
  권한 상승 403(GET/resume/end 3개 동작 모두), 인증 없음 401, 존재하지 않는 id 404,
  세션 만료 410(GET/resume 2개 동작)
- 제외 범위 및 사유:
  - `GET /interviews`(목록) — unit-19가 이미 L3 정식 통합 수준(API 21+브라우저 39=60건)
    으로 검증 완료(traceability.md REQ-002 비고), 중복 검증 금지 원칙에 따라 제외.
  - `paused` 자동 전이(하트비트 감지) — DEC-026이 이번 프로젝트 범위에서 신설하지 않기로
    확정한 기능이라 테스트 대상 자체가 존재하지 않음(unit-3-test.md §2와 동일 사유).
  - `code-submissions`/`whiteboard` GET — unit-9/17 소관, Feature B가 아님.

## 3. 테스트 환경
- 실행 환경: Windows, 로컬 backend(uvicorn, `.claude/launch.json` "backend" 구성, 포트
  8000, `preview_start`로 기동), PostgreSQL 16(Docker `final-project-db`, 포트 5544)
- 테스트 데이터: `itB1-<suffix>@example.com`/`itB2-<suffix>@example.com`(둘 다
  candidate, B2는 수평 권한 상승 시도 전용) — 신규 생성, 종료 후 DB에서 삭제.
  `ai_interview_notice` 동의는 unit-2/3 선례대로 DB에 직접 INSERT(`POST /consents` API가
  이 기능 범위 밖).
- 전제 조건: unit-2-test.md/unit-3-test.md의 06 PASS(정상 경로)를 그대로 승계, 이번
  07은 그 나머지(예외/경계 케이스)만 추가로 커버한다.

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-B01 | 인증 없음 | 없음 | `POST /interviews`(Authorization 없음) | `401` | `401`, `AUTH_INVALID_TOKEN` | PASS | |
| TC-B02 | 존재하지 않는 id | B1 로그인 완료 | `GET /interviews/{임의 uuid4}` | `404` | `404`, `NOT_FOUND` | PASS | |
| TC-B03 | 수평 권한 상승 — GET | B1 소유 interview 존재, B2 로그인 완료 | B2 토큰으로 `GET /interviews/{B1의 id}` | `403` | `403`, `AUTH_FORBIDDEN`, `"본인의 면접 세션만 조작할 수 있습니다."` | PASS | |
| TC-B04 | 수평 권한 상승 — resume | 상동 | B2 토큰으로 `POST .../resume` | `403` | `403`, 동일 코드/메시지 | PASS | |
| TC-B05 | 수평 권한 상승 — end | 상동 | B2 토큰으로 `POST .../end` | `403` | `403`, 동일 코드/메시지 | PASS | |
| TC-B06 | 중복 시작(이미 live) | B1이 동의 부여 후 `/start` 성공(live) | 동일 세션 `/start` 재호출 | `409` | `409`, `VALIDATION_ERROR`, `"scheduled 상태의 세션만 시작할 수 있습니다 (현재 상태: live)."` | PASS | |
| TC-B07 | 중복 종료(이미 completed) | `/end` 성공(completed) | 동일 세션 `/end` 재호출 | `409` | `409`, `VALIDATION_ERROR`, `"live 상태의 세션만 종료할 수 있습니다 (현재 상태: completed)."` | PASS | |
| TC-B08 | completed 상태에서 resume 시도 | 상동 | `POST .../resume` | `409` | `409`, `VALIDATION_ERROR`, `"live 또는 paused 상태의 세션만 재개할 수 있습니다 (현재 상태: completed)."` | PASS | unit-3-note.md 인수조건 7 |
| TC-B09 | 세션 만료 — resume | 신규 세션 `/start`(live) 후 DB에서 `started_at`을 25시간 전으로 조작(DEC-026 임계값 24h 초과) | `POST .../resume` | `410 SESSION_EXPIRED` | `410`, `{"code":"SESSION_EXPIRED","detail":"이 세션은 만료되어 재개할 수 없습니다. 새 면접을 시작해 주세요."}` | PASS | `_apply_lazy_expiry`가 lazy하게 DB status를 `expired`로 커밋하는 것까지 확인 |
| TC-B10 | 세션 만료 — GET(조회) | 상동(TC-B09 이후 같은 세션) | `GET /interviews/{id}` | (아래 6절 참고 — 최초 예상은 `410`이었으나 실제 설계는 다름) | `200`, `{"status":"expired",...}` | PASS(예상 정정 후) | 아래 6절 "판단 근거" 참고 |

## 5. 커버리지
- unit-2-note.md 인수조건 5·6·8·9(중복 시작/종료, 수평 권한 상승, 인증 없음, 존재하지
  않는 id) + unit-3-note.md 인수조건 6·7·8·9(만료 410, completed 409, 수평 권한 상승,
  인증 없음/존재하지 않는 id) 전부 커버 — REQ-002/REQ-013 인수조건 100% 실측 완료
  (unit-19가 이미 커버한 목록조회 제외).

## 6. 결함(Defect) 목록 및 판단 근거
- **TC-B10 관련 — 결함 아님(테스트 설계 당시의 잘못된 예상을 코드 대조로 정정)**:
  최초 테스트 설계 시 "만료된 세션은 GET도 410을 반환해야 한다"고 가정했으나, 실행
  결과 `GET /interviews/{id}`는 만료된 세션도 `200`으로 반환하며 응답 바디의
  `status` 필드가 `"expired"`로 표시되는 것을 확인했다. `interviews.py::_apply_lazy_expiry`
  독스트링(146행)과 `get_interview` 핸들러(459행)를 직접 대조한 결과, 이는 **의도된
  설계**임을 확인했다 — 04-ux-design.md [C-12]가 "서버가 내려주는 SESSION_EXPIRED를
  그대로 표시"하도록 요구한 것은 **조회(GET, 상태를 그대로 보여주는 passive 엔드포인트)**
  가 아니라 **행동(resume/turn 제출 등 active 엔드포인트가 만료된 세션에 실제로 뭔가를
  하려 할 때)** 에 한정된다 — GET은 항상 200으로 현재 상태(expired 포함)를 알려주고,
  화면이 그 값을 보고 "만료됨" UI를 그리는 구조다. 03-system-design.md §4.1은 에러
  코드 존재만 정의하고 어떤 엔드포인트가 그것을 던지는지는 05단계 구현 재량이었으므로
  (unit-3-note.md 참고), 이 해석이 설계와 모순되지 않는다. **결함으로 등록하지 않고,
  테스트 케이스의 기대값만 정정**했다(위 4절 표에 그 경위를 그대로 남김 — 검증 과정을
  숨기지 않는다는 원칙).
- 그 외 결함 없음 — TC-B01~B09 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 스크래치 결과 파일(세션 스크래치패드, 저장소 밖)
  — 프로젝트 `.harness-tmp/`에는 아무것도 생성하지 않음
- 신규 생성한 DB 레코드: `itB1-*`/`itB2-*` 계정 2건, interview 2건(정상 경로용 1건 +
  만료 시나리오용 1건), consents 1건 — 테스트 종료 직후 전부 DELETE로 정리, 재조회로
  0건 확인
- 기동한 프로세스: `preview_start("backend")` — `preview_stop`으로 종료 확인
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*`(이 문서·decisions.md·traceability.md) 외
  코드 변경 없음(Feature B 자체는 이번 07에서 코드 수정이 없었음 — 결함이 없었으므로)
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- `paused` 상태로의 자동 전이(하트비트/WS 접속 끊김 감지)는 여전히 미구현(DEC-026,
  범위 자체가 아님 — 리스크 아님, 설계상 확정된 제외).
- 실제 turn/코드/화이트보드 콘텐츠 복원은 이번 Feature B 범위가 아니라 unit-4/9/17이
  각각 담당(unit-3-note.md §2가 이미 명시).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). REQ-002/REQ-013의 "L1 부채"를
  정산한다 — `traceability.md` 두 행의 "L1 부채" 비고를 제거하고 통합테스트 컬럼에
  이 문서를 기록.

## 10. 내부 검증 (최소 2회)
- 1차(커버리지 확인): unit-2-note.md/unit-3-note.md의 미검증 인수조건 목록과
  TC-B01~B10을 1:1 대조 — 누락 없음(§5).
- 2차(단위 간 경계 재검토 — 07단계 고유 가치): 개별 06 테스트는 "생성"·"시작/재접속/
  재개"를 각각 별도 세션으로 봤지만, 이번 07은 **하나의 세션이 scheduled→live→
  completed로 흐르는 동안 각 상태 전이 시점마다 잘못된 동작(중복 시작/종료/재개 시도)이
  일관되게 차단되는지**를 연속 시나리오로 확인했다 — 이것이 unit-2/unit-3 테스트가
  각자 정상 경로만 보느라 놓칠 수 있었던 "단위 간 상태 일관성"이다. 또한 TC-B10에서
  최초 가정이 틀렸다는 것을 스스로 의심하고 코드/설계 문서까지 재대조한 것 자체가
  2차 검증의 핵심(성급하게 FAIL로 기록하지 않고 근거를 확인)이다.
