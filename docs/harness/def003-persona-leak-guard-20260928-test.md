# 테스트 결과서 (Test Result Report) — unit-10 DEF-003 수정(리포트 파싱 실패 폴백 REQ-039 적용)

## 1. 개요
- 테스트 대상: `app/api/v1/interviews.py::_report_to_out`(신규 유출 마커 검사 분기),
  `docs/harness/units/unit-10-test.md` DEF-003
- 테스트 유형: 단위(Low 등급, 기존 REQ-039 탐지 함수를 놓친 경로에 재적용하는
  국소 수정이라 새로운 설계 위험 없음)
- 적용 Tier: Low
- 테스트 목적: (1) 리포트 생성 §4.4 파싱 실패 폴백이 사용자에게 그대로 보여주던
  LLM 원문에 시스템 프롬프트 유출 마커가 있을 때 실제로 안내 문구로 치환되는지,
  (2) 유출 마커가 없는 기존 정상 폴백 텍스트는 그대로 보존돼 기존 동작이
  회귀하지 않는지, (3) `report`가 없는 경우 등 기존 분기가 그대로 동작하는지
  실측 확인
- 관련 산출물: `docs/harness/decisions.md` DEC-080, `docs/harness/units/unit-10-test.md`
  DEF-003, `docs/harness/traceability.md` REQ-039
- 테스트 수행자(에이전트): 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: `_report_to_out()` 함수 단위 — 지원자 화면(`GET /interviews/{id}/report`)과
  채용담당자 화면(`GET /recruiter/reports/{id}`)이 이 함수 하나를 공유하므로
  (recruiter.py가 `_report_to_out`을 직접 재사용, 코드 중복 없음) 이 함수 검증이
  두 화면 모두를 커버한다.
- 제외 범위 및 사유: 실제 uvicorn 서버를 띄운 실HTTP E2E는 이번 범위에서
  생략 — 이 수정은 API 계약(응답 스키마)을 바꾸지 않는 순수 서버 내부 치환
  로직이라 회귀 위험이 낮고, 함수 자체를 실제 SQLAlchemy 모델 인스턴스로
  직접 호출해 검증하는 것이 더 정확하다고 판단(모킹 없이 실제 클래스 사용).

## 3. 테스트 환경
- Windows, Python 3.13(`backend/.venv`), DB/서버 프로세스 기동 불필요(함수
  직접 호출 검증)
- 테스트 데이터: 실제 `Interview`/`EvaluationReport` ORM 클래스 인스턴스를
  세션 없이(unbound) 직접 생성 — `rubric_template_id=None`으로 두어
  `_build_rubric_out`이 DB 조회 없이 조기 반환하는 경로를 이용(부작용 없음)
