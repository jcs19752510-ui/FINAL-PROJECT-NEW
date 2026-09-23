# 테스트 결과서 (Test Result Report) — unit-23

## 1. 개요
- 테스트 대상: 모듈/기능 — 원안(REQ-F-006/007) "합격/불합격 추천 의견" 필드 복원
  (`EvaluationReport.pass_fail_recommendation` 및 이를 소비하는 전 계층: 모델→
  마이그레이션→LLM 구조화출력→워커 저장→API 응답→프론트 표시)
- 테스트 유형: 단위+통합 병합(Low 등급 전용 — 이 유닛은 기존 EVALUATION_REPORTS
  파이프라인에 nullable 필드 1개를 additive로 얹는 작업으로, 작업 단위 1개·영향
  범위가 명확해 별도 07단계 없이 이 보고서 1건으로 단위+데이터흐름 케이스를 모두 커버)
- 적용 Tier: Low (신규 REQ 번호 미부여, 기존 REQ-009/010/012 파이프라인에 대한
  additive 확장이며 스키마 자체를 깨지 않음 — 단, ④절 리스크에 명시하듯 컴플라이언스
  관점에서는 Low로 단정하지 않고 09단계 재검토를 명시적으로 요구함)
- 적용 속도 트랙: L1(경량판) — 사용자가 "내부테스트 결과서 완벽하게 작성"을 명시
  요구해 L1이지만 4절 케이스를 표준 수준으로 채움(과설계 아님, 명시적 요구 반영)
- 테스트 목적: (1) 신규 필드가 모델→DB→API 전 계층에서 실제로 동작하는지 실측
  확인, (2) 기존 REQ-031 메커니즘(overall_recommendation 3단계)이 이 변경으로
  손상되지 않았는지 확인, (3) null 케이스·화이트리스트 밖 값 거부 등 경계 확인
- 관련 산출물: `unit-23-note.md`, 원 계획서 §3.1.3(REQ-F-006/007), `docs/harness/
  traceability.md` REQ-031 행
- 테스트 수행자(에이전트): 본 세션(05+06 역할 겸임)
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 모델 컬럼/enum, Alembic 마이그레이션(upgrade+downgrade), LLM
  구조화출력 스키마 검증, 워커 매핑 로직, `GET /interviews/{id}/report`(지원자),
  `GET /recruiter/reports/{id}`(채용담당자) 실제 HTTP 응답, null 케이스, 프론트
  타입/렌더링 코드 리뷰
- 제외 범위 및 사유: (1) 실제 GPU LLM(`llama-server`)을 통한 end-to-end 리포트
  생성 — 워커 매핑 로직 자체는 결정론적 순수 함수라 직접 호출로 동등 검증했고(TC-006),
  GPU 파이프라인 기동(수 분+)은 이 작은 additive 변경 대비 과도함. (2) 프론트
  브라우저 실제 렌더링 — 이 환경에 브라우저 자동화 도구 없음(unit-4 이래 반복된
  환경 제약과 동일), 코드 리뷰(TSX 문법/타입 정합)로 대체.

## 3. 테스트 환경
- 실행 환경: Windows, Python 3.13(`backend/.venv`), FastAPI(uvicorn, 신규 포트
  8301), PostgreSQL(Docker `final-project-db`, 5544 — 기존 개발 DB를 그대로 사용,
  격리 venv/DB 신설 없음), curl
- 테스트 데이터: 신규 격리 계정 2개(`unit22-cand@example.com`, `unit22-
  recruiter@example.com`) + 신규 interview 2건 + evaluation_report 2건(모두 테스트
  종료 후 삭제, 7절 참고)
- 전제 조건: `docker ps`로 `final-project-db`(5544), `final-project-redis`(6389)
  기동 확인 완료. 기존 데이터(다른 세션이 만든 것으로 보이는 `live` 상태 interview
  1건 등)는 건드리지 않음(격리 원칙).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | Python 문법/타입 정합 | 편집 완료 | `py_compile` 8개 파일 + `ruff check` | 오류 0건(단, 무관한 기존 부채 제외) | `PY_COMPILE_OK`, ruff 7/8 파일 clean, 1개(`interviews.py`)는 내가 만들지 않은 기존 import-순서 부채(git diff로 확인, 내 변경은 3줄 추가뿐) | PASS | |
