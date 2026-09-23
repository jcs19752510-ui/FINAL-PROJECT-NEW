# 테스트 결과서 (Test Result Report) — unit-11 (REQ-010 루브릭 스코어링 · REQ-012 평가 근거) · 소급 정적 검토판

## 1. 개요
- 테스트 대상: 모듈(작업단위) unit-11. 리포트의 점수 산출·저장·표시(`ReportLLMOutput` 점수 필드, `tasks.py` 종합 점수, `EVALUATION_REPORTS.*_score`/`details_json`, `ReportOut`, 지원자·채용담당자 리포트 화면)와 루브릭 템플릿(`RUBRIC_TEMPLATES`, `INTERVIEWS.rubric_template_id`)의 연결
- 테스트 유형: 단위
- 적용 Tier: High(DEC-002)
- 적용 속도 트랙: L3(DEC-031)
- 테스트 목적: 하네스 절차 없이 구현된 REQ-010/012 코드(unit-11-note.md §0)가 기획서(02 §4.2 68·69행), 설계서(03 §3·§4.4), 디자인서(04 [C-11]·`RubricEvidenceAccordion`)를 충족하는지 확인한다.
- 관련 산출물: `docs/harness/units/unit-11-note.md`, `unit-10-note.md`, 02-planning.md §4.2, 03-system-design.md §3·§4.4, 04-ux-design.md [C-11]/[R-02]/[R-03], `decisions.md` DEC-031/053/054
- 테스트 수행자(에이전트): 본 세션(오케스트레이터, 06 역할)
- 테스트 일시: 2026-09-23

> **이 결과서의 한계:** unit-10-test.md 1절과 같다. 이번 PC에서는 실행할 수 없어 새 케이스는 모두 정적 검토이고, "실행 결과"는 기존 개발 서버 실측을 인용한 것이다(DEC-053).

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope):
  - REQ-010: 1~5점 범위 강제, 종합 점수 계산, 저장·반환·표시, **사전 정의 루브릭 템플릿 기반 여부**
  - REQ-012: 평가 근거 생성·저장·반환·**화면 노출**, "답변 구간 ↔ 루브릭" 대응 표시
  - 경계: 점수 null(파싱 실패 폴백) 시 표시
