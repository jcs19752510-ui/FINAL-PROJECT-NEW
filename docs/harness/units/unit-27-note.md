# unit-27 구현 노트 — AI 안전장치 5종(REQ-035~039)

- 작성 에이전트: 본 세션(05+06 역할 겸임), 작성일: 2026-09-22
- `docs/harness/traceability.md`가 unit-8(미착수)에 배정해뒀던 5개 요구사항 —
  원 계획서에는 없고 하네스 자체 보안 규칙(규칙 J)이 요구하는 항목.

## 1. 이미 충족되어 재구현하지 않은 항목 (실측 확인)

- **REQ-036(출력 새니타이즈, XSS 방지)**: `frontend/app/interviews/[id]/page.tsx`,
  `.../report/page.tsx` 전체를 grep해 `dangerouslySetInnerHTML` 실사용이 없음을
  확인(주석 속 언급만 있었음). React JSX 텍스트 보간이 모든 텍스트 노드를
  자동 이스케이프하므로 이미 충족.
- **REQ-037(함수 호출 최소 권한)**: `llm_engine.TurnLLMOutput.control`이
  `Literal["next_question","end_interview","switch_to_coding","none"]`로 선언돼
  화이트리스트 밖 값은 pydantic이 스키마 검증 단계에서 자동 거부 — 이미 충족.

## 2. 새로 구현한 항목

- `backend/app/services/prompt_safety.py`(신규):
  - REQ-035: `detect_injection_attempt()` — 정규식 기반 1차 인젝션 시도 탐지
    (한/영 패턴). **차단하지 않고 감사 로그만 남긴다** — 오탐으로 정상 답변을
    막지 않기 위함(핵심 방어는 이미 `llm_engine._call_chat_completions`의
    role 분리가 담당).
  - REQ-038: `check_and_increment_turn_rate_limit()` — Redis INCR+EXPIRE 고정
    윈도우, 분당 10회. **키를 `user_id`로 선택**(아래 3절 "실측으로 발견한
    설계 재검토" 참고).
  - REQ-039: `log_persona_leak_detected()` — 실제 탐지는 기존
    `interview_prompts.validate_followup_speak_text()`가 이미 수행, 이 유닛은
    그 결과 중 "시스템 프롬프트 유출 마커 포함"에 해당하는 경우만 감사 로그를
    남기도록 `interview_prompts.contains_persona_leak_marker()`(기존 내부 로직
    분리·노출)와 `worker/tasks.py._generate_validated_followup()`(interview_id
    파라미터 추가)를 연결.
- `backend/app/api/v1/interviews.py`: 레이트리밋 체크를 텍스트/음성 턴 제출
  양쪽의 **맨 앞부분**(무거운 작업 시작 전)에 추가. 인젝션 탐지 로그도 함께.

## 3. 실측으로 발견한 설계 재검토 — 레이트리밋 키를 interview_id에서 user_id로

최초 설계는 `interview_id` 단위 카운터였으나, 실제 HTTP로 검증하는 과정에서
`app/api/v1/interviews.py`에 이미 있던 별개 규칙(`MAX_CANDIDATE_TURNS=5`,
2026-09-21 사용자 요청, "인터뷰 세션당 지원자 턴 최대 5회")이 항상 먼저 걸려
분당 10회 레이트리밋이 **절대 발동하지 않음**을 실측으로 확인했다. `user_id`
단위로 바꿔 "세션을 계속 새로 만들어 5턴씩 우회 반복"하는 실제 공격 패턴을
막을 수 있게 재설계했다(`prompt_safety.py` 모듈 내 주석에 근거 기록).

## 4. 테스트 중 겪은 방법론적 함정(버그 아님, 기록 목적)

레이트리밋을 HTTP E2E로 처음 검증할 때, 매 반복마다 디버그용 Redis 조회(curl+
python 프로세스 기동)를 끼워 넣었더니 그 오버헤드만으로 60초 윈도우가 8회
만에 만료돼 "레이트리밋이 작동하지 않는다"는 **잘못된 결론**에 도달할 뻔했다.
디버그 오버헤드를 제거한 빠른 루프로 재검증해 정확히 10회 통과/11회차부터
429로 차단됨을 확인했다(unit-27-test.md TC 참고) — 테스트 방법론 자체가
결과를 왜곡할 수 있다는 근거 있는 사례로 남긴다.

## 5. 범위 밖 (인수인계)

- 레이트리밋 윈도우(분당 10회)와 "일일 상한"(원안 §6.3 "세션당/일일 상한" 중
  일일 부분)은 이번 유닛에서 다루지 않음 — 필요 시 별도 일 단위 카운터 추가.
- REQ-039의 "n-gram 유사도 검사"(원 설계 §6.3 표현)는 마커 기반 정확매칭으로
  구현했다 — 진짜 n-gram 유사도(예: Jaccard)는 과설계로 판단해 보류.
