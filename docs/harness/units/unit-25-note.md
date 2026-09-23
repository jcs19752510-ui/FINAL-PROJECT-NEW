# unit-25 구현 노트 — 원안(REQ-N-001/003 축소판) TLS 1.3 + AES-256 암호화

- 작성 에이전트: 본 세션(05+06 역할 겸임), 작성일: 2026-09-22
- 원 계획서 §3.2.2: "모든 데이터는 전송 시(TLS 1.3) 및 저장 시(AES-256)
  암호화되어야 하며 ... 사용자가 원할 경우 즉시 영구 삭제 가능한 기능을 제공해야
  한다"

## 1. 스코프 결정 (왜 "모든 데이터"가 아닌가)

"모든 데이터"를 문자 그대로 이번 유닛에서 암호화하지 않았다. 이유:

1. **`TRANSCRIPTS.content_text`는 별도로 발견된 인코딩 손상 결함(unit-24-note.md
   §3)의 조사 대상이다.** 손상 여부/원인이 불명확한 컬럼에 암호화를 먼저 씌우면
   (a) 손상된 데이터가 "정상적으로 암호화된 손상 데이터"로 굳어 이후 조사를
   더 어렵게 만들고, (b) 손상 여부를 판별하는 방법 자체(원문 대조)가 복잡해진다.
   사용자 지시("현재 작업 마무리 후 추가 작업")에 따라 이 결함은 이번 6개 항목
   이후 별도로 다룬다 — 그 전에 이 컬럼을 건드리지 않는 것이 안전하다.
2. 나머지 컬럼(예: `code_submissions.content`, `evaluation_reports.star_json`)도
   같은 이유로 이번 범위에서 제외했다 — LLM/리포트 파이프라인과 얽혀 있어 손상
   결함 조사 전 손대면 같은 위험이 있다.
3. 대신 **재사용 가능한 AES-256-GCM 암호화 인프라**(`EncryptedString`
   `TypeDecorator`)를 만들고, 그 파이프라인과 완전히 무관한 필드(`consents.
   ip_address`, 애초에 API로도 노출되지 않는 내부 감사 전용 컬럼)에 실제로
   적용해 "동작하는 예시"로 검증했다. 향후 콘텐츠 손상 결함이 해결되면 다른
   컬럼도 `EncryptedString(N)`으로 타입만 바꾸면 된다(마이그레이션은 매번 필요).

**[2026-09-23 정정, DEC-051]** 위 1번의 전제("`content_text` 인코딩 손상
결함")는 재조사 결과 **오탐(실제 손상 아님, 콘솔 표시 오류)**으로 판정됐다.
`content_text`/`code_submissions.content`/`evaluation_reports.star_json`을
암호화 범위에서 뺀 이유 자체는 이제 사라졌다 — 다만 이 정정 시점에는 이미
06단계까지 PASS 확정된 산출물이라 임의로 범위를 넓히지 않고, **암호화 범위
확대는 사용자가 원할 때 별도 후속 유닛으로 진행**하기로 했다(재작업 아님,
신규 착수 대상으로 분류). 상세 근거는 `decisions.md` DEC-051 참고.

## 2. 구현 범위

- `backend/app/services/field_encryption.py`(신규): AES-256-GCM
  encrypt/decrypt + `EncryptedString` TypeDecorator.
- `backend/app/core/config.py`: `field_encryption_key` 설정(base64 32바이트,
  redis_url과 동일한 "로컬 개발 전용 placeholder, 운영 전 교체 필수" 패턴).
- `backend/.env`/`.env.example`: `FIELD_ENCRYPTION_KEY` 추가(키 생성 명령 포함).
- `backend/app/models/consent.py`: `ip_address`를 `EncryptedString(255)`로 전환
  (기존 `String(64)`에서 폭 확장 — 암호화 오버헤드 감안).
- `backend/alembic/versions/c9e451f3a708_v13_consent_ip_encryption.py`: 컬럼 폭
  확장 + **기존 평문 IP 699건을 같은 키로 암호화해 덮어쓰는 데이터 마이그레이션**
  (스키마만 바꾸면 기존 행이 전부 복호화 실패하므로 필수).
- `backend/deploy/nginx.conf.sample`(신규): TLS 1.3 종단, HTTP→HTTPS 강제
  리다이렉트, HSTS, WS 업그레이드 프록시 설정 포함하는 배포 참고 설정.
- `backend/app/main.py`: `_security_headers_middleware` 추가 — HSTS(운영에서만,
  `cookie_secure` 재사용) + X-Content-Type-Options + X-Frame-Options +
  Referrer-Policy.

## 3. "일치" 판정 기준 관련 유의사항

이 유닛으로 ②비교표의 "보안/규정" 행이 완전한 "일치"가 되지는 않는다 — 원안은
"모든 데이터"를 요구했으나 이번엔 감사용 필드 1개만 실제로 암호화했다. ②표는
이 유닛 완료 후 사용자 요청 시 "부분 이행 확대"로 갱신 가능(아티팩트 갱신은
6개 항목 전체 완료 후 일괄 진행 예정, 대화 내 기존 지시 참고).