- 제외 범위 및 사유:
  - 실제 실행: 환경 부재(DEC-053). 실측 절차는 8절.
  - 리포트 생성 흐름 자체(상태 전이 등): unit-10 범위
  - 루브릭 템플릿 CRUD(REQ-014): unit-13에서 PASS. 여기서는 "채점에 쓰이는가"만 본다.

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro. 코드 읽기와 grep만 사용.
- 검토 기준 코드: `PROD` HEAD `05f8d1a`
- 인용한 기존 실측: `bugfix-20260922-event-loop-hang-test.md` TC-H04/H05(개발 서버), `unit-23-test.md` TC-009
- 전제 조건: 없음

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 점수 범위 1~5 강제(경계값) | 코드 HEAD | `ReportLLMOutput` 읽기 | 0·6 등 범위 밖 값은 검증 실패 | `Field(ge=1, le=5)` 3축 모두 적용 | Pass(정적) | 범위 밖 → 파싱 실패 → 폴백(unit-10 TC-005) |
| TC-002 | 종합 점수 계산 | 〃 | `tasks.py` 종합 점수 식 읽기 | 3축 평균 → `INTERVIEWS.overall_score` | `round((t+c+f)/3, 1)`, 파싱 실패 시 null | Pass(정적) | |
| TC-003 | 점수 저장·API 반환 | 〃 | `_save_evaluation_report`, `_report_to_out` 읽기 | 3축 + 종합이 응답에 포함 | 일치 | Pass(정적) | |
| TC-004 | 점수 표시(지원자·채용담당자) | 〃 | `report/page.tsx` "세부 점수", `recruiter/[id]/page.tsx` 읽기 | 3축 점수 표시, null이면 숨김 또는 "-" | 일치(04의 "게이지" 대신 숫자 행) | Pass(정적) | 시각 형식 차이는 결함으로 보지 않음 |
| TC-005 | 정상 경로 점수 생성 | 기존 개발 서버 | **인용**: TC-H04 | 점수 생성·반환 | `overall_score=4.0`, 점수 반환 확인(2026-09-22) | Pass(인용) | 재실행 안 함 |
| TC-006 | **사전 정의 루브릭 템플릿 기반 채점**(REQ-010 핵심) | 코드 HEAD | `grep -rni rubric backend/app/worker backend/app/services/interview_prompts.py backend/app/services/llm_engine.py`, `grep -rn rubric_template_id backend/app` | 리포트 생성이 면접에 연결된 템플릿의 `criteria_json`을 읽어 채점 기준으로 사용 | 리포트 경로에서 루브릭 참조 0건(유일한 일치는 턴 스키마 `rubric_match` 필드 선언). `rubric_template_id`는 모델·스키마 선언뿐이고 읽는 곳 없음. **쓰는 곳도 없음** — `create_interview`는 `candidate_id/status/report_status`만 설정하고, 면접에 템플릿을 지정하는 API가 없어 값이 항상 null이다. 채점 축은 프롬프트 고정 3축 | **Fail(정적)** | DEF-001 |
| TC-007 | 평가 근거 저장·반환(REQ-012) | 〃 | 워커 `details_json` 저장, `ReportOut.details` 읽기 | 근거가 저장되어 응답에 포함 | 저장·반환 모두 있음 | Pass(정적) | |
| TC-008 | **평가 근거 화면 노출**(REQ-012 핵심) | 〃 | `grep -rn "\.details\b" frontend/app frontend/components` | [C-11]/[R-02]에 근거 영역(비었으면 "세부 근거 없음") | 렌더링 0건. `RubricEvidenceAccordion` 컴포넌트 없음 | **Fail(정적)** | DEF-002 |
| TC-009 | 근거의 "답변 구간 ↔ 루브릭" 대응 | 〃 | `_REPORT_PERSONA` 스키마 설명, `TurnLLMOutput` 저장 여부 읽기 | 구간별 적용 루브릭을 식별할 수 있는 구조 | `details`는 자유형 object(구간 지정 요구 없음). 턴마다 나오는 `rubric_match`/`key_observations`/턴 점수는 파싱 후 저장되지 않고 버려짐 | **Fail(정적)** | DEF-003 |
| TC-010 | 파싱 실패 시 점수 표시(경계) | 〃 | 폴백 경로 + 화면 조건부 렌더 읽기 | 점수 null이면 점수 영역 숨김, 종합 "-" | 일치(3축 모두 null이면 섹션 미표시, 종합 "-") | Pass(정적) | |
| TC-011 | 권한 경계 | — | unit-10 TC-004와 같은 함수를 공유 | — | unit-10 TC-004 참고 | Pass(정적) | 중복 방지를 위해 참조만 |

## 5. 커버리지
- 커버리지 지표: 기능 커버리지. REQ-010 요소 4개(범위·계산·저장/반환·표시) + 템플릿 기반 1개, REQ-012 요소 3개(저장/반환·화면·구간 대응) + 경계 1개. 라인/브랜치는 측정 불가(실행 환경 없음).
- 커버되지 않은 부분과 사유: 전 케이스의 실제 실행(DEC-053). LLM이 매긴 점수가 타당한지(평가 품질)는 단위 테스트로 판정할 수 없어 08 UAT 대상이다.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | REQ-010 "사전 정의 루브릭 템플릿 기반 채점"이 구현되지 않았다. 채점 축이 프롬프트에 고정된 3축이고, 채용담당자 템플릿(REQ-014)과 `INTERVIEWS.rubric_template_id`가 채점에 쓰이지 않는다. **면접에 템플릿을 지정하는 경로 자체도 없다**(생성 시 항상 null). 03 설계서는 ERD FK(§3)와 템플릿 구조(04 [R-03]: 항목명+가중치/설명)만 정의하고, "누가 면접에 템플릿을 지정하는지"와 "채점에 어떻게 반영하는지"를 모두 정의하지 않았다. 그래서 **근본 원인은 3단계 설계 공백일 수 있다**(규칙 F) | TC-006의 grep 2개 | High | Open | 수정 안 함 — 해석이 여러 가지라 규칙 A 질문 대상(DEC-054) |
| DEF-002 | REQ-012 평가 근거가 화면에 전혀 보이지 않는다(API는 반환함). 04 디자인서 `RubricEvidenceAccordion` 미구현 | TC-008의 grep | High | Open | 수정 안 함(DEC-053 범위). DEF-001 방향이 정해진 뒤 함께 구현하는 것이 합리적 — 근거의 형태가 템플릿 구조에 달려 있음 |
| DEF-003 | 근거가 자유형이라 "어떤 답변 구간에 어떤 루브릭" 대응을 보장하지 않는다. 턴 단위 평가값(`rubric_match` 등, 03 §4.4 턴 계약)은 저장 없이 버려진다 | TC-009 코드 읽기 | Medium | Open | DEF-001/002와 묶어 설계 결정 필요 |

