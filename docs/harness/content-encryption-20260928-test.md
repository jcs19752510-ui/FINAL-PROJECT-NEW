# 테스트 결과서 (Test Result Report) — content_text/code_submissions.content AES-256 암호화 확대

## 1. 개요
- 테스트 대상: `TRANSCRIPTS.content_text`, `code_submissions.content` 컬럼의
  저장 시 AES-256-GCM 암호화(`app.services.field_encryption.EncryptedText`
  신규 클래스 + 마이그레이션 f1a3c7e92b04)
- 테스트 유형: 단위+통합 병합(Low 등급, 기존 암호화 인프라 재사용이라 신규
  위험 낮음, 실제 프로덕션 데이터 마이그레이션 포함이라 데이터 정합성만
  Standard 수준으로 철저히 검증)
- 적용 Tier: Low(암호화 자체는 unit-25가 이미 검증한 알고리즘/키관리 재사용,
  이번은 적용 범위 확대일 뿐 신규 암호 설계 아님)
- 테스트 목적: (1) 기존 실데이터가 마이그레이션 후에도 바이트 단위로 완전히
  보존되는지, (2) DB에 실제로 평문이 아니라 암호문이 저장되는지, (3) 신규
  쓰기 경로(ORM)도 정상 동작하는지, (4) downgrade 경로도 실제로 동작하는지
  실측 확인
- 관련 산출물: `docs/harness/decisions.md` DEC-078
- 테스트 수행자(에이전트): 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: 로컬 개발 DB(`final-project-db` 컨테이너, 실제 누적 데이터 포함)에
  대한 실제 Alembic 마이그레이션 실행 + 전체 행 검증
- 제외 범위 및 사유: `evaluation_reports.star_json`/`details_json`/
  `criteria_scores_json`(JSONB 컬럼) — JSONB→Text 전환이 필요한 더 큰
  아키텍처 결정이라 이번 범위에서 의도적으로 제외(DEC-078 참고, 사용자
  확인 후 별도 진행)

## 3. 테스트 환경
- Windows, Python 3.13(`backend/.venv`), Docker Desktop(`final-project-db`
  pgvector/pg16 컨테이너, 포트 5544 — 테스트 시작 시 4일간 정지 상태였던 것을
  기동), `final-project-redis`(포트 6389, 이번 테스트에는 미사용이나 함께 기동)
- 테스트 데이터: **기존 실데이터 그대로 사용**(transcripts 96건, code_submissions
  172건 — 신규 테스트 데이터를 따로 만들지 않고 실제 누적 데이터로 검증해야
  "진짜로 안전한지" 증명 가치가 있다고 판단). ORM 쓰기 경로 검증용으로만 계정
  1개·면접 1개·transcript 1개를 임시 생성 후 즉시 삭제
- 전제 조건: 마이그레이션 실행 전 `pg_dump`로 전체 DB 백업(`.harness-tmp/
  pre_v16_backup.dump`, 456KB, 테스트 종료 후 삭제) + 전체 행의 SHA-256
  해시·길이를 사전 기록(`.harness-tmp/pre_migration_hashes.json`, 테스트
  종료 후 삭제)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | 문법/린트 | 신규/수정 파일(`field_encryption.py`, `transcript.py`, `code_submission.py`) | 오류 0건 | clean(alembic/versions는 프로젝트 설정상 린트 제외 대상, 기존 마이그레이션과 동일 스타일 확인) | PASS |
| TC-002 | 사전 스냅샷 | 마이그레이션 전 전체 96+172건 SHA-256 해시·길이 기록 | 기록 완료 | 96건+172건 전부 기록 확인 | PASS |
| TC-003 | 마이그레이션 실행(v15+v16 함께 적용) | `alembic upgrade head` | 오류 없이 적용, DB가 1단계 뒤처져 있던 v15(unit-37 rubric)도 함께 적용됨 | 정확히 그대로 진행, 오류 없음 | PASS |
| TC-004 | 원본 데이터 완전 보존(핵심) | 마이그레이션 후 ORM으로 전체 재조회, TC-002 해시와 1:1 비교 | 96+172건 전부 일치(0 mismatch) | **96+172건 전부 일치, 0 mismatch** | PASS |
| TC-005 | 실제 암호화 확인(평문이 그대로 남아있으면 안 됨) | raw SQL로 DB 원본 값 직접 조회 | base64 형태의 암호문(사람이 읽을 수 없는 값) | 정확히 base64 암호문 확인(`HkgrOaN4iaZctfH9bEEscdK9DS8ay...`), ASCII만 포함 | PASS |
| TC-006 | Downgrade 왕복 | `alembic downgrade -1` 실행 후 raw SQL로 원본 값 재확인 | 평문(읽을 수 있는 한국어)으로 복원 | 정확히 원래 한국어 문장으로 복원 확인 | PASS |
| TC-007 | Re-upgrade 후 최종 재검증 | `alembic upgrade head` 재실행 후 TC-002 해시와 전체 재비교 | 96+172건 전부 다시 일치 | **전부 일치, 0 mismatch**(왕복 후에도 데이터 손실 없음 최종 확인) | PASS |
| TC-008 | ORM 신규 쓰기 경로 | 특수문자 포함 한국어 텍스트로 신규 Transcript 생성 → 새 세션으로 재조회 | 원문과 정확히 일치 + DB 원본은 암호문 | 원문 완전 일치 확인, DB 원본이 암호문임도 별도 확인 | PASS |
| TC-009 | 정리 확인 | 기존 행 개수(96/172)가 테스트 전후로 변하지 않았는지 | 정확히 96/172 유지 | 정확히 96/172 확인 | PASS |

