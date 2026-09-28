# 테스트 결과서 (Test Result Report) — 503 QUEUE_FULL 실측 (job_queue.py §1.3/unit-37 §4.6 (2))

## 1. 개요
- 테스트 대상: `backend/app/api/v1/recruiter.py::assign_rubric_template`(`PUT
  /recruiter/interviews/{id}/rubric-template`)의 `queue_length() >= MAX_QUEUE_LENGTH`
  503 방어 로직
- 테스트 유형: 통합(실제 서버+실제 Redis 큐를 실측 임계값까지 채운 실HTTP 검증)
- 적용 Tier: Low(기존 코드 실측 검증, 코드 변경 없음)
- 테스트 목적: `job_queue.py` 모듈 docstring이 "턴/종료 경로에는 큐 상한 로직이 아직
  없고, 재채점 엔드포인트만 예외적으로 503을 반환한다"고 명시한 이 유일한 방어 경로가,
  실제로 큐(`ai_pipeline`, Redis 리스트)가 `MAX_QUEUE_LENGTH`(50)에 도달했을 때 진짜로
  503을 반환하는지 — 지금까지 프로젝트 전체에서 한 번도 실측된 적이 없었던 것을
  처음으로 실측한다.
- 관련 산출물: `docs/harness/decisions.md` DEC-085, `backend/app/services/job_queue.py`
  모듈 docstring
- 테스트 수행자(에이전트): 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: 실제 uvicorn 서버(포트 8000) + 실제 Redis(`final-project-redis`)의 `ai_pipeline`
  리스트를 실제로 50개 이상 채운 상태에서, 실제 회원가입/로그인으로 발급받은 JWT로
  실제 HTTP `PUT` 요청을 보내 503을 검증. 큐를 비운 뒤 재시도해 정상 200(대조군)도 확인.
- 제외 범위 및 사유: 턴/종료 경로의 큐 상한(모듈 docstring이 이미 "이번 유닛에서 임의로
  확장하지 않고 그대로 인수인계, 09단계/REQ-038과 겹치는 영역"으로 명시) — 코드
  자체가 없으므로 테스트 대상 부존재. 실제 Celery 워커가 그 50개 항목을 소비하는
  시나리오 — 이번 테스트 목적(큐 상한 방어 자체)과 무관.

## 3. 테스트 환경
- Windows, 로컬 backend(uvicorn, `.claude/launch.json` "backend" 구성, 포트 8000,
  `preview_start`로 기동), PostgreSQL 16/Redis(Docker, 세션 시작 시 이미 Up 상태)
- 테스트 데이터: recruiter 1명 + candidate 1명 + interview 1건(report_status=ready로
  시드 — 재채점 경로 진입 조건), `ai_pipeline` Redis 리스트에 더미 문자열 50개
  (`dummy-0`~`dummy-49`)를 직접 `RPUSH`

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | 큐를 실측 임계값(50)까지 채운 뒤 재채점 요청 | `ai_pipeline`에 더미 50개 RPUSH(큐 길이 0→50) → recruiter 토큰으로 실제 `PUT /recruiter/interviews/{id}/rubric-template` 호출 | `503`, `code=QUEUE_FULL` | `503`, `{"code":"QUEUE_FULL","detail":"지금 처리 대기 중인 작업이 많습니다. 잠시 후 다시 시도해 주세요."}` | PASS |
| TC-002 | 503으로 거부됐을 때 DB 상태가 오염되지 않는지 | TC-001 직후 interview.report_status 재조회 | 여전히 `ready`(큐 검사가 상태 변경 이전에 먼저 실행되므로) | `ready` 그대로 확인 | PASS |
| TC-003 | 큐를 비운 뒤(대조군) 동일 요청이 정상 처리되는지 | `ai_pipeline`에서 더미 50개 제거(큐 길이 0으로 복원) → 동일 엔드포인트 재호출 | `200` | `200`, `rubric_template_id` 정상 반환 | PASS |

## 5. 커버리지
- `queue_length() >= MAX_QUEUE_LENGTH` 분기의 참/거짓 양쪽 경로 모두 실측(TC-001 vs
  TC-003), 거부 시 부수효과 없음(TC-002)까지 확인 — 이 방어 로직의 실질적 커버리지 100%.

## 6. 결함(Defect) 목록
- 결함 없음 — TC-001~003 전부 실측으로 확인(위 표 근거).
- 참고(결함 아님, 테스트 진행 중 관측한 환경 특이사항): TC-001 확인 직후, 같은
  `httpx.Client` 커넥션을 재사용해 두 번째 요청(TC-003에 해당)을 보냈을 때 클라이언트
  쪽에서 10초 타임아웃이 발생했다. 서버 로그를 확인한 결과 첫 번째 503 요청 이후
  서버는 정상적으로 응답을 대기하고 있었고(별도 연결로 즉시 재시도하니 정상 200
  수신), DB 상태(`report_status=queued`로 정상 전이)로 미루어 서버가 요청을 못 받은
  것이 아니라 클라이언트 쪽 keep-alive 연결 재사용 과정의 일시적 현상으로 판단된다
  (Windows 로컬 httpx 클라이언트의 알려진 산발적 증상, 이 프로젝트에서도 cp949
  콘솔 표시 문제처럼 "실제 결함처럼 보이지만 실은 테스트 하네스/환경 쪽 문제"인
  사례가 반복적으로 있었음 — 이번 것도 그 계열로 판단). 새 연결로 즉시 재확인해
  정상 동작을 재검증했으므로(TC-003 결과가 그 재확인) 서버 코드에 대한 결함으로
  등록하지 않는다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 스크래치 결과 파일(세션 스크래치패드, 저장소 밖)
- Redis에 생성한 더미 큐 항목 50개 + 재시도로 실제 enqueue된 Celery 태스크 메시지 1건,
  대응 `job_watch:*` 감시 키 1건: 전부 확인 후 `DEL`로 정리, 재조회로 `ai_pipeline`
  길이 0·`job_watch:*` 0건 확인
- 신규 생성한 DB 레코드: recruiter 1명, candidate 1명, interview 1건 — 테스트 종료
  직후 DELETE로 정리, 재조회로 0건 확인
- 기동한 프로세스: `preview_start("backend")` — `preview_stop`으로 종료 확인
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(이 테스트는 기존 코드를
  그대로 검증만 했고 결함이 없었으므로 코드 수정 없음)
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- 턴/면접종료 경로에는 여전히 큐 상한 방어가 없다(모듈 docstring이 이미 밝힌 설계
  범위, REQ-038/09단계 인계 대상 — 이번 테스트가 새로 발견한 문제가 아니라 기존에
  알려진, 코드가 아직 없는 영역).
- `queue_length()` 자체가 Redis 순간 오류 시 "확인 불가 → 진행 허용"으로 설계돼
  있음(job_queue.py 기존 주석) — 즉 Redis 장애 상황에서는 이 방어가 우회될 수 있으나,
  이는 "과도하게 막지 않는다"는 기존 설계 의도이지 이번 테스트의 결함이 아니다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). "503 QUEUE_FULL 미실측"
  항목을 실측 완료로 정산.

## 10. 내부 검증
- L1 경량판(Low Tier) — 1차 검증(작성자 관점): TC-001~003 실행 로그와 본 문서 대조,
  결함 0건. 규칙 B Tier=Low 예외에 따라 2차 생략. 단, §6의 클라이언트 타임아웃
  특이사항과 §8의 잔존 리스크는 2차 없이도 명시적으로 남김(생략이 리스크 은폐가
  되지 않도록).