- 전제 조건: 콘솔 출력이 cp949로 한글을 깨뜨리는 이 프로젝트의 알려진 문제
  (여러 세션에서 반복 확인된 red herring)를 피하기 위해 `PYTHONIOENCODING=utf-8`
  로 실행하고 결과를 UTF-8 파일로 저장 후 `Read` 도구로 재확인

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 유출 마커 포함 원문 → 안내 문구로 치환 | `summary_text`에 `_PERSONA_LEAK_MARKERS` 중 하나("시니어 기술 면접관") 포함 | `_report_to_out(interview, report_with_leak, db=None)` 호출 | `summary_text`가 `_REPORT_SUMMARY_FALLBACK_NOTICE`로 치환됨 | 정확히 일치(assert 통과), 감사 로그("시스템 프롬프트 유출 의심 출력 차단(REQ-039)") 실제 출력 확인 | PASS | |
| TC-002 | 유출 마커 없는 정상 폴백 텍스트 → 원문 그대로 보존(회귀 없음) | `summary_text`="지원자는 전반적으로 우수한 답변을 했습니다." | 위와 동일 함수 호출 | 원문 그대로 반환 | 원문과 완전 일치 확인 | PASS | 기존 §4.4 폴백 취지(정보 없는 것보다 낫다) 유지 확인 |
| TC-003 | report 자체가 없음(리포트 미생성 상태) | `report=None` | `_report_to_out(interview, None, db=None)` | `summary_text=None`, 예외 없음 | `None` 확인, 예외 없음 | PASS | 기존 분기 무변경 회귀 확인 |
| TC-004 | recruiter 경로 중복 구현 여부 | `recruiter.py` 소스 | import 확인 | `_report_to_out`을 그대로 import해 재사용(자체 유출 검사 로직 중복 작성 없음) | `from app.api.v1.interviews import _report_to_out` 확인 — 별도 로직 없음 | PASS | 수정 1곳으로 양쪽 화면 모두 커버됨을 코드 근거로 확인 |
| TC-005 | 정적 검증 — import/순환참조 | 수정된 `interviews.py` | `python -c "from app.api.v1 import interviews"` | 정상 import | `IMPORT_OK` | PASS | `interview_prompts.py`는 `app.models.question`만 import해 순환참조 없음 사전 확인 |
| TC-006 | 린트 | 수정된 `interviews.py` | `ruff check` | 오류 0건 | `All checks passed!` | PASS | |

## 5. 커버리지
- 커버리지 지표: 신규 분기(if문 1개) 100% — TC-001(참 경로)/TC-002(거짓 경로) 양쪽 모두 실행·검증
- 커버되지 않은 부분과 사유: 실제 LLM이 파싱 실패를 일으키며 동시에 유출
  마커를 포함한 원문을 생성하는 전체 E2E 경로는 이번 범위에서 재현하지 않음
  (원문 생성 자체는 unit-27/DEC-077이 이미 다른 각도로 실측 검증한 LLM 동작
  영역이라 중복 검증 불필요로 판단, 이번 수정은 "그 원문을 어떻게 안전하게
  보여줄지"에 대한 서버측 후처리 로직만 다룸)

## 6. 결함(Defect) 목록
- 결함 없음 — TC-001~006 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `scratchpad/def003_test_result.txt`(세션
  스크래치패드, 프로젝트 저장소 밖) — 프로젝트 `.harness-tmp/`에는 아무것도
  생성하지 않음(함수 직접 호출 검증이라 DB/서버/venv 불필요)
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시
  아티팩트 자체를 생성하지 않음)
- 정리 완료 여부: 정리 대상 없음(저장소 내 생성물 없음)
- 정리 후 `git status`: 코드 3파일(`interviews.py`, `decisions.md`,
  `traceability.md`, `unit-10-test.md`) 변경분만 존재, `.harness-tmp/` 관련
  항목 없음
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- 이 수정은 "유출 마커 포함" 케이스만 방어한다 — 마커에 없는 새로운 형태의
  유출(예: 마커 목록에 없는 다른 시스템 프롬프트 문구)은 여전히 그대로 노출될
  수 있다. `_PERSONA_LEAK_MARKERS`는 unit-27이 실측 관찰한 표본 기반이라
  완전한 목록이 아님 — 09단계 보안검증에서 추가 표본 확보 시 목록 보강 권장.
- 여전히 미해결(별도 후속 항목, 이번 범위 아님): unit-10 DEF-001(입력 길이
  상한 없음), DEF-002(워커 크래시 시 `queued` 영구 고착) — "나머지 6개 후보"
  중 #2/#3에 해당, 사용자 승인 시 별도 진행.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료)

## 10. 내부 검증
- L1 경량판(Low Tier) — 1차 검증(작성자 관점): TC-001~006 실행 로그와 본
  문서 대조, 결함 0건. 규칙 B Tier=Low 예외에 따라 2차 생략. 단, §8의 유출
  마커 목록 완전성 한계는 2차 없이도 명시적으로 남김(생략이 리스크 은폐가
  되지 않도록).