- 관찰(결함 아님, unit-23 범위): 채용담당자 상세 화면이 `pass_fail_recommendation`을 표시하지 않는다(API는 반환). unit-23 후속 과제로 기록한다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: **해당 없음** — 정적 검토만 했고 venv, DB, 프로세스를 만들지 않았다.
- `.harness-tmp/` 하위에서만 생성했는가: [x] 예(생성물 없음) / [ ] 아니오
- 정리(삭제) 완료 여부: 대상 없음
- 정리 후 `git status` 실행 결과(2026-09-23, 모든 문서 작성 후 실제 실행한 `git status --short` 원문):
```
 M docs/harness/decisions.md
 M docs/harness/traceability.md
?? docs/harness/units/unit-10-note.md
?? docs/harness/units/unit-10-test.md
?? docs/harness/units/unit-11-note.md
?? docs/harness/units/unit-11-test.md
?? docs/harness/verify-log_unit-10-test.md
?? docs/harness/verify-log_unit-11-test.md
```
(이번 작업 산출물뿐이고 코드 변경은 없다. `.harness-tmp/`는 존재하지 않음)
- 강제 중단이 있었는가: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크: 정적 검토의 오독 가능성. LLM 점수의 일관성(같은 대화 → 같은 점수?)과 타당성은 미평가.
- 후속 조치가 필요한 항목:
  1. **사용자 결정(규칙 A, DEC-054):** 두 가지를 정해야 한다.
     - 지정 주체: 면접에 템플릿을 누가 지정하는가(지원자가 면접 생성 시 선택 / 채용담당자가 초대·배정 / 시스템 기본 템플릿 자동 적용)
     - 채점 반영 방식: 예시 선택지
       - (a) 템플릿 기준을 리포트 프롬프트에 주입하고 기존 3축은 유지
       - (b) 점수 축 자체를 템플릿 기준으로 동적 구성(DB 스키마·화면 변경 큼)
       - (c) 현행 고정 3축을 "시스템 기본 루브릭"으로 설계서에 명문화하고 REQ-010 문구를 조정
  2. 결정 후 규칙 F: 03 §4.4(와 필요 시 04 [C-11]) 수정 → 05 → 06 재실행
  3. 개발 서버 실측 절차: unit-10-test.md 8절 1번 흐름에 더해 (i) 응답의 점수가 1~5 범위이고 종합=평균인지, (ii) `details`가 반환되는지, (iii) 수정 후 템플릿을 바꿨을 때 채점 기준이 바뀌는지, (iv) 화면에 근거 영역이 보이는지(Playwright)
  4. 실행 후 규칙 K-6 헬스체크

## 9. 결론 및 판정
- [ ] PASS — 다음 단계 진행 가능
- [ ] CONDITIONAL PASS — 조건:
- [x] FAIL — 사유 및 재작업 요청 사항:
  1. Must 요건 REQ-010(템플릿 기반)과 REQ-012(근거 노출)의 핵심이 구현되지 않았다(DEF-001/002, High).
  2. 실행 검증이 없다(DEC-053).
  - 재작업은 사용자의 설계 결정(DEC-054) 뒤 규칙 F 순서로 진행한다.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약(작성자 관점): 결함 3건 발견·수정(v0→v1).
  - 7절 `git status`를 실제 출력 없이 요약
  - 10절 요약을 검증 전에 미리 적음
  - 관련 산출물에 04 [R-03] 누락
- 2차 검증 결과 요약(처음 받는 심사자 관점): 결함 1건 발견·수정(v1→v2). `rubric_template_id`를 "쓰는 곳도 없음"(면접에 템플릿을 지정하는 경로 부재)을 놓쳤고, 그래서 사용자 질문에 "지정 주체" 항목이 빠져 있었다. TC-006, DEF-001, 8절, unit-11-note.md를 수정했다.
- 3차 검증 결과 요약: 결함 0건, 최종.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-11-test.md`