| TC-002 | Alembic upgrade 최초 실행 | DB가 v10(`9c91a685f9df`)에 있음 | `alembic upgrade head` | 성공 | **최초 실패**: `type "pass_fail_recommendation" does not exist`(DEF-001) → 마이그레이션에 `ENUM.create()` 추가 후 재실행 → 성공 | PASS(수정 후) | 트랜잭션 롤백으로 DB는 실패 시점에도 깨지지 않고 v10 유지됨을 `alembic current`로 재확인 |
| TC-003 | ORM insert(정상값) | TC-002 통과, DB가 v11(head) | `EvaluationReport(pass_fail_recommendation=PassFailRecommendation.pass_, ...)` 후 commit | 성공, DB에 `"pass"` 저장 | **최초 실패**: `invalid input value for enum ...: "pass_"`(DEF-002, enum 멤버명≠값 문제) → `values_callable` 추가 후 재실행 → 성공. 원시 SQL로 `pass_fail_recommendation` 컬럼 직접 조회해 `'pass'` 저장 확인 | PASS(수정 후) | |
| TC-004 | Alembic downgrade | DB가 head(`a7c3e9f14b02`) | `alembic downgrade -1` | 컬럼+타입 깨끗이 제거, 오류 없음 | 성공, `alembic current`로 `9c91a685f9df` 복귀 확인 | PASS | 이후 `upgrade head`로 재적용해 최종 상태를 head로 정리 |
| TC-005 | `GET /interviews/{id}/report`(지원자, 정상값) | 신규 uvicorn(8301), 신규 지원자 계정+report(pass_fail=`pass`) | 로그인 → report GET | 응답에 `"pass_fail_recommendation":"pass"` + `disclaimer` 동시 포함 | 정확히 일치 확인(curl 원문 응답 기록됨) | PASS | |
| TC-006 | `GET /recruiter/reports/{id}`(채용담당자, 정상값) | 신규 recruiter 계정, 동일 interview | 로그인 → report-detail GET | 동일 필드 포함 | 정확히 일치 확인 | PASS | |
| TC-007 | null 케이스 | 별도 interview, `pass_fail_recommendation=None`으로 report 생성 | 지원자 GET | 응답에 `"pass_fail_recommendation":null`, 크래시 없음 | 정확히 일치 확인 | PASS | overall_recommendation은 `"neutral"`로 정상 별도 표시 — 기존 REQ-031 메커니즘 손상 없음 확인 |
| TC-008 | 워커 매핑 로직(pass/fail/borderline/None 4종) | — | `PassFailRecommendation(v) if v else None` 직접 호출 | 4종 모두 올바른 enum/None 반환 | 4종 전부 일치 | PASS | 전체 GPU LLM 파이프라인 기동 없이 결정론적 매핑 함수만 격리 검증(2절 제외범위 사유) |
| TC-009 | `ReportLLMOutput` 화이트리스트 강제(REQ-037 방향 정합) | — | `pass_fail_recommendation` 필드에 `"accepted_definitely"`(화이트리스트 밖) 전달 | `pydantic.ValidationError` 발생 | 정확히 거부됨 확인 | PASS | `pass`/`fail`/`borderline`/생략(None) 4종은 모두 정상 통과 확인(같은 케이스에 포함) |

> 경계값/예외입력(TC-007/009), 권한 경계(TC-005/006가 각 역할 토큰으로 실행돼 최소
> 권한 경로 재확인 포함)를 포함했다. 동시성/부하 케이스는 이 additive 필드 변경의
> 성격상 해당 없음(신규 동시성 경로를 추가하지 않음).

## 5. 커버리지
- L1 경량판 — 미해당(템플릿 5절 지침에 따름). 단, 위 4절이 신규 코드 경로(모델/
  마이그레이션/LLM스키마/워커/API 응답 2종/null케이스/화이트리스트 거부)를 전량
  실제 실행으로 커버함을 기록.
- 커버되지 않은 부분: 프론트 실제 브라우저 렌더링(3절 제외범위 사유와 동일), 실제
  GPU LLM이 `pass_fail_recommendation`을 자연스럽게 생성하는지(모델의 실제 출력
  경향 — TC-008/009는 파싱·검증 로직만 확인, 모델이 이 필드를 얼마나 정확히/
  일관되게 채우는지는 실제 운영 트래픽에서 관찰 필요).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | `op.add_column`이 종속 ENUM 타입 자동 생성 안 함 → `alembic upgrade head` 실패 | `alembic upgrade head`(수정 전 마이그레이션 파일로) | High | Fixed | `postgresql.ENUM(...).create(bind, checkfirst=True)`를 `add_column` 앞에 명시 호출(`downgrade`에도 대칭적으로 `.drop()` 추가) |
