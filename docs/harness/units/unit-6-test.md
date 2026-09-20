# 테스트 결과서 (Test Result Report) — unit-6

## 1. 개요
- 테스트 대상: unit-6, Feature C(대화형 인터뷰 엔진) — REQ-006 오픈소스 TTS(Piper) 연동. `backend/app/services/tts_engine.py`(신규), `backend/app/api/v1/interviews.py`의 `POST /interviews/{id}/tts-preview`(신규), `backend/app/main.py`의 `/media` 정적 마운트.
- 테스트 유형: 단위
- 적용 Tier: (오케스트레이터 전달값 기준) — 이 feature(Feature C)는 여러 유닛(unit-4/5/6/7)으로 구성되어 06·07 병합 조건("이 feature의 마지막 작업 단위 + Low 등급 + 유닛 3개 이하") 중 "유닛 3개 이하"를 충족하지 않으므로(unit-4/5/6/7 최소 4개) 병합 대상이 아니다. 통상 절차대로 `unit-6-test.md` 단독 산출.
- 적용 속도 트랙: **L1**(unit-6-note.md §0, DEC-003) — 경량판. 본 보고서는 1·2·3·4·6·7·9절만 정식 작성하고 5·8·10절은 "L1 경량판 — 미해당"으로 명시한다.
- 테스트 목적: 5단계(`05-unit-developer`)가 자체 기록한 end-to-end 검증을 그대로 승계하지 않고, 06단계가 독립적으로 새 서버 프로세스를 기동해 (1) 임의 텍스트가 실제로 음성(WAV)으로 합성·저장·다운로드되는지, (2) Piper가 GPL 격리 원칙대로 서브프로세스로만 호출되는지(코드 확인)를 재현·재확인한다.
- 관련 산출물: `docs/harness/units/unit-6-note.md`(인수조건 §7, 게이트1/2 §4/§5), `docs/harness/03-system-design.md` §2.5/§4.5/§5.4, `docs/harness/traceability.md` REQ-006 행.
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19

> "단위+통합 병합" 해당 없음(위 Tier 절 사유 참고) — 이 보고서는 순수 단위테스트 범위만 다룬다.

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - `POST /interviews/{id}/tts-preview` 정상 경로(200, `audio_url` 반환) 및 실제 합성된 WAV 파일 유효성.
  - `GET {audio_url}`(정적 서빙)의 상태코드/`Content-Type`/바디 무결성.
  - `text` 필드 경계값(빈 문자열/필드 누락/501자/500자).
  - 인증/권한 경계(토큰 없음 401, 존재하지 않는 interview 404, 타인 소유 세션 403).
  - 동일 텍스트 반복 호출 시 매번 새 `audio_url` 발급(비멱등성).
  - `GET /interviews/{id}/transcripts`(unit-4)에 이 엔드포인트의 흔적이 남지 않는지.
  - 코드 검토를 통한 GPL 격리 원칙 재확인(Piper 프로세스 내 import 여부, `subprocess.run` 인자 방식).
  - unit-6-note.md §4/§5(게이트1 린트, 게이트2 체크리스트)가 실제로 통과됐는지 note 기록 확인.
