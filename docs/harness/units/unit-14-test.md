# 테스트 결과서 — unit-14 (Feature G. 규제 컴플라이언스, REQ-029/030)

## 1. 개요
- 테스트 대상: `backend/app/api/v1/consents.py`(동의 등록/철회/이력조회, 삭제요청 생성/조회 5개 엔드포인트), `backend/app/models/deletion_request.py`, `backend/app/schemas/consent.py`
- 테스트 유형: 단위
- 적용 Tier: High
- 적용 속도 트랙: **L1(DEC-003)** — 경량판. 정상 경로 1~2케이스만 06단계가 독립적으로 재현·검증. `test-report-template.md` 1·2·3·4·6·7·9절만 정식 작성, 5·8·10절은 "L1 경량판 — 미해당"으로 명시(오케스트레이터 지시 그대로).
- 테스트 목적: 5단계(`05-unit-developer`)가 자체 검증(curl)한 결과를 그대로 승계하지 않고, 06단계가 새 서버 프로세스를 독립적으로 기동해 핵심 정상 경로가 실제로 재현되는지 증명한다.
- 관련 산출물: `docs/harness/units/unit-14-note.md`(인수조건 §4, 게이트1/2 §5·6), `docs/harness/03-system-design.md` §3(CONSENTS/DELETION_REQUESTS ERD), §4.2, §6.2(DEC-023/024), `docs/harness/traceability.md`(REQ-029/030)
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST, 서버 로그 타임스탬프는 UTC 23:03경)

