# unit-23 구현 노트 — 원안(REQ-F-006/007) "합격/불합격 추천 의견" 필드 복원

- 작성 에이전트: 본 세션(claude, 05+06 역할 겸임), 작성일: 2026-09-22
- 배경: 사용자가 "웹 AI 모의면접 프로젝트 계획서.pdf"(원 계획서) §3.1.3(REQ-F-006/007
  "합격/불합격 추천 의견")과 현재 구현(`docs/harness/traceability.md` REQ-031, §3.2
  "합격/불합격 확정 필드는 스키마에 만들지 않는다")의 불일치를 지적하고, **법적
  리스크(개인정보 보호법 제37조의2, 자동화된 결정 거부권)를 명시적으로 인지한 상태로
  복원을 승인**함(대화 기록 기준 결정, 정식 DEC 번호 미부여 — 09단계 보안/컴플라이언스
  감사에서 재검토 필요).
- REQ-ID: REQ-031과 긴장 관계(신규 REQ 번호 미부여, traceability.md는 이번 유닛
  범위에서 갱신하지 않음 — 09단계 감사 후 정식 반영 여부 판단 필요).

## 1. 구현 범위

- `backend/app/models/evaluation_report.py`: `PassFailRecommendation` StrEnum(`pass`/
  `fail`/`borderline`) 신설 + `EvaluationReport.pass_fail_recommendation` nullable
  컬럼 추가. `overall_recommendation`(기존 3단계 권고, REQ-031 방어선)은 유지·삭제하지
  않음 — 신규 필드는 **추가**일 뿐 REQ-031 메커니즘을 대체하지 않는다.
- `backend/alembic/versions/a7c3e9f14b02_v11_pass_fail_recommendation.py`: 신규
  마이그레이션. `postgresql.ENUM(...).create()`을 `add_column` 이전에 명시적으로
  호출(아래 2절 결함 DEF-001 참고).
- `backend/app/services/llm_engine.py`: `ReportLLMOutput.pass_fail_recommendation`
  optional 필드 추가(`Literal["pass","fail","borderline"] | None = None`) — 모델이
  생략해도 리포트 자체는 깨지지 않음.
- `backend/app/services/interview_prompts.py`: `_REPORT_PERSONA`에 필드 설명 추가,
  "참고용 의견일 뿐 확정 판정이 아니다. 애매하면 borderline" 지시 포함.
- `backend/app/worker/tasks.py`: `_save_evaluation_report`에 파라미터 추가, LLM
  출력값을 `PassFailRecommendation`으로 매핑해 저장.
- `backend/app/schemas/interview.py`(`ReportOut`), `backend/app/api/v1/interviews.py`
  (`_report_to_out`), `backend/app/schemas/recruiter.py`/`api/v1/recruiter.py`(recruiter
  경로)에 필드 노출 추가 — 모두 기존 `REPORT_DISCLAIMER`("최종 채용 결정은 인간이
  내립니다")와 같은 응답에만 포함되도록 유지.
- `frontend/app/interviews/[id]/report/page.tsx`, `frontend/lib/api.ts`: 타입 추가 +
  "⚠ 참고용 합격/불합격 의견" 배지 렌더링(경고 톤 스타일, disclaimer 문구 근접 배치).

## 2. 실측으로 발견한 결함 (구현 중 자체 발견·수정)

| ID | 설명 | 재현 | 심각도 | 상태 |
|---|---|---|---|---|
| DEF-001 | `op.add_column`이 종속 ENUM 타입을 자동 생성하지 않아 `alembic upgrade head` 시 `psycopg.errors.UndefinedObject: type "pass_fail_recommendation" does not exist` 실제 발생 | 최초 마이그레이션 작성본으로 `alembic upgrade head` 직접 실행 | High(마이그레이션 자체가 실패) | Fixed — `postgresql.ENUM(...).create(bind, checkfirst=True)`를 `add_column` 앞에 명시 호출 |
| DEF-002 | SQLAlchemy `Enum(PythonEnum)`이 기본적으로 멤버 **이름**을 DB에 저장 — `pass_`(파이썬 예약어 회피용 멤버명) ≠ `"pass"`(값)라 `INSERT` 시 `psycopg.errors.InvalidTextRepresentation: invalid input value for enum pass_fail_recommendation: "pass_"` 실제 발생 | ORM으로 `EvaluationReport(pass_fail_recommendation=PassFailRecommendation.pass_, ...)` 생성 후 `commit()` | High(모델 자체 저장 불가) | Fixed — 컬럼 정의에 `values_callable=lambda enum_cls: [m.value for m in enum_cls]` 추가 |

두 결함 모두 "실제로 실행해서 재현 → 원인 파악 → 수정 → 재실행으로 통과 확인"까지
마쳤다(아래 unit-23-test.md TC-002/TC-003). 코드 리뷰만으로는 발견되지 않았을
결함으로, 실제 DB 마이그레이션 실행이 왜 필요한지 보여주는 사례.

## 3. 범위 밖으로 남긴 것 (인수인계)

- **법무 검토**: 이 필드 자체가 REQ-031의 원래 설계 결정과 충돌한다. 배포 전 반드시
  법무 검토가 선행되어야 하며, 이 유닛은 "사용자가 리스크를 인지하고 명시적으로
  승인한 기술 구현"일 뿐 법적 리스크를 해소한 것이 아니다.
- **09단계 보안/컴플라이언스 감사** 시 이 유닛을 반드시 재검토 대상으로 포함해야 함.
- `traceability.md` 갱신은 하지 않았다(신규 REQ 번호 부여 여부가 사용자/거버넌스
  판단 사항이라 임의로 추가하지 않음, 규칙 A).
- 나머지 "가능" 판정 14개 항목(STT 스트리밍/LangChain/Prosody/TLS+AES/AI안전장치
  5종/WebRTC 등)은 이 유닛 범위 밖 — 순차 진행 예정.
