# 테스트 결과서 (Test Result Report) — unit-25

## 1. 개요
- 테스트 대상: TLS 1.3 전송 암호화(nginx 샘플 설정 + 앱 계층 보안 헤더) + AES-256
  저장 암호화(`field_encryption.py`, `consents.ip_address` 적용)
- 테스트 유형: 단위+통합 병합(Low 등급)
- 적용 Tier: Low(신규 인프라 모듈 + 기존 컬럼 1개 타입 전환, 스키마 계약 자체는
  API 응답을 바꾸지 않음 — `ip_address`는 애초에 API로 노출된 적 없음)
- 적용 속도 트랙: L1(경량판), 표준 수준으로 채움
- 테스트 목적: (1) AES-256-GCM 암호화 모듈 자체의 정확성/변조탐지, (2) 기존
  평문 데이터 699건이 마이그레이션으로 안전하게 전환되는지, (3) 실제 API 신규
  쓰기도 암호화되는지, (4) 서버 응답에 보안 헤더가 올바른 조건에서만 붙는지
- 관련 산출물: `unit-25-note.md`, 원 계획서 §3.2.2(REQ-N-001/003)
- 테스트 수행자(에이전트): 본 세션(05+06 역할 겸임)
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위: AES-256-GCM 라운드트립/논스랜덤화/변조탐지, 컬럼 폭(IPv6 최장 케이스),
  Alembic upgrade(데이터 마이그레이션 포함)/downgrade 라운드트립, 실제 HTTP
  API로 생성한 신규 레코드의 DB 저장값 확인, 보안 헤더 조건부 로직(true/false
  양쪽 분기) 실측
- 제외 범위 및 사유: (1) nginx 샘플 설정 자체의 실제 TLS 핸드셰이크 — 이 환경에
  실제 도메인/인증서가 없어 문법 검토(nginx 표준 지시어만 사용, 커스텀 구문
  없음)로 갈음. (2) `content_text` 등 다른 컬럼 암호화 — unit-25-note.md §1
  사유로 이번 범위에서 의도적으로 제외.

## 3. 테스트 환경
- Windows, Python 3.13(backend/.venv), PostgreSQL(Docker `final-project-db`,
  5544, 기존 개발 DB — `consents` 테이블에 실제 존재하던 699건의 평문 IP 포함),
  신규 uvicorn 프로세스(포트 8303, 8304)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | 문법/린트 | `py_compile`+`ruff check` 신규/수정 파일 전체 | 오류 0건 | 최초 1건(미사용 `String` import) 발견→제거→clean | PASS |
| TC-002 | 암호화 라운드트립 | `encrypt_field`→`decrypt_field` | 원문 복원 | 정확히 일치 | PASS |
| TC-003 | 논스 랜덤화 | 같은 평문 2회 암호화 | 암호문이 매번 다름, 둘 다 정상 복호화 | 암호문 상이, 둘 다 원문 복원 성공 | PASS |
| TC-004 | 변조 탐지 | 암호문 마지막 문자 1개 변경 후 복호화 시도 | `FieldEncryptionError` 발생(GCM 태그 검증 실패) | 정확히 예외 발생, 평문 유출 없음 | PASS |
| TC-005 | 컬럼 폭 여유 | IPv6 최장 표기(`2001:0db8:...`) 암호화 | 암호문 길이 ≤255 | 92자, 여유 있음 | PASS |
| TC-006 | 기존 데이터 마이그레이션 | `alembic upgrade head`(v13) 실행 | 699건 전부 암호화되어 평문이 DB에 남지 않음 | DB 직접조회로 암호문(52자 base64) 확인, 평문 흔적 없음 | PASS |
| TC-007 | ORM 투명 복호화 | 마이그레이션 후 ORM으로 기존 레코드 3건 조회 | 원래 IP(127.0.0.1)로 정확히 복호화 | 3건 전부 정확히 일치 | PASS |
| TC-008 | Alembic downgrade 데이터 보존 | `downgrade -1` 실행 | 암호문이 평문으로 복원되고 컬럼 폭 원복 | 3건 샘플 확인 — 정확히 원래 IP로 복원 확인, 이후 `upgrade head`로 재적용해 최종 상태 head 유지 | PASS |
| TC-009 | 실제 API 신규 쓰기 | 신규 계정 등록→로그인→`POST /consents` | DB에 암호문 저장, ORM으로는 평문 복호화 | 암호문 52자 확인, ORM 복호화 시 `127.0.0.1` 정확 | PASS |
| TC-010 | 보안 헤더 — 로컬(cookie_secure=false) | `curl -D -` 로 `/health` 응답 헤더 확인 | HSTS 없음, 나머지 3개 헤더는 있음 | 정확히 일치(X-Content-Type-Options/X-Frame-Options/Referrer-Policy 존재, HSTS 부재) | PASS |
| TC-011 | 보안 헤더 — 운영모드(COOKIE_SECURE=true) | 동일 서버를 `COOKIE_SECURE=true`로 기동 후 확인 | HSTS 포함 4개 전부 | `strict-transport-security: max-age=63072000; includeSubDomains; preload` 확인 | PASS |
| TC-012 | CORS 회귀 없음 | `Origin` 헤더 포함 요청 | 기존 CORS 헤더(`access-control-allow-origin` 등)가 보안 헤더 미들웨어 추가 후에도 정상 | 정확히 함께 존재 확인(미들웨어 순서 문제 없음) | PASS |