- 제외 범위 (Out-of-Scope) 및 사유:
  - L1 경량판 원칙에 따라 동시 다중 요청 시 지연/큐잉, 다양한 텍스트(특수문자·이모지·다국어) 견고성, 브라우저 실사용 재생 UI 검증(애초에 프런트 변경 없음)은 이번 06단계 범위에서 제외한다 — `traceability.md` REQ-006 비고에 "L1 부채"로 이미 기록되어 있으며, 08 착수 전 정산 대상이다.
  - 음성모델 재다운로드 경로(네트워크 단절/다운로드 실패) 자체 재현은 하지 않는다 — 이번 환경에 이미 캐시(`backend/var/piper_voices/ko_KR-kss-medium.*`)가 존재해 5단계가 이미 실측했고, L1 범위에서 재현 비용 대비 실익이 낮다고 판단. 다만 이 결정이 위험을 은폐하지 않도록 8절 대신 아래 §3 "위험 관찰"에 기록한다(참고: L1 경량판이라도 명백히 위험한 케이스는 발견 시 범위를 넘어 기록한다는 원칙에 따라, 이번 재현에서는 발견된 신규 위험이 없었음을 명시).
  - `turn_result.audio_url`로의 실제 파이프라인 연결(unit-7 LLM 이후)은 이 유닛 자체가 범위 밖으로 명시했으므로 테스트 대상이 아니다.

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.13.9, PostgreSQL(Docker `final-project-db`, 포트 5544, 기존 컨테이너 재사용, 신규 마이그레이션 없음 — `alembic current` → `d3f7a2c9e1b4 (head)` 확인), FastAPI/uvicorn(`uvicorn app.main:app --port 8163`, 06단계가 신규로 기동).
- 격리 venv(DEC-027): `.harness-tmp/venv_06_unit6`을 06단계가 신규로 생성(5단계의 `venv_05_unit6` 재사용하지 않음, 서로 다른 병렬 유닛 영향 방지). `pip install -r backend/requirements.txt` + `pip install -r backend/requirements-dev.txt` 성공. `pip show piper-tts` → 버전 1.8.0 확인(5단계 기록과 일치).
- 테스트 데이터: 신규 candidate 계정 2개(`u6_test_<ts>@example.com`, `u6_test2_<ts>@example.com`), candidate A 소유 interview 세션 1건(`status=scheduled`, 신규 생성). 5단계가 남겨둔 음성모델 캐시(`backend/var/piper_voices/ko_KR-kss-medium.{onnx,onnx.json}`, 약 63MB)를 재사용해 다운로드 없이 즉시 합성 재현.
- 전제 조건: `final-project-db` 컨테이너 기동 상태. 한글 텍스트를 curl 요청 바디에 넣을 때는 UTF-8 인코딩의 임시 JSON 파일(`--data-binary @file`)을 사용해야 함 — bash 인라인 `-d '{"text":"한글"}'` 방식은 Windows 셸 로캘(cp949) 문제로 서버가 `400 There was an error parsing the body`를 반환함을 직접 재현으로 확인(unit-4/5-note.md가 이미 기록한 것과 동일 계열의 환경 이슈, **앱 결함 아님** — 인증/존재/권한 검증처럼 텍스트 내용에 의존하지 않는 케이스는 ASCII 인라인으로도 정상 확인됨).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 (AC1) | 정상 경로: 본인 세션에 한국어 문장 합성 요청 | candidate A 로그인, 본인 interview(scheduled) 존재 | `POST /interviews/{id}/tts-preview` with UTF-8 파일 바디 `{"text":"안녕하세요, 자기소개 부탁드립니다."}` | `200` + `{"audio_url":"/media/tts/{uuid}.wav"}` | `200`, `{"audio_url":"/media/tts/dcb38e0e-...wav"}`, 소요 2.57초 | PASS | AC1 |
| TC-002 (AC2) | TC-001의 `audio_url`을 실제 다운로드해 유효한 오디오인지 검증 | TC-001 완료 | `GET /media/tts/{uuid}.wav` 후 `wave` 모듈로 열기 | `200`, `Content-Type: audio/wav`, 손상 없는 모노/22050Hz WAV | `200`, `Content-Type: audio/wav`, `content-length: 123948`, `channels=1, rate=22050Hz, duration≈2.81초` — 정상 재생 가능한 WAV로 확인 | PASS | AC2 |
| TC-003 (AC3) | 경계값: 빈 문자열 | candidate A 로그인 | `{"text":""}` 전송 | `422` | `422 VALIDATION_ERROR`(`string_too_short`) | PASS | AC3 |
| TC-004 (AC3) | 경계값: `text` 필드 누락 | candidate A 로그인 | `{}` 전송 | `422` | `422 VALIDATION_ERROR`(`missing`) | PASS | AC3 |
| TC-005 (AC3) | 경계값: 501자 | candidate A 로그인 | `{"text":"a"*501}` 전송 | `422` | `422 VALIDATION_ERROR`(`string_too_long`, max 500) | PASS | AC3 |
| TC-006 (AC3, 경계) | 경계값: 정확히 500자(통과 경계) | candidate A 로그인 | `{"text":"a"*500}` 전송 | `200`(422 아님) | `200`, `audio_url` 정상 발급, 2.46초 | PASS | AC3 — 500자는 통과해야 함을 별도 재확인 |
| TC-007 (AC4) | 인증 없음 | 토큰 미포함 | `Authorization` 헤더 없이 호출(`{"text":"hello"}`) | `401` | `401 AUTH_INVALID_TOKEN` | PASS | AC4 |
| TC-008 (AC4) | 존재하지 않는 interview id | candidate A 로그인 | 랜덤 UUID(`00000000-...`)로 호출 | `404` | `404 NOT_FOUND` | PASS | AC4 |
| TC-009 (AC4) | 타인 소유 세션 호출(수평 권한 상승) | candidate B 로그인, candidate A의 interview id 사용 | candidate B 토큰으로 A의 interview에 호출 | `403 AUTH_FORBIDDEN` | `403 AUTH_FORBIDDEN` | PASS | AC4 |
| TC-010 (AC5) | 동일 텍스트 반복 호출 → 비멱등 | TC-001과 동일 텍스트 재사용 | 동일 `{"text":...}`로 두 번째 호출 | 첫 호출과 다른 새 `audio_url`(UUID 상이) | `audio_url` = `/media/tts/1179b3cc-...wav`(TC-001의 `dcb38e0e-...`와 상이) | PASS | AC5 |
| TC-011 (AC6) | TTS 미리듣기가 대화 이력(transcripts)에 영향 없음 | TC-001/TC-010으로 tts-preview 2회 호출 완료, 해당 interview에는 실제 턴(turn) 제출 이력 없음 | `GET /interviews/{id}/transcripts` 호출 | `200 []`(tts-preview 호출로 생긴 레코드 없음) | `200 []` | PASS | AC6 |
| TC-012 (AC7, 참고) | 합성 소요시간이 §5.4 타임아웃(10초) 예산 내 | TC-001/TC-006 실측 | `time curl ...`로 소요시간 측정 | 매 호출이 서브프로세스 기동+모델 로드 포함 약 2~4초 내외(결함 아님, 참고 조건) | TC-001: 2.57초, TC-006(500자): 2.46초 — 두 번째 호출도 빨라지지 않고 유사한 시간대(§2 편차#3과 일치, "두 번째부터 빨라지는" STT 패턴이 아님을 재확인) | PASS | AC7(참고, 결함 아님) |
| TC-013 (코드 확인) | GPL 격리 원칙 준수: Piper 프로세스 내 import 금지, 서브프로세스 커맨드 인젝션 경로 없음 | 정적 코드 검토 | `backend/app/` 전체에서 `import piper`/`from piper` 검색, `tts_engine.py`의 `subprocess.run` 호출부 인자 방식 확인 | 매칭 없음(import 없음), `subprocess.run`이 리스트 인자 + `shell=True` 미사용 | `grep "import piper|from piper" backend/app/` → No matches found. `tts_engine.py`의 두 `subprocess.run` 호출 모두 `[sys.executable, "-m", "piper"/"piper.download_voices", ...]` 리스트 인자, `shell=True` 없음 확인 | PASS | 인수조건 목록 밖이나 오케스트레이터 지시(GPL 격리 재확인)에 따라 추가 |
| TC-014 (내구성 확인) | 서버 로그/임시파일 정리 | TC-001~TC-012 실행 후 | `uvicorn_06_unit6.log`에서 예기치 못한 스택트레이스 grep, `backend/var/media/.tts_tmp/` 디렉터리 내용 확인 | 예기치 못한 예외 없음, `.tts_tmp`가 매 요청 후 비어있음 | 로그에 401/404/403/422 외 스택트레이스 없음, `.tts_tmp` 비어있음(입출력 임시파일이 `finally`에서 정리됨을 재확인) | PASS | 게이트2 체크리스트(§5) 재확인 |

> 정상 경로 + 경계값(501/500자) + 예외 입력(빈 문자열/필드 누락/토큰 없음) + 권한 경계(403/404) 모두 포함. 인수조건 1~7 전항목 1:1 매핑 완료(위 표 "비고" 컬럼 AC1~AC7 참고).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. TC-001~TC-014 총 14개 케이스(정상 경로 2건, 경계값 3건, 통과 경계 1건, 인증/권한 경계 3건, 비멱등성 1건, 대화이력 비침투 1건, 참고 성능 1건, 코드 검토 1건, 로그/임시파일 정리 1건)를 06단계가 독립 기동한 신규 서버 프로세스(포트 8163, `.harness-tmp/venv_06_unit6`)와 신규 계정으로 직접 재현했고, 모두 unit-6-note.md §7의 인수조건 및 03-system-design.md §2.5/§4.5/§5.4 명세와 일치하는 실제 결과를 확인했다. 테스트 도중 겪은 유일한 이상 동작(한글 인라인 curl 바디의 400 에러)은 재현 결과 앱 결함이 아니라 Windows 셸 인코딩 문제임을 확인했다(§3 전제조건에 기록, UTF-8 파일 경유로 우회 후 정상 동작 재확인 — unit-4/5-note.md의 선례와 동일 계열).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit6/`(신규 격리 venv)
  - `.harness-tmp/uvicorn_06_unit6.log`, `.harness-tmp/uvicorn_06_unit6.pid`
  - `.harness-tmp/u6_*.json`, `.harness-tmp/u6_*.wav`, `.harness-tmp/u6_*.txt`(요청 바디/응답 캡처, 다운로드한 WAV 사본)
  - `backend/var/media/tts/*.wav`(TC-001/TC-006/TC-010이 실제로 합성해 저장한 WAV 5건 — `.gitignore` 대상 런타임 산출물)
  - DB: candidate 계정 2개(`u6_test*@example.com`) + 그에 연결된 interview 세션 1건
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 — 단, `backend/var/media/tts/*.wav`는 애플리케이션 자체의 정식 산출물 경로(`backend/var/`, `.gitignore` 대상)이며 06단계가 `.harness-tmp/` 밖에 별도로 만든 임시자원이 아니다. 이 경로는 정리 목록에는 포함하되 규칙 K 1번(venv/임시DB/임시설정파일 한정)의 직접 대상은 아니라고 판단했다 — 다만 안전을 기해 테스트로 생성한 5개 WAV 파일 전부 삭제했다.
- 정리(삭제) 완료 여부: 완료. `Stop-Process -Id 18436 -Force`로 06단계가 직접 기동한 uvicorn 프로세스만 지정 종료(DEC-028, 이미지 이름 와일드카드 미사용, 종료 전 `Get-NetTCPConnection -LocalPort 8163`로 실제 소유 PID 재확인) → 이후 `curl`이 연결 거부됨을 확인. DB에서 테스트 계정/세션 `DELETE` 완료(1 interview, 2 users). `.harness-tmp/u6_*`, `uvicorn_06_unit6.log/.pid` 전체 삭제. `.harness-tmp/venv_06_unit6` 전체 삭제. `backend/var/media/tts/*.wav`(테스트 산출물 5건) 삭제, `backend/var/media/.tts_tmp/` 빈 디렉터리 제거. 5단계가 남긴 `backend/var/piper_voices/`(음성모델 캐시)는 재사용 목적의 정당한 공유 자원이므로 보존.
- 정리 후 `git status` 실행 결과:
```
 M .gitignore
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
?? backend/app/services/tts_engine.py
?? docs/harness/units/(각 유닛의 note.md/test.md — 06단계가 생성 중인 본 파일 포함)
```
(위 목록은 이 유닛(unit-6) 작업 시작 전부터 존재하던 다른 병렬 작업 단위의 미커밋 변경 + 이번 06단계가 새로 작성 중인 `unit-6-test.md` 자체뿐이며, unit-6 테스트 과정에서 발생한 잔여 임시 산출물은 없음을 확인했다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- **7절 완료, `git status`가 unit-6 테스트로 인한 잔여물 없이 깨끗함(사전 존재하던 다른 유닛의 변경만 남음)을 확인 — 8절/9절 PASS 판정 가능.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당. (단, "07 부채(미실행)" 사실은 `docs/harness/traceability.md` REQ-006 행 비고란에 별도로 기록했다 — 아래 "완료 보고" 참고.)

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). L1 규칙에 따라 07단계로 handoff하지 않고, 05단계로 복귀하여 다음 작업 단위를 진행한다.
- [ ] CONDITIONAL PASS
- [ ] FAIL

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
L1 경량판 — 검증 생략. (참고: 작성 과정에서 자체적으로 2단계 재확인을 수행했다 — 1차: unit-6-note.md §7의 인수조건 7개와 위 §4 표의 TC-001~TC-012가 1:1로 대응하는지 대조해 누락 없음을 확인. 2차: "이 결과를 신뢰할 수 있는가"를 의심하며 (a) 5단계 자체보고를 그대로 베끼지 않고 06단계가 새 venv·새 서버 프로세스·새 계정으로 처음부터 재현했는지, (b) GPL 격리를 코드 레벨에서 직접 재확인했는지, (c) Teardown이 실제로 완료됐는지를 재점검 — 모두 충족을 확인. 다만 이는 L1 규칙상 요구되는 정식 `verification-log-template.md` 2회 절차는 아니며, 08 착수 전 정식화 시 정식 수행 필요.)
