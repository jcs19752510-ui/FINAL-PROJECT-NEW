# 테스트 결과서 — unit-5 (Feature C. 대화형 인터뷰 엔진: 음성 턴제 STT 파이프라인 연동, REQ-004/REQ-005)

## 1. 개요
- 테스트 대상: `POST /interviews/{id}/turns`의 음성(multipart) 제출 경로(`_submit_voice_turn`), `backend/app/services/stt_engine.py`(faster-whisper 실제 변환), `biometric_voice` 동의 게이트(DEC-023)
- 테스트 유형: 단위
- 적용 Tier: (오케스트레이터 지정, 이 feature 전체가 L1 트랙으로 진행) — 프로젝트 위험도 등급 자체는 traceability.md/03-design 참고. 06 병합 조건(마지막 단위 + Low + 유닛 3개 이하)은 이 feature(Feature C, unit-4/5/6/7/8, 5개 이상)에 해당하지 않으므로 06·07 병합 대상 아님 — 이 결과서는 unit-5의 06단계(단위테스트) 단독 산출물이다.
- 적용 속도 트랙: **L1**(DEC-003) — 경량판. 정상 경로 1~2케이스 중심이나, 오케스트레이터 지시에 따라 DEC-023 동의 게이트(핵심 검증 대상)는 정상/거부/철회 3갈래를 모두 독립 재현했고, 5단계 note가 이미 실측한 예외 입력(422/504)·상태 충돌(409) 경로도 저비용으로 함께 재현했다(unit-2/3/4/9/12/17-test.md 선례와 동일하게 "저비용 추가 재현"으로 취급, 범위 임의 확대 아님 — 5단계 note §7 인수조건 5/6이 이미 명시한 항목).
- 테스트 목적: 5단계가 curl로 자체 검증한 결과를 그대로 승계하지 않고, 06단계가 독립된 프로세스·venv·서버 인스턴스로 처음부터 재현해 실제로 동작함을 증명한다. 특히 "생체정보(음성) 동의 게이트가 매 요청 재검사되어 철회 시 실제 차단되는가"(DEC-023)를 최우선으로 검증한다.
- 관련 산출물: `docs/harness/units/unit-5-note.md`(인수조건 §7), `docs/harness/03-system-design.md` §2.3/§4.2/§4.3/§6.2, `backend/app/services/stt_engine.py`, `backend/app/api/v1/interviews.py`, `docs/harness/traceability.md` REQ-004/REQ-005 행
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): unit-5-note.md §7 인수조건 1~6(음성 제출 동의게이트 403, 동의 후 실제 STT 저장, 텍스트/음성 turn_index 공유 회귀, 동의 철회 후 즉시 재차단(DEC-023 핵심), 예외 입력 422/504+미저장, scheduled/completed 409). 실제 faster-whisper 모델을 실제 오디오로 호출해 텍스트 변환이 일어나는지 실측.
- 제외 범위 및 사유:
  - 인수조건 7(브라우저 마이크 버튼/인라인 동의 팝업의 실제 클릭 상호작용): 이 환경에 브라우저 자동화 도구(Playwright/Selenium 등)가 없어 06단계도 재현 불가 — unit-4/9/12/16/17-test.md와 동일한 선례의 부채. `frontend/app/interviews/[id]/page.tsx`/`frontend/lib/api.ts`(`submitVoiceTurn`)는 코드 리뷰로 백엔드 실제 계약(필드명 `audio`, 에러 스키마의 top-level `code` 필드)과 일치함만 확인했다(§4 TC-999 참고, 실 렌더링 아님).
  - AI 응답 생성(LLM 꼬리질문) 자체의 품질/내용: unit-7 범위, `enqueue_turn_job` 스텁 계약(202+job_id 문자열)만 확인.
  - L1 경량판 원칙에 따라 401(인증없음)/404(존재하지 않는 id)/타인 소유 403(수평 권한상승)은 이번 06단계가 독립 재현하지 않음 — unit-2/3/4가 이미 같은 패턴(`_get_own_interview`, `get_current_user`)을 검증했고 unit-5는 이를 재사용만 했으므로 회귀 위험이 낮다고 판단, L1 부채로 이연.
  - 동시성/부하 테스트: L1 범위 밖, 설계서도 동시 STT 요청 순차처리를 unit-7(실제 워커) 범위로 명시.

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.13.9(신규 격리 venv `.harness-tmp/venv_06_unit5`, DEC-027/028 — 5단계의 `venv_05_unit5`를 재사용하지 않고 06 전용으로 새로 생성해 5단계 상태를 그대로 승계하지 않았음), PostgreSQL(Docker `final-project-db`, 포트 5544, 기존 컨테이너 재사용 — 신규 컨테이너 생성 안 함), Uvicorn 신규 프로세스(포트 8156, 06 전용 신규 포트).
- 테스트 데이터: 신규 candidate 계정 3개(이메일 `u5_06_candidate_*@example.com`, 매 실행마다 UUID로 신규 생성), gTTS(Google TTS, 인터넷 필요, 5단계와 동일하게 순수 테스트 도구 — 런타임 의존성 아님)로 합성한 실제 한국어 발화 mp3("안녕하세요, 저는 3년차 백엔드 개발자입니다. 대규모 트래픽 처리 경험이 있습니다.").
- 전제 조건: `backend/.env`의 `DATABASE_URL`이 기존 `final-project-db` 컨테이너를 가리킴(변경 없음), Alembic 마이그레이션은 unit-5가 신규 리비전을 만들지 않아 기존 head(`b84a71b986c5`) 그대로 사용, `faster-whisper` 모델 캐시(`~/.cache/huggingface/hub/models--Systran--faster-whisper-small`)가 사용자 홈 디렉토리에 이미 존재해 venv와 독립적으로 재사용됨(재다운로드 없음).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | (인수조건1) `biometric_voice` 동의 없이 실제 오디오 제출 | candidate 신규가입/로그인, `ai_interview_notice` 동의→`/start`(live) | `POST /turns`에 multipart로 실제 mp3 첨부 제출 → `GET /transcripts` 확인 | `403 {code: CONSENT_REQUIRED_VOICE}`, transcripts 0건 유지 | `403 CONSENT_REQUIRED_VOICE` 확인, `GET /transcripts` → `[]`(0건) | PASS | 독립 재현(run1/run2 각 1회씩, 총 2회 동일 결과) |
| TC-002 | (인수조건2, **실제 STT 실증**) 동의 등록 후 동일 오디오 재제출 | TC-001 상태에서 `POST /consents`(biometric_voice) 등록 | 동일 mp3로 `POST /turns` multipart 제출 → 응답/DB 확인 | `202`+문자열 `job_id`, `GET /transcripts`에 `speaker=user`/`input_mode=voice`/`audio_ref=null`/`content_text`가 비어있지 않은 한국어 텍스트로 저장, `turn_index=0` | `202`+job_id UUID 문자열 확인. transcripts[0] = `{speaker:'user', input_mode:'voice', audio_ref:null, turn_index:0, content_text:'안녕하세요 저는 3년차 백앤드 개발자입니다. 대규모 트래픽 처리 경험이 있습니다.'}` — 실제 faster-whisper 변환 결과이며 원문과 부분일치(`안녕`/`백엔드`(STT 결과는 "백앤드"로 근사 인식)/`개발자` 포함) 확인 | PASS | 첫 요청 소요 약 4.2초(모델은 앞선 05단계 실행으로 이미 캐시 로드된 상태라 5단계가 관찰한 17초보다 짧음 — 모델 로드/캐시 상태 편차, 결함 아님). STT 인식이 "백엔드"를 "백앤드"로 인식한 것은 실제 음성인식 모델의 정상적 오차범위이며 unit-5-note.md §7 인수조건2가 명시한 "정확한 워딩 100% 일치 불필요" 기준 충족 |
| TC-003 | (인수조건3) 음성 턴 직후 텍스트 턴 제출 — turn_index 공유 회귀 확인 | TC-002 완료 상태 | JSON `{"text":"..."}`로 `POST /turns` 제출 → `GET /transcripts` | `202` 반환, transcripts 2건, `turn_index` 0(voice)→1(text) 순서로 이어짐, unit-4 텍스트 경로 회귀 없음 | `202` 확인, transcripts 2건이 정확히 `turn_index=0(voice)`/`1(text)` 순서로 반환됨 | PASS | |
| TC-004 | (인수조건4, **DEC-023 핵심**) `biometric_voice` 동의 철회 후 재제출 — 실시간 재검사 증명 | TC-003 완료 상태, 등록했던 consent의 id 보유 | `POST /consents/{id}/revoke` → 동일 mp3로 `POST /turns` 재제출 → `GET /transcripts` | 철회 응답 `200`+`revoked_at` 채워짐. 재제출은 **캐시가 아니라 매 요청 재조회**이므로 즉시 `403 CONSENT_REQUIRED_VOICE`, transcripts는 여전히 2건(거부 시도 미저장) | 철회 `200`+`revoked_at` non-null 확인. 재제출 즉시 `403 CONSENT_REQUIRED_VOICE` 확인, transcripts 여전히 2건 확인 | PASS | **오케스트레이터 지시의 최우선 검증 대상 — 5단계 결과를 그대로 승계하지 않고 06단계가 새 프로세스/새 계정/새 세션으로 처음부터 재현해 통과**. 서버 요청 핸들러가 세션/캐시된 동의 상태가 아니라 DB를 실시간 재조회함이 코드(§`_has_active_consent`)와 실측 양쪽에서 확인됨 |
| TC-005 | (인수조건5) `audio` 필드 누락 | biometric_voice 재동의 등록(동의 자체는 유효 상태) | `audio`가 아닌 다른 필드명으로 multipart 제출 | `422 VALIDATION_ERROR`, transcripts 미저장 | `422 VALIDATION_ERROR` 확인 | PASS | 예외 입력 — 명백히 위험한 경계값이라 L1 범위 내에서도 필수 포함(원칙 3) |
| TC-006 | (인수조건5) 빈 오디오 파일(0바이트) | 동일 | `audio` 필드에 빈 바이트 제출 | `422 VALIDATION_ERROR`, transcripts 미저장 | `422 VALIDATION_ERROR` 확인 | PASS | 빈 입력 경계값 — 원칙에 따라 필수 검증 |
| TC-007 | (인수조건5) 오디오로 디코딩 불가능한 임의 바이트 | 동일 | 쓰레기 바이트(`\x00\x01...`반복)를 `audio.mp3`로 제출 | `504 AI_SERVICE_TIMEOUT`, transcripts 미저장 | `504 AI_SERVICE_TIMEOUT` 확인. TC-005~007 이후 `GET /transcripts`로 여전히 2건(추가 저장 없음) 재확인 | PASS | `stt_engine.SttTranscriptionError`→504 매핑이 실제로 동작함을 실측(코드 리뷰만이 아닌 실행 검증) |
| TC-008 | (인수조건6) `scheduled` 상태 세션에 음성 제출 | 신규 세션 생성 직후(아직 `/start` 호출 안 함) | 해당 세션에 `POST /turns` multipart 제출 | `409 VALIDATION_ERROR`(동의 여부 무관, 상태 검사가 먼저 적용) | `409 VALIDATION_ERROR` 확인 | PASS | unit-4 텍스트 경로의 `_ensure_turn_submittable` 공통 로직 재사용 확인 |
| TC-009 | (인수조건6) `completed` 상태 세션에 음성 제출 | TC-008 세션을 `/start`→`/end`로 completed 전환 | 동일 세션에 `POST /turns` multipart 제출 | `409 VALIDATION_ERROR` | `409 VALIDATION_ERROR` 확인 | PASS | |
| TC-999 | (범위 외, 코드 리뷰 한정 — 인수조건7 대체) 프런트 `submitVoiceTurn`/`AudioRecorderControl` 계약 일치 확인 | 없음 | `frontend/lib/api.ts`의 `submitVoiceTurn` 소스와 백엔드 실제 계약(필드명 `audio`, 에러 응답 top-level `code`) 대조 | 필드명/에러 스키마 일치 | 일치 확인(`formData.append("audio", ...)`, `body?.code`가 실제 응답 스키마의 top-level `code`와 일치) — 단, 실제 브라우저 클릭/녹음/업로드 상호작용 자체는 미검증(도구 부재) | CONDITIONAL PASS(코드 레벨만) | 실 브라우저 검증은 L1 부채로 이연(§2 제외범위 참고) |

