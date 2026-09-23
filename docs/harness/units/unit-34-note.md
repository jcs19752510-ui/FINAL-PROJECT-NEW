# unit-34 구현 노트 — GDPR/CCPA 남은 기술 조각 (적법근거 필드 + CCPA 고지 + 법률고지 정합성 수정)

- 작성 에이전트: 본 세션, 작성일: 2026-09-23
- 배경: unit-33-note.md §5 "적법근거 기록·CCPA 고지문 등 나머지는 미착수,
  비교적 작은 범위이니 우선순위가 있다면 후속 유닛으로 바로 착수 가능"의
  실제 착수분. 사용자가 "10개 중 바로 작업 가능한 것"으로 지목.

## 1. 구현 범위

- `backend/app/models/consent.py`: `LawfulBasis` StrEnum(GDPR 제6조 6종) +
  `Consent.lawful_basis` 컬럼(NOT NULL, 기본값 `consent`). 기존 699건 전부
  실측으로 `consent`값이 정상 채워짐을 확인.
- `backend/app/schemas/consent.py`: `ConsentOut.lawful_basis` 노출.
- `backend/alembic/versions/d4f7b2c8a913_v14_consent_lawful_basis.py`: 신규
  마이그레이션(unit-23이 겪은 "ENUM 타입 선행 생성" 교훈 적용, 처음부터 결함
  없이 한 번에 성공).
- `frontend/lib/complianceContent.ts`:
  1. **정합성 버그 수정**: 기존 문구가 "AI가 자동으로 합격/불합격을 확정하는
     기능은 존재하지 않습니다"라고 단정했는데, unit-23이 `pass_fail_
     recommendation` 필드를 실제로 추가해 이 문구가 **사실과 어긋나 있었다**
     — 법률 고지 문구가 실제 시스템 동작과 불일치하는 것은 방치하면 안 되는
     문제라 우선 수정. "참고용 의견일 뿐 법적 구속력 없음"으로 문구 교체 +
     REQ-031 법률 검토 필요 사실 명시.
  2. CCPA "개인정보를 판매/공유하지 않는다" 고지 문구 추가, GDPR/CCPA 해외
     이용자 대상 서비스 확장 시 별도 법률 검토 필요 사실 명시.

## 2. 실측 검증 요약(상세는 unit-34-test.md)

마이그레이션 upgrade/downgrade 라운드트립 성공, 기존 699건 기본값 확인, 실제
HTTP로 `POST /consents` 응답과 `GET /users/me/data-export`(unit-33) 응답 양쪽
모두에 `lawful_basis:"consent"`가 정확히 나타남을 확인(두 기능이 자연스럽게
연동됨 — 별도 배선 없이 스키마 확장만으로 데이터 이동권 응답에도 반영됨).

## 3. 왜 이것으로 "GDPR/CCPA 완료"가 아닌가

이 유닛은 unit-33-note.md §2 갭 분석표의 "❌ 미구현" 항목 중 기술적으로 작은
것 2개(적법근거 기록, CCPA 판매안함 고지)만 채웠다. 여전히 남은 것: 국외 이전
안전조치, DPO 지정 여부 — 둘 다 **코드가 아니라 법적 판단**이 선행되어야
한다. ③ 매트릭스에는 계속 "부분착수"로 유지한다.
