# unit-11 구현 노트 — 루브릭 기반 스코어링 + 평가 근거 노출 (REQ-010, REQ-012) · 소급 작성

- 작성: 2026-09-23, 본 세션(오케스트레이터가 05 역할로 **소급 문서화**, DEC-053)
- 대상 REQ:
  - REQ-010 [Must] 루브릭 기반 채용 적합도 스코어링(1~5점, **사전 정의 루브릭 템플릿**, 02-planning §4.2 표 68행)
  - REQ-012 [Must] 평가 근거 노출(**어떤 답변 구간에 어떤 루브릭이 적용됐는지** 최소 표시, 02-planning §4.2 표 69행)
- 속도 트랙: **L3**(DEC-031), Tier=High
- 입력: 03-system-design.md §3(EVALUATION_REPORTS 점수·`details_json`, RUBRIC_TEMPLATES, `INTERVIEWS.rubric_template_id` FK)·§4.4, 04-ux-design.md [C-11](점수 게이지, 평가 근거 아코디언)·§4 `RubricEvidenceAccordion`

## 0. 소급 사유

unit-10과 같다(unit-10-note.md §0). 점수·근거 필드는 리포트 생성 커밋 `18d5ceb`에 unit-10과 같이 들어갔다. 별도 unit-11 작업·노트·결과서는 없었다.

## 1. 구현된 것

| 항목 | 위치 | 상태 |
|---|---|---|
| 1~5점 3축 점수(기술/의사소통/조직적합) | `ReportLLMOutput`(`Field(ge=1, le=5)`), `EVALUATION_REPORTS.*_score` | 구현됨. 기존 개발 서버 실측: TC-H04에서 `overall_score=4.0` 생성 확인 |
| 종합 점수 | `tasks.py` — 3축 평균, 소수 1자리 → `INTERVIEWS.overall_score` | 구현됨 |
| 점수 표시 | 지원자 `report/page.tsx` "세부 점수" 3행, 채용담당자 `recruiter/[id]/page.tsx` | 구현됨(04의 "게이지"가 아니라 숫자 행 — 시각 표현 차이, 기능 동등) |
| 평가 근거 저장·API 반환 | `details_json`(LLM이 "점수 판단 근거 요약" 자유형 object를 작성) → `ReportOut.details` | 저장·반환은 됨 |

## 2. 구현되지 않았거나 설계와 다른 것 (결함 후보 → unit-11-test.md에 등록)

1. **루브릭 템플릿 미연결(REQ-010 핵심 요건).** 채점 축은 프롬프트(`interview_prompts._REPORT_PERSONA`)에 고정된 3축뿐이다.
   - 채용담당자가 만든 `RUBRIC_TEMPLATES.criteria_json`(REQ-014, unit-13)도, `INTERVIEWS.rubric_template_id`도 리포트 생성 경로에서 읽지 않는다. 확인 방법은 `backend/app/worker`와 `interview_prompts.py`의 `rubric` grep이고 결과는 0건이다.
   - **면접에 템플릿을 지정하는 경로 자체가 없다.** `create_interview`는 `candidate_id/status/report_status`만 설정하고, `rubric_template_id`를 쓰는 API가 없어 값이 항상 null이다. 설계서는 ERD FK(03 §3)와 템플릿 구조(04 [R-03])만 정의했고, 지정 주체와 채점 반영 방식은 정의하지 않았다.
   - 이미 `bugfix-20260922-ws-fallback-test.md` §8에 "루브릭 템플릿 미연결"이라고 언급됐지만, 결함으로 등록된 적은 없다.
   - 03 설계서 §4.4도 고정 3축 스키마만 정의하고 템플릿을 어떻게 연결할지는 정하지 않았다. 그래서 **근본 원인이 3단계 설계 공백일 수 있다**(규칙 F. 수정 방향은 사용자 결정 대기, DEC-054).
2. **평가 근거가 화면에 보이지 않는다(REQ-012 핵심 요건).** API는 `details`를 반환하지만 지원자·채용담당자 화면 어디에도 렌더링하지 않는다(`frontend/app`에서 `details` 렌더링 0건). 04 디자인서의 `RubricEvidenceAccordion`(내용이 비었을 때 "세부 근거 없음" 표시 포함)은 구현되지 않았다.
3. **근거 형식 미정, 턴 단위 근거는 버려짐.** `details_json`은 LLM이 쓰는 자유형 object라서 "어떤 답변 구간에 어떤 루브릭"이라는 대응 관계를 스키마로 보장하지 않는다(프롬프트에도 구간을 지정하라는 요구가 없다).
   - 03 설계서 §4.4의 **턴 처리** 출력 계약에는 턴마다 `technical_accuracy`/`communication_clarity`/`key_observations`/`rubric_match`가 있다. 이게 구간별 근거의 원천이 될 수 있었다.
   - 그런데 `TurnLLMOutput`은 이 값들을 파싱만 하고 어디에도 저장하지 않는다(`rubric_match`는 저장 코드 0건, `TRANSCRIPTS`에 해당 컬럼 없음). 리포트 생성 시 사용할 수도 없다.
4. (관찰) 채용담당자 상세 화면은 unit-23의 `pass_fail_recommendation`을 표시하지 않는다. API는 반환한다. 이건 unit-23 범위의 프런트 누락이라 이 유닛 결함으로 세지 않고 결과서 §8에 기록만 한다.

## 3. 06 인계 사항

- 06 결과서: `unit-11-test.md`(정적 검토 + 기존 실측 인용. 새 실측은 없음, DEC-053).
- 위 §2의 1·2는 Must 요건의 핵심을 충족하지 못하므로 **PASS 처리가 불가능하다.** 고치는 방향(템플릿 기준을 프롬프트에 주입할지, 점수 축 자체를 템플릿 기준으로 바꿀지 등)은 해석이 두 가지 이상이라 규칙 A 질문 대상이다.