> 이 보고서는 "단위+통합 병합" 대상이 아니다 — Feature G(unit-14/15)는 작업 단위 총 2개이나 적용 Tier가 **High**이므로 06·07 병합 조건(Low 등급 + 3개 이하)을 충족하지 못한다. 따라서 07단계로 handoff하지 않는 것은 병합 때문이 아니라 **L1 규칙**(정상 경로만 검증하고 07은 L1 부채로 이월) 때문이다.

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로만):
  - TC-001: `POST /consents`(`ai_interview_notice`) 등록 → `GET /users/me/consents` 이력 반영 확인 → unit-2가 만든 `/interviews/{id}/start` 동의 게이트가 이 동의를 실시간 소비함(동의 전 403 → 동의 후 202) 통합 확인(unit-14-note.md 인수조건 #1,#2,#11에 대응).
  - TC-002: TC-001의 동의를 `POST /consents/{id}/revoke`로 철회 → `DELETE /users/me/biometric-data`(삭제요청 생성, 202/pending) → `GET /users/me/deletion-requests` 이력 반영 확인(인수조건 #3,#8,#9에 대응).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 #4(재철회 409), #5(존재하지 않는 id 404), #6(타인 소유 403), #7(잘못된 enum 422), #10(토큰 없음 401) — L1 규칙상 06단계는 "정상 경로 1~2케이스만" 재현하도록 명시적으로 지시받았다. 이 경계/예외 케이스들은 5단계가 자체 curl로 이미 실행했다고 note §7에 기록되어 있으나, 06단계가 독립 재현하지 않았으므로 traceability.md에 "L1 부채"로 이월한다.
  - `biometric_voice` 동의의 실제 강제(`403 CONSENT_REQUIRED_VOICE`) — 그 게이트를 소비할 `/turns` 음성(multipart) 엔드포인트 자체가 아직 없음(unit-5, REQ-004/005 범위). unit-14-note.md §3에 06단계가 이 케이스를 요구해서는 안 된다고 명시되어 있어 그대로 따름.
  - 실제 생체정보 하드 삭제(파기) 완료 여부 — `DELETION_REQUESTS.status`를 `completed`로 바꾸는 배치는 아직 어떤 유닛도 구현하지 않음(unit-15/REQ-033 소관). 이번 테스트는 `pending` 상태 생성까지만 확인한다.
  - 프론트엔드([C-13] 마이페이지 UI) — unit-14는 API 전용 유닛으로 프론트 구현이 없다(unit-14-note.md §2 편차 #5).

## 3. 테스트 환경
- 실행 환경: Windows 11, Git Bash, Python(venv) `.harness-tmp/venv_05_unit1`(5단계가 만든 venv 재사용, 이번 테스트에서 신규 venv를 만들지 않음), PostgreSQL(Docker `final-project-db`, 포트 5544, 기존 컨테이너 재사용), Backend는 `uvicorn app.main:app --port 8051`로 **06단계가 이번에 독립적으로 새로 기동**(5단계가 쓰던 포트 8031이 아닌 별도 포트, 5단계 프로세스와 무관함을 보장).
- 테스트 데이터: 이번 테스트에서 신규 생성한 candidate 계정 1개(`u14_06test_<timestamp>@example.com`, 06단계가 직접 회원가입·로그인), 그 계정으로 생성한 면접 세션 1건, 동의 레코드 1건, 삭제요청 레코드 1건. 5단계가 만든 데이터는 재사용하지 않았다.
- 전제 조건: `alembic current` 확인 결과 DB가 `8a55fda78a42 (head)`(unit-14의 `v4_deletion_requests` 리비전 포함)에 있음을 사전 확인(아래 로그). `ruff check`로 게이트1을 06단계가 재확인.

```
$ python -m alembic current
8a55fda78a42 (head)

$ python -m ruff check app/api/v1/consents.py app/models/deletion_request.py app/schemas/consent.py
All checks passed!
```

## 4. 테스트 케이스 및 결과

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 사전고지 동의 등록 → 이력 조회 → `/start` 게이트 실통합(인수조건 #1,#2,#11) | candidate 신규 가입/로그인 완료, 면접 세션 1건 생성(`scheduled`) | 1) 동의 없이 `POST /interviews/{id}/start` 2) `POST /consents {"consent_type":"ai_interview_notice"}` 3) `GET /users/me/consents` 4) 동일 `POST /interviews/{id}/start` 재시도 | 1) `403 CONSENT_REQUIRED_NOTICE` 2) `201`, `id`/`granted_at`(not null)/`revoked_at`(null) 3) 응답 배열에 방금 만든 레코드 포함 4) `202`, `interview.status="live"` | 1) 실제 `403 {"code":"CONSENT_REQUIRED_NOTICE",...}` 확인 2) 실제 `201 {"id":"cbf23678-...","consent_type":"ai_interview_notice","granted_at":"2026-09-18T23:03:39...","revoked_at":null}` 확인 3) `GET` 응답 배열에 동일 `id` 포함 확인 4) 실제 `202 {"job_id":"...","interview":{...,"status":"live",...}}` 확인 | PASS | 5단계가 이미 이 플로우를 자체 curl로 검증했다고 보고했으나(note §7), 06단계가 새 서버(포트 8051)·새 계정·새 세션으로 처음부터 독립 재현해 동일 결과를 얻었다. unit-2의 `/start` 게이트(`interviews.py`, unit-14가 수정하지 않은 파일)가 unit-14의 신규 API로 채워진 `CONSENTS` 데이터를 실시간으로 정상 소비함을 증명 |
| TC-002 | 동의 철회 → 생체정보 삭제요청 생성 → 이력 조회(인수조건 #3,#8,#9) | TC-001에서 만든 동의 레코드(`revoked_at=null`) 존재 | 1) `POST /consents/{id}/revoke` 2) `DELETE /users/me/biometric-data` 3) `GET /users/me/deletion-requests` | 1) `200`, `revoked_at`(not null) 채워진 레코드 반환 2) `202`, `target="biometric_only"`/`status="pending"`/`completed_at=null` 3) 응답 배열에 방금 생성한 요청 포함 | 1) 실제 `200 {"id":"cbf23678-...","revoked_at":"2026-09-18T23:03:48..."}` 확인 2) 실제 `202 {"id":"b6bd3144-...","target":"biometric_only","status":"pending","completed_at":null}` 확인 3) `GET` 응답 배열에 동일 `id` 포함 확인 | PASS | 실제 하드 삭제(파기)는 검증 범위 밖(unit-15/REQ-033 소관, §2 명시) — 이번 케이스는 "요청 접수 및 상태 관리"까지만 확인 |

> L1 규칙에 따라 정상 경로 2케이스만 실행했다. 경계값/예외 입력 케이스(재철회 409, 존재하지 않는 id 404, 타인 소유 403, 잘못된 enum 422, 토큰 없음 401)는 이번 06단계 검증 범위가 아니며, 5단계 자체 보고(unit-14-note.md §7)에만 기록되어 있고 06단계가 독립 재현하지 않았다는 사실을 그대로 명시한다(§2, traceability.md 비고 참고). 위험도가 높은 "빈 입력/null" 케이스도 이번 L1 라운드에서는 추가 실행하지 않았다 — 07(L1 부채 정산) 단계에서 반드시 재검토해야 한다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| (없음) | | | | | |

- 결함 0건: TC-001, TC-002 모두 unit-14-note.md §4 인수조건 #1,#2,#3,#8,#9,#11에 명시된 기대 응답(상태 코드, 필드값, not null/null 여부)과 실제 응답이 정확히 일치함을 위 §4 표에서 확인했다. 또한 게이트1(ruff, 대상 파일 전체) 재실행 결과 `All checks passed!`로 06단계가 독립 재확인했다(5단계 보고를 그대로 승계하지 않음).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/uvicorn_06_unit14.log`(06단계가 새로 기동한 uvicorn 프로세스 로그, 포트 8051)
  - `.harness-tmp/u14_06_token.txt`(테스트용 JWT/interview id 임시 저장)
  - venv/DB는 신규 생성하지 않고 기존 `.harness-tmp/venv_05_unit1`, Docker `final-project-db`(포트 5544)를 재사용만 했다(내가 만든 것이 아니므로 삭제 대상 아님).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. uvicorn 프로세스(PID 18436, 포트 8051)를 `taskkill`로 종료하고 `curl http://127.0.0.1:8051/docs` → `000`(연결 거부)으로 재확인. 위 2개 임시 파일을 `rm -f`로 삭제 완료.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M backend/alembic/env.py
 M backend/app/api/v1/interviews.py
 M backend/app/main.py
 M backend/app/services/job_queue.py
 M docs/harness/traceability.md
 M frontend/app/globals.css
 M frontend/lib/api.ts
?? backend/alembic/versions/0df1434883f2_v3_transcripts.py
?? backend/alembic/versions/8a55fda78a42_v4_deletion_requests.py
?? backend/alembic/versions/b84a71b986c5_v6_code_submissions.py
?? backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py
?? backend/app/api/v1/code_submissions.py
?? backend/app/api/v1/consents.py
?? backend/app/api/v1/ops.py
?? backend/app/api/v1/whiteboard.py
?? backend/app/api/v1/ws.py
?? backend/app/models/code_submission.py
?? backend/app/models/deletion_request.py
?? backend/app/models/transcript.py
?? backend/app/models/whiteboard.py
?? backend/app/schemas/code_submission.py
?? backend/app/schemas/consent.py
?? backend/app/schemas/ops.py
?? backend/app/schemas/transcript.py
?? backend/app/schemas/whiteboard.py
?? docs/harness/units/unit-14-note.md
?? docs/harness/units/unit-18-note.md
?? docs/harness/units/unit-3-test.md
?? docs/harness/units/unit-4-note.md
?? frontend/app/admin/
?? frontend/app/interviews/
?? frontend/components/
?? frontend/tsconfig.tsbuildinfo
```
  위 목록에 이번 06단계 테스트가 만든 임시 아티팩트(`uvicorn_06_unit14.log`, `u14_06_token.txt`)는 더 이상 없음을 확인했다. 남아있는 `M`/`??` 항목들은 모두 unit-14의 05단계 정식 산출물(`consents.py`, `deletion_request.py`, `schemas/consent.py`, `main.py`/`alembic/env.py`/`traceability.md` 수정분, Alembic 리비전)이거나, 이 세션과 동시에 진행 중인 다른 작업 단위(unit-3/4/17/18 등)가 남긴 것으로 unit-14 담당 범위가 아니므로 임의로 건드리지 않았다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당. (단, 07 부채 사실은 아래 traceability.md 갱신에 기록함)

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). **단, 오케스트레이터 지시에 따라 07단계로 handoff하지 않는다** — traceability.md REQ-029/030 비고란에 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요"를 기록하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(오케스트레이터 지시). 다만 최소한의 자체 재확인은 다음과 같이 수행했다:
- 1차(인수조건 커버리지 확인): unit-14-note.md §4의 인수조건 11개 중, L1 규칙이 요구하는 "정상 경로 1~2케이스"에 해당하는 #1,#2,#3,#8,#9,#11 총 6개 항목이 TC-001/TC-002로 1:1 커버됨을 확인했다. 나머지 #4~#7,#10(경계/예외)은 의도적으로 이번 라운드 범위 밖으로 남기고 traceability.md에 명시했다(범위를 몰래 줄인 것이 아니라 근거를 남긴 것).
- 2차(과신 경계 재검토): "이 정상 경로 2케이스 통과만으로 다음 단계(08 정산 시 07)에 그대로 넘겨도 되는가"를 재검토한 결과, 넘길 수 없다고 판단했다 — 특히 인수조건 #6(타인 소유 403, 수평 권한 상승 차단)과 #10(인증 없음 401)은 보안에 직결되는 항목이라 07 정산 시 반드시 06단계가 아닌 07/08단계에서 재현·검증되어야 함을 traceability.md 비고에 명시적으로 남겼다. 이 재검토 자체가 "테스트가 놓쳤을 법한 경계 조건"에 대한 기록이다.
