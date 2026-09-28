# 테스트 결과서 (Test Result Report) — Feature G 통합테스트 (개인정보/동의 관리, REQ-029/REQ-030)

> `templates/test-report-template.md` 사용. 07단계 — unit-14가 남긴 "L1 부채"(traceability.md
> REQ-029/REQ-030 비고)를 정산한다. "07단계 통합테스트 부채 21건" 우선순위 진행분(#2) 계속.

## 1. 개요
- 테스트 대상: `backend/app/api/v1/consents.py`(동의 등록/철회/이력조회, 삭제요청 생성/조회)
- 테스트 유형: 통합(07단계)
- 적용 Tier: High
- 테스트 목적: unit-14-test.md(06단계, L1)가 정상 경로 2케이스만 검증하고 명시적으로
  제외했던 재철회 409, 존재하지 않는 id 404, 타인 소유 403, 잘못된 enum 422, 인증 없음
  401을 실측 검증
- 관련 산출물: `docs/harness/units/unit-14-note.md`/`unit-14-test.md`, `docs/harness/decisions.md`
  DEC-086
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: unit-14-test.md §2가 명시한 미검증 항목 전부(재철회 409, 존재하지 않는 id 404,
  타인 소유 403, 잘못된 enum 422, 인증 없음 401) + 나머지 3개 조회/삭제요청 엔드포인트의
  인증 없음 401(계약 일관성 확인)
- 제외 범위 및 사유: `biometric_voice` 동의의 실제 강제(`403 CONSENT_REQUIRED_VOICE`)는
  음성 turn 제출 경로(Feature C, REQ-004/005) 소관이라 이번 범위 밖 — Feature C 07
  진행 시 함께 확인 예정. 실제 하드 삭제(파기) 배치는 REQ-033(unit-15/21) 소관, 코드
  자체가 없어 테스트 대상 부존재(unit-14-test.md §2와 동일 사유).

## 3. 테스트 환경
- 로컬 backend(uvicorn, 포트 8000, `preview_start`), PostgreSQL(Docker, 기존 컨테이너)
- 테스트 데이터: `itG1-*`/`itG2-*` candidate 2명 — 종료 후 DB에서 전부 삭제

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-G01 | 인증 없이 동의 등록 | 401 | `401 AUTH_INVALID_TOKEN` | PASS |
| TC-G02 | 잘못된 `consent_type` enum | 422 | `422`, `enum` 위반 | PASS |
| TC-G03 | 존재하지 않는 id로 철회 | 404 | `404 NOT_FOUND` | PASS |
| TC-G04 | 타인 소유 동의 철회 시도(수평 권한 상승) | 403 | `403 AUTH_FORBIDDEN` | PASS |
| TC-G05 | 이미 철회된 동의 재철회 | 409 | `409 VALIDATION_ERROR`, "이미 철회된 동의입니다." | PASS |
| TC-G06 | `GET /users/me/consents` 인증 없음 | 401 | `401` | PASS |
| TC-G07 | `DELETE /users/me/biometric-data` 인증 없음 | 401 | `401` | PASS |
| TC-G08 | `GET /users/me/deletion-requests` 인증 없음 | 401 | `401` | PASS |

## 5. 커버리지
- unit-14-note.md 인수조건 #4~#7, #10(경계/예외 전부) 커버 완료 — REQ-029/030 인수조건 100%.

## 6. 결함(Defect) 목록
- 결함 없음 — TC-G01~08 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 신규 생성한 DB 레코드: candidate 2명 + consent 1건 — 종료 직후 DELETE, 재조회 0건 확인
- 기동한 프로세스: `preview_start("backend")` — `preview_stop`으로 종료
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(결함이 없어 코드 수정 없음)
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- `biometric_voice` 강제 게이트(403 CONSENT_REQUIRED_VOICE)는 Feature C 07단계에서
  함께 확인 필요(§2 참고).

## 9. 결론 및 판정
- [x] PASS — REQ-029/030의 "L1 부채" 정산 완료.

## 10. 내부 검증
- 1차: unit-14-note.md 미검증 인수조건과 TC-G01~08 1:1 대조 — 누락 없음.
- 2차: TC-G04(수평 권한 상승)와 TC-G03(존재하지 않는 id)을 분리해 각각 확인 — 소유권
  검사가 존재 여부 검사보다 먼저/나중에 실행돼 정보를 흘리지 않는지(404 우선 반환 후
  403 검사 순서, 코드 순서 확인) 재검토, `consents.py` 실제 코드 순서(404 우선 체크
  후 403)와 일치함을 확인.