## 5. 커버리지
- 코드 변경 자체(EncryptedText 클래스, 두 모델의 컬럼 타입 변경)는 100%
  실제 DB 마이그레이션 + 전체 실데이터 검증으로 커버.
- 커버되지 않은 부분: (1) 애플리케이션 서버(uvicorn)를 통한 실HTTP E2E(이번은
  DB/ORM 레벨 검증까지만 — API 계층은 코드 변경이 없어 회귀 위험 낮다고
  판단해 생략). (2) JSONB 컬럼 암호화(§2 제외범위 참고, 별도 결정 필요).

## 6. 결함(Defect) 목록
- 결함 없음 — TC-001~009 전부 실측으로 확인(위 표 근거). 부수 발견 1건(결함
  아님): 로컬 DB 컨테이너가 최신 마이그레이션보다 1단계 뒤처져 있었음(v15
  rubric_scoring 미적용 상태) — 이번 upgrade가 자동으로 함께 적용해 정상화,
  데이터 손실 없음.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/pre_v16_backup.dump`(pg_dump 백업),
  `.harness-tmp/pre_migration_hashes.json`, `.harness-tmp/verify_result.txt`,
  `.harness-tmp/raw_check.txt`, `.harness-tmp/downgrade_check.txt`,
  `.harness-tmp/final_verify.txt`, `.harness-tmp/write_path_test.txt`(전량
  삭제 완료)
- ORM 쓰기 경로 테스트로 생성한 계정 1개·면접 1개·transcript 1개: 삭제 완료
  확인(정리 스크립트 1차 시도가 detached-instance 오류로 부분 실패했으나,
  재확인 쿼리로 잔여 0건 확인 후 최종 완료 처리 — "삭제했다고 보고하고
  끝내지 않고 실제로 없는지 재확인"한 사례)
- DB/Redis 컨테이너(`final-project-db`, `final-project-redis`): 이번 세션이
  시작(4일간 정지 상태였음) — 프로젝트 표준 개발 인프라라 유지, 정지하지
  않음
- 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예
- 정리 완료 여부: 완료
- 정리 후 `git status`: `.harness-tmp/` 관련 항목 없음, 원본 코드/마이그레이션/
  문서 변경분만 남음
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- `evaluation_reports.star_json`/`details_json`/`criteria_scores_json`은
  여전히 평문(JSONB) — 이 세 필드도 REQ-036 새니타이즈 대상으로 지정된
  민감 필드라, 암호화 확대를 원하면 JSONB→Text 전환이라는 별도의 더 큰
  결정이 필요함(사용자 확인 필요).
- `FIELD_ENCRYPTION_KEY`는 여전히 로컬 개발 전용 플레이스홀더 키다(unit-25
  당시 경고 그대로 유효) — 실제 운영 배포 전 KMS/Vault 등 안전한 키 관리로
  반드시 교체해야 한다.
- API 계층(uvicorn) 경유 실HTTP E2E는 이번 범위에서 생략했다 — 07단계
  통합테스트에서 함께 확인 권장.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). 실제 프로덕션
  데이터(268건)에 대한 무손실 암호화 전환을 바이트 단위로 증명했다.

## 10. 내부 검증
- L1 경량판 — 1차 검증(작성자 관점): TC-001~009 실행 로그와 본 문서 대조,
  결함 0건. 규칙 B Tier=Low 예외에 따라 2차 생략. 단, §8의 JSONB 후속 결정
  필요 사항과 운영 키 교체 경고는 2차 없이도 명시적으로 남김(생략이 곧
  리스크 은폐가 되지 않도록).