## 5. 커버리지
- L1이나 표준 수준. 신규 경로(암호화 모듈 전체, 마이그레이션 upgrade/downgrade,
  API 신규쓰기, 헤더 조건부 분기 양쪽) 전량 실제 실행 커버.
- 커버되지 않은 부분: nginx 실제 TLS 핸드셰이크(2절 사유), 다른 컬럼으로의
  암호화 확장(의도적 범위 제외).

## 6. 결함(Defect) 목록
- 결함 없음. 근거: TC-001에서 발견한 미사용 import 1건은 기능 결함이 아니라
  린트 스타일 이슈로 즉시 수정, 4절 전 케이스(TC-002~012) PASS로 기능적 결함
  없음을 확인.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/unit25_uvicorn.log`,
  `.harness-tmp/unit25b_uvicorn.log`(둘 다 삭제 완료), 신규 uvicorn 프로세스 2개
  (포트 8303/8304, 각각 `taskkill`로 종료 확인), DB 테스트 계정 1개+동의 1건
  (`unit25-cand@example.com`, 삭제 완료 — `consents=1 users=1`)
- **주의**: 기존 실서비스(또는 이전 세션) 데이터였던 `consents.ip_address` 699건은
  이번 마이그레이션으로 **암호화된 상태로 영구 변경**됐다 — 이는 테스트 부산물이
  아니라 이 유닛의 실제 목적(저장 시 암호화)이므로 되돌리지 않았다(정상 동작).
- 전부 `.harness-tmp/` 하위에서만 생성: [x] 예
- 정리 완료 여부: 완료
- 정리 후 git status: 사용자 지시("Git 작업 금지")로 미실행(unit-24부터 동일
  방침 유지)
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- **키 관리**: `FIELD_ENCRYPTION_KEY`가 현재 `.env`(로컬)에 평문으로 존재 —
  운영 배포 전 KMS/Vault 등으로 반드시 교체해야 한다(모듈 docstring에도 명시).
  이 세션은 로컬 개발 키를 생성해 넣었을 뿐 운영 키 관리 체계를 구축하지 않았다.
- **"모든 데이터" 암호화 미완**: `content_text` 등 핵심 컬럼은 의도적으로 제외
  (1절 사유) — 인코딩 손상 결함 해결 후 확장 필요.
- **키 분실/교체 시 복호화 불가**: GCM의 특성상 키가 바뀌면 기존 암호문은
  복호화 불가능(재암호화 마이그레이션 필요) — 키 로테이션 절차는 이번 범위에서
  설계하지 않음(운영 설계 시 별도 필요).
- nginx 샘플은 실제 인증서/도메인으로 교체 전까지 "참고용"이며 자동 적용되지 않음.

## 9. 결론 및 판정
- [x] PASS

## 10. 내부 검증
- L1 경량판 — 검증 생략. 핵심 리스크(데이터 마이그레이션 안전성)는 upgrade/
  downgrade 양방향 실측(TC-006~008)으로 이중 확인함.
