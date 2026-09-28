# 테스트 결과서 (Test Result Report) — unit-10 DEF-002 수정(리포트 job 유실 시 복구 불가)

## 1. 개요
- 테스트 대상: `backend/app/services/job_watchdog.py`(`register_job` job_type 확장,
  `_mark_report_failed` 신규, `_check_job` 리포트 job 전이 분기), `backend/app/services/job_queue.py`
  (`enqueue_report_generation_job`이 `job_type="report"` 전달)
- 테스트 유형: 단위+통합 병합(Low 등급 — 기존 watchdog 인프라 위에 분기 1개 추가, 신규
  아키텍처 없음)
- 적용 Tier: Low
- 테스트 목적: 진짜 워커 프로세스 크래시로 리포트 생성 job이 영구 유실됐을 때(unit-10-test.md
  DEF-002), `Interview.report_status`가 `queued`에 영원히 머물지 않고 `failed`로 전이돼
  화면의 기존 "다시 생성하기" 버튼이 실제로 동작하는지 실측 확인
- 관련 산출물: `docs/harness/decisions.md` DEC-082, `docs/harness/units/unit-10-test.md` DEF-002
- 테스트 수행자(에이전트): 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: `job_watchdog.py`의 신규/수정 로직을 실제 Redis(aioredis)·실제 PostgreSQL(DB row)로
  직접 검증. 워커 크래시 자체는 재현하지 않고(실제 프로세스를 죽이는 것은 재현 비용 대비
  검증 가치가 낮음 — "STARTED 후 타임아웃 경과"라는 관측 가능한 결과 상태를 직접
  구성해 그 이후 로직만 정확히 검증), Celery `AsyncResult.state`는 `unittest.mock.patch`로
  `"STARTED"`를 반환하도록 대체.
- 제외 범위 및 사유: 실제 uvicorn+Celery 워커 프로세스를 기동해 물리적으로 kill하는
  E2E는 unit-7-test.md TC-014(2026-09-20)가 이미 "워커 재기동 후에도 해당 job 이벤트가
  다시 오지 않음"을 실측 확인한 바 있어(DEF-008 근거), 이번에는 그 위에 새로 추가된
  DB 전이 로직만 별도로 검증하면 충분하다고 판단.

## 3. 테스트 환경
- Windows, Python 3.13(`backend/.venv`), Docker Desktop(`final-project-db`/`final-project-redis`,
  세션 시작 시 이미 Up 상태)
- 테스트 데이터: 신규 candidate 1명 + interview 1건(테스트 종료 직후 DB에서 삭제)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | `register_job(job_type="report")`이 Redis에 job_type을 정확히 저장하는지 | `register_job` 호출 후 raw Redis GET | JSON에 `"job_type":"report"` 포함 | 정확히 포함 확인 | PASS |
| TC-002 | `_mark_report_failed`가 `queued`→`failed` 전이 | interview.report_status=queued 상태에서 호출 | `failed`로 변경 | `failed` 확인 | PASS |
| TC-003 | `_mark_report_failed`가 이미 `queued`가 아닌 상태(예: `ready`)는 덮어쓰지 않음 | interview.report_status=ready 상태에서 호출 | `ready` 그대로 유지(워커가 늦게 살아나 정상 완료했을 가능성 보호) | `ready` 그대로 확인 | PASS |
| TC-004 | 전체 `_check_job` 경로 — `job_type="report"` + 타임아웃 경과 시뮬레이션 → DB 전이 + 감시키 정리 | `started_seen_at`을 999초 전으로 설정한 감시키를 실제 Redis에 기록 후 `_check_job` 실행(AsyncResult.state는 "STARTED"로 mock) | `report_status=failed`로 전이, 감시 키(`job_watch:*`) 삭제 | 정확히 전이 확인, 감시 키 존재 여부(`exists`) 0 확인 | PASS |
| TC-005 | `job_type="turn"`(기본값)은 동일 타임아웃에도 `report_status`를 건드리지 않음(회귀 방지) | TC-004 직후 같은 interview에 대해 turn용 감시키로 `_check_job` 재실행 | `report_status`는 TC-004의 `failed`에서 변화 없음 | 변화 없음 확인 | PASS |

## 5. 커버리지
- 신규 분기(job_type 구분, DB 전이, 조건부 스킵) 100% — TC-001~005가 참/거짓 양쪽
  경로와 회귀 케이스(턴 job 비영향)까지 모두 실행.
- 커버되지 않은 부분: 실제 물리적 워커 프로세스 kill(§2 제외범위 참고, 기존 unit-7-test.md
  TC-014로 대체 커버).

## 6. 결함(Defect) 목록
- 결함 없음 — TC-001~005 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 스크래치 결과 파일(세션 스크래치패드, 저장소 밖)
- 신규 생성한 DB 레코드: candidate 1명 + interview 1건 — 테스트 종료 직후 DELETE로 정리
- Redis에 생성한 감시 키(`job_watch:*`)·테스트용 큐 항목: 테스트 로직 자체가 정리하거나
  (감시 키는 `_check_job`이 삭제) 세션 종료 시 잔여 확인 후 수동 삭제 완료
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `job_watchdog.py`, `job_queue.py`, `docs/harness/*` 외 변경 없음
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- 화면(`report/page.tsx`)의 "다시 생성하기" 버튼 자체는 이미 구현·존재하는 코드라
  이번에 새로 테스트하지 않았다(이 버튼의 독립적인 프론트 동작은 최초 구현 시점에
  이미 검증된 기존 코드) — 이번 수정으로 이 버튼이 "실제로 트리거될 조건"(report_status
  가 failed로 전이되는 것)이 처음으로 실제 발생 가능해졌다는 점이 이번 테스트의 핵심.
- 워커가 STARTED 관측 직전에 죽는 극단적 타이밍(예: enqueue 직후 즉시 크래시, PENDING
  상태에서 영원히 멈춤)은 기존 watchdog 설계상 "AC5 정상 대기 시나리오와 구분 불가"로
  의도적으로 다루지 않는다(job_watchdog.py 기존 주석 그대로, 이번 수정 범위 밖).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료)

## 10. 내부 검증
- L1 경량판(Low Tier) — 1차 검증(작성자 관점): TC-001~005 실행 로그와 본 문서 대조,
  결함 0건. 규칙 B Tier=Low 예외에 따라 2차 생략. 단, §8의 "화면 버튼은 기존 코드"라는
  구분과 "극단적 타이밍은 범위 밖"이라는 한계는 2차 없이도 명시적으로 남김.