| DEF-002 | SQLAlchemy `Enum(PythonEnum)` 기본 동작이 멤버 이름(`pass_`)을 저장하려 해 DB enum 라벨(`pass`)과 불일치 | ORM으로 `pass_fail_recommendation=PassFailRecommendation.pass_` 저장 시도 | High | Fixed | 컬럼 정의에 `values_callable=lambda enum_cls: [m.value for m in enum_cls]` 추가 |

- 위 2건 모두 Fixed 확정. 그 외 결함 없음 — 근거: TC-001~009 전건 PASS(수정 반영판
  기준), null/화이트리스트 경계 케이스 포함.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/unit22_uvicorn.log`
  (신규 uvicorn 프로세스 표준출력 리다이렉트, 삭제 완료), DB 임시 행(사용자 2·
  interview 2·evaluation_report 2, 전량 삭제 완료), 신규 uvicorn 프로세스(PID
  23480, `taskkill`로 종료 확인 — `curl`이 연결 거부로 응답 없음 확인)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예
- 정리(삭제) 완료 여부: 완료(로그 파일 삭제, DB 테스트 행 전량 삭제 확인 — 삭제
  쿼리 결과 `reports=2 interviews=2 users=2`, 프로세스 종료 확인)
- 정리 후 `git status` 실행 결과(그대로 첨부): 이 저장소에는 **작업 디렉터리를
  감시해 자동 커밋하는 외부 워처**가 동작 중임을 이번 테스트 도중 발견함(커밋
  `a182388`, 작성자 정찬성, 메시지 "파이널 프로젝트 신규 프로그램" — 이 세션이
  `git add`/`git commit`을 실행한 적은 없음). 그 결과 이 유닛의 코드 변경 대부분이
  이미 자동 커밋되어 있었고, `git status` 확인 시점에는 가장 마지막에 고친 2개
  파일(`backend/alembic/versions/a7c3e9f14b02_...py`, `backend/app/models/
  evaluation_report.py` — DEF-002 수정분)만 "modified"로 남아 있었다. 사용자에게
  별도로 보고함(이 세션이 임의로 커밋을 만들거나 되돌리지 않았음).
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음

## 8. 리스크 및 잔존 이슈
- **컴플라이언스 리스크(최우선)**: 이 필드는 REQ-031(개인정보 보호법 제37조의2)이
  원래 "만들지 않는다"고 명시했던 종류의 값이다. 기술 구현은 완료·검증됐으나 법적
  리스크 자체는 이 테스트로 해소되지 않는다 — 배포 전 법무 검토 필수, 09단계
  보안/컴플라이언스 감사에서 재검토 필수.
- LLM이 실제 운영에서 `pass_fail_recommendation`을 얼마나 신뢰성 있게 채우는지는
  실측하지 않음(5절 참고) — unit-7이 겪었던 "구조화 출력 품질" 이슈(질문형 검증
  실패→재시도→폴백 패턴)가 이 필드에도 재현될 가능성 있음, 운영 관찰 필요.
- traceability.md 미갱신(신규 REQ 번호 부여는 사용자/거버넌스 판단 필요, 규칙A로
  임의 진행 안 함).
- 저장소 자동 커밋 워처의 존재 자체(리스크는 아니나 사용자가 인지해야 할 운영
  특성 — 미완성/버그 있는 중간 상태도 커밋될 수 있음을 이번에 실측함, DEF-001이
  담긴 최초 마이그레이션 파일이 실제로 그 상태로 한 차례 커밋됐다).

## 9. 결론 및 판정
- [x] PASS — 다음 단계(나머지 "가능" 14개 항목 순차 진행) 진행 가능 (7절 Teardown
  확인 완료)

## 10. 내부 검증 (최소 2회)
- L1 경량판 — 검증 생략(템플릿 10절 지침에 따름). 단, DEF-001/002는 "수정 전 실패
  실측 → 수정 → 재실행 성공 실측"의 2회 이상 실측 사이클을 실제로 거쳤음(4절
  TC-002/003 "실제 결과" 란 참고 — 이는 형식적 2차 검증은 아니나 동일한 실측
  엄격성을 충족).