> 실행 로그: `.harness-tmp/u5_06/run1.log`, `run2.log`(2회 독립 실행, 각 28건/28건 PASS, 0건 FAIL — 7절 Teardown에 따라 세션 종료 시 삭제됨, 위 표가 그 결과의 요약). 서버 로그(`uvicorn_06_unit5.log`)에 기대하지 못한 스택트레이스/예외 없음을 확인 후 삭제.

## 5. 커버리지
L1 경량판 — 미해당(ORCHESTRATOR.md 1장 "구현 속도 트랙" 참고, 라인/브랜치 커버리지 도구를 이번 유닛에서 구동하지 않음).

## 6. 결함(Defect) 목록
- 결함 없음. 근거: TC-001~TC-009(총 9개 시나리오, 28개 개별 단언)를 독립된 신규 venv·신규 서버 프로세스·신규 계정으로 2회 반복 실행(run1/run2)해 두 번 모두 전체 PASS(0 FAIL)를 확인했다. 서버 로그에서도 기대하지 못한 예외/스택트레이스가 없음을 별도로 grep 확인했다. STT 인식 결과의 사소한 표기 차이("백엔드"→"백앤드")는 unit-5-note.md §7 인수조건2가 명시적으로 허용한 범위(완전 무관하거나 빈 문자열일 때만 결함)에 해당하지 않아 결함으로 기록하지 않는다.
- 참고(결함 아님, 정보성): 5단계 note가 기록한 "첫 요청 약 17초" 지연은 이번 06단계 재현에서는 관측되지 않았다(약 4.2초) — faster-whisper 모델이 사용자 홈 캐시(`~/.cache/huggingface`)에 venv와 무관하게 이미 존재했기 때문이며, 이는 05단계가 이미 문서화한 "캐시/디스크 상태에 따른 편차"와 일치하는 정상 변동이다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit5/`(06 전용 신규 격리 venv, DEC-027) — 다른 유닛들의 선례(unit-5-note.md §6-8이 명시한 `venv_05_unit9/12`, `venv_06_unit17` 등)와 동일하게 재사용 가능하도록 **보존**함(삭제하지 않음, 아래 사유 참고).
  - `.harness-tmp/u5_06/`(테스트 스크립트 `test_unit5.py`, DB 정리 스크립트 `cleanup.py`, gTTS 합성 오디오 `u5_06_test_audio.mp3`, 실행 로그 `run1.log`/`run2.log`, 서버 로그 `uvicorn_06_unit5.log`) — **삭제 완료**.
  - DB에 생성된 테스트 데이터(candidate 계정 3개, interview 6건, consent 9건, transcript 6건, 이메일 패턴 `u5_06_%`) — `cleanup.py`로 직접 DELETE해 정리 완료(정리 후 `select count(*) from users where email like 'u5_06_%'` → 0 확인).
  - Uvicorn 서버 프로세스(포트 8156, PID 39800 — `Get-NetTCPConnection`으로 확인한 실제 소유 PID만 지정해 종료, 이미지 이름 기준 광범위 종료 금지 원칙(DEC-027/028) 준수) — 종료 완료(종료 후 해당 포트 `Get-NetTCPConnection` 결과 없음으로 재확인).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: `.harness-tmp/u5_06/`은 삭제 완료. `.harness-tmp/venv_06_unit5/`는 05단계 선례와 동일한 근거(재사용 가능한 격리 환경 보존, 다른 유닛의 venv를 건드리지 않음)로 의도적으로 보존 — 프로젝트 소스 트리(git 추적 대상) 밖이라 `git status`에는 영향 없음.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M backend/alembic/env.py
 M backend/app/api/v1/interviews.py
 M backend/app/main.py
 M backend/app/services/job_queue.py
 M backend/requirements.txt
 M docs/harness/decisions.md
 M docs/harness/traceability.md
 M frontend/app/globals.css
 M frontend/lib/api.ts
 M frontend/next-env.d.ts
 M frontend/package-lock.json
 M frontend/package.json
?? backend/alembic/versions/0df1434883f2_v3_transcripts.py
?? backend/alembic/versions/8a55fda78a42_v4_deletion_requests.py
?? backend/alembic/versions/b84a71b986c5_v6_code_submissions.py
?? backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py
?? backend/alembic/versions/d3f7a2c9e1b4_v7_rubric_templates.py
?? backend/app/api/v1/code_submissions.py
?? backend/app/api/v1/consents.py
?? backend/app/api/v1/ops.py
?? backend/app/api/v1/recruiter.py
?? backend/app/api/v1/whiteboard.py
?? backend/app/api/v1/ws.py
?? backend/app/models/code_submission.py
?? backend/app/models/deletion_request.py
?? backend/app/models/rubric_template.py
?? backend/app/models/transcript.py
?? backend/app/models/whiteboard.py
?? backend/app/schemas/code_submission.py
?? backend/app/schemas/consent.py
?? backend/app/schemas/ops.py
?? backend/app/schemas/recruiter.py
?? backend/app/schemas/rubric_template.py
?? backend/app/schemas/transcript.py
?? backend/app/schemas/whiteboard.py
?? backend/app/services/stt_engine.py
?? docs/harness/units/  (unit-5-test.md 포함, 이번 산출물)
?? frontend/app/admin/
?? frontend/app/interviews/
?? frontend/app/legal/
?? frontend/app/mypage/
?? frontend/app/recruiter/
?? frontend/components/
?? frontend/lib/complianceContent.ts
?? frontend/tsconfig.tsbuildinfo
```
  `frontend/next-env.d.ts`(수정)와 `frontend/tsconfig.tsbuildinfo`(신규)는 이번 06단계 세션이 프런트엔드 명령(`npm`/`npx`)을 전혀 실행하지 않았음에도 관찰되었다 — 병렬로 진행 중인 다른 작업 단위 세션이 만든 변경으로 추정되며(unit-4-test.md §7이 기록한 것과 동일한 성격의 공유 환경 이슈), 이번 unit-5 06 세션이 원인이 아니고 원복 대상도 아니므로 그대로 둔다(다른 세션의 작업을 임의로 되돌리지 않음). 그 외 모든 파일은 unit-1~18의 05단계가 이미 만든 것으로 이번 06 세션이 신규로 남긴 변경이 아니다(백엔드 `interviews.py`/`stt_engine.py`/`requirements.txt`는 5단계 산출물 그대로, 06단계가 코드를 수정하지 않았음).
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 준수 확인: 위 목록과 같이 `.harness-tmp/` 하위 임시 산출물은 삭제(venv 제외, 재사용 근거 명시), DB 테스트 데이터 삭제, 서버 프로세스(직접 확인한 PID만) 종료 모두 완료. `git status`에 이번 세션이 원인인 미정리 잔여물 없음.

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, "07 부채(미실행)" 사실은 아래 §9 및 `docs/harness/traceability.md`에 기록함, ORCHESTRATOR.md 1장 참고). 참고로 남겨둘 잔존 리스크: (1) 인수조건7(브라우저 마이크 UI 실제 상호작용)은 이 환경 제약상 06단계도 검증하지 못했다 — 실제 브라우저(또는 headless 자동화) 도입 시 최우선 재검증 필요. (2) AI Worker(Celery)가 아직 없어 STT가 HTTP 요청 핸들러 내 동기 실행되는 구조(unit-5-note.md §2 편차1) — 동시 다중 요청 시 지연/큐잉 동작은 unit-7이 실제 워커를 만들 때 재검증 필요.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). 단, L1 트랙 규칙에 따라 07단계(통합테스트)로 handoff하지 않고 05단계로 돌아가 다음 작업단위를 진행한다. `docs/harness/traceability.md`의 REQ-004/REQ-005 비고란에 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요"를 표기했다(인수조건7 브라우저 UI, 401/404/403 수평권한상승, 동시성/실제 워커 지연 등 미검증 항목 포함).
- [ ] CONDITIONAL PASS
- [ ] FAIL

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장 참고). 다만 아래는 06단계가 실제로 수행한 자체 재점검 기록(형식적 생략과 구분하기 위해 남김):
- 1차 검증(실행 직후): TC-001~TC-009가 unit-5-note.md §7 인수조건 1~6과 1:1로 대응하는지 표로 재대조 — 인수조건 1→TC-001, 2→TC-002, 3→TC-003, 4→TC-004, 5→TC-005/006/007, 6→TC-008/009로 100% 커버 확인. 첫 실행에서 5건이 FAIL로 표시됐으나 원인을 조사한 결과 테스트 스크립트 자체의 단언 버그(`error.code` 중첩 경로를 잘못 가정, 실제 API는 top-level `code` 필드)였음을 확인 — 스크립트를 수정하고 재실행(run1.log)해 28/28 PASS 확인. 이는 "테스트 자체가 잘못 설계되어 결함을 놓칠 가능성"을 실제로 겪고 교정한 사례.
- 2차 검증(회의적 재검토): "이 테스트를 통과했다고 다음 단계에 넘겨도 되는가"를 의심하며 완전히 독립된 두 번째 실행(신규 계정, 신규 UUID)을 수행(run2.log, 28/28 PASS) — 우연한 일치가 아님을 확인. 또한 놓쳤을 법한 경계 조건을 재검토: (a) 철회 후 재동의하면 다시 통과하는지(TC-005 직전에 재동의→성공 확인, 캐시가 없다는 것의 역방향 증거), (b) 예외 입력 3종이 실제로 DB에 아무 흔적도 남기지 않는지(각 TC 직후 `GET /transcripts` count 재확인), (c) STT 결과가 하드코딩/스텁이 아니라 실제 모델 출력인지(오디오 원문과 부분일치 검증 + 05단계와 다른 신규 세션에서 동일 문장 재확인으로 재현성 확보). 이 세 가지 모두 표에 반영됨.
- 검증 로그 파일 경로: `.harness-tmp/u5_06/run1.log`, `.harness-tmp/u5_06/run2.log`(규칙 K에 따라 세션 종료 시 삭제됨 — 삭제 전 위 §4/§6/본 절에 핵심 내용을 텍스트로 보존했음).
