# unit-15 구현 노트 — Feature G. 규제 컴플라이언스 (REQ-031~034)

**속도 트랙: L1** (오케스트레이터 지시). 06/07단계는 L1 경량판 절차(정상경로 중심, 예외경로는 부채로 명시 후 07/08 착수 전 정산)를 따르면 된다.

## 0. 이전 시도 재사용 여부

직전 세션이 API rate limit로 게이트1 실행 직전에 중단되었다. 재개 시점에 다음 파일이 이미 완성된 상태로 존재함을 확인했고, 코드/문서 내용을 전부 재검토(Read)한 뒤 그대로 이어받아 사용했다 — 처음부터 다시 만들지 않았다:

- `frontend/lib/complianceContent.ts` (사전고지/법률고지 정적 문구)
- `frontend/app/interviews/[id]/consent/page.tsx`, `consent.module.css` ([C-04])
- `frontend/app/legal/page.tsx`, `legal.module.css` ([C-14])
- `frontend/app/mypage/page.tsx`, `mypage.module.css` ([C-13])
- `frontend/lib/api.ts`의 Consent/DeletionRequest 관련 타입·함수 (`createConsent`, `revokeConsent`, `listMyConsents`, `requestBiometricDataDeletion`, `listMyDeletionRequests`)

이번 세션에서 실제로 변경한 것은 `frontend/app/mypage/page.tsx` 마운트 `useEffect` 1곳뿐이다(게이트1에서 발견된 lint 에러 수정, 아래 §3 참고). 나머지는 이전 시도 결과물을 코드 리뷰 후 그대로 승인했다.

## 1. 구현 범위

1. **사전고지 화면** (`/interviews/[id]/consent`, [C-04], REQ-031/032):
   - AI 면접 진행/평가 사실 고지, "AI는 보조 도구 — 최종 채용 결정은 사람이 내린다" 원칙, 개인정보 항목별 보관기간(음성원본=STT 완료 즉시삭제, transcript/리포트=180일 임시값), 동의철회/삭제요청 안내, 법률자문 권고 문구를 `PRE_NOTICE_TEXT`(정적 텍스트, 스크롤 박스)로 노출.
   - 고지문을 끝까지 스크롤해야 필수 체크박스(`ai_interview_notice`)가 활성화(04-ux-design [C-04] 명세). 선택 체크박스(`biometric_voice`)는 스크롤과 무관하게 체크 가능.
   - "동의하고 시작" 클릭 시 `POST /consents`(`ai_interview_notice`, 필수) → (선택 시) `POST /consents`(`biometric_voice`, 실패해도 흐름을 막지 않고 배너로만 알림) → `POST /interviews/{id}/start` 순서로 호출.
   - 법률/컴플라이언스 고지 전문 링크(`/legal`)를 하단에 노출(REQ-034).

2. **법률/컴플라이언스 고지 화면** (`/legal`, [C-14], REQ-034): 로그인 여부와 무관하게 항상 열람 가능한 정적 페이지. `LEGAL_DISCLAIMER_TEXT`에 "결과는 참고용, 법적 효력 없음", "법률 자문 대체 불가, 전문가 자문 권고", "AI는 보조 도구 — 최종 결정은 사람" 원칙을 재수록.

3. **마이페이지 동의 관리** (`/mypage`, [C-13], REQ-030/033):
   - `GET /auth/me`, `GET /users/me/consents`, `GET /users/me/deletion-requests`를 병렬 조회해 계정 정보/동의 이력 테이블/삭제요청 이력 테이블 표시.
   - 동의 이력 행마다 "철회" 버튼 → `POST /consents/{id}/revoke`, 철회 후 목록 재조회.
   - "생체정보(음성) 즉시 삭제 요청" 버튼 → 2단계 확인 UI → `DELETE /users/me/biometric-data`, 처리 중/완료 상태를 이력 테이블에 표시.

## 2. 설계서 대비 편차 (사유 포함)

- **`GET /interviews/{id}/pre-notice`, `GET /legal/disclaimer` 미구현**: 03-system-design.md v3 §4.2가 정의한 두 엔드포인트를 어떤 유닛도 구현하지 않았고, 이번 세션은 `backend/app/api/v1/interviews.py` 등 백엔드 파일 수정이 명시적으로 범위 밖이라 신규 백엔드 엔드포인트를 추가할 수 없었다. 대신 고지문/법률고지문을 `frontend/lib/complianceContent.ts`의 정적 텍스트로 프런트에 직접 둔다. 두 화면 모두 "정적 법정 고지문"이라는 성격상 서버 조회가 필수는 아니어서 기능상 치명적이지 않지만, 추후 문구를 서버에서 관리하고 싶다면(예: 버전 관리, 다국어) 별도 유닛에서 두 엔드포인트를 만들고 이 두 페이지가 그걸 소비하도록 바꿔야 한다.
- **보관기간 180일은 확정값이 아님**: 03-design §6.2 원문 그대로 "법률자문 확인 필요" 임시값을 그대로 사용했다(`RETENTION_DAYS_PROVISIONAL = 180`, `frontend/lib/complianceContent.ts`). 화면 문구에도 "아직 법률자문을 거치지 않은 임시값"이라고 숨기지 않고 명시했다 — 사용자를 속이지 않는다는 원칙을 우선했다.
- **자동 파기(하드 삭제) 배치 미구현 (REQ-033 일부)**: 03-design §7.4가 요구하는 Celery beat 배치 잡("delete_requested_data")은 `DELETION_REQUESTS.status`를 `pending → completed`로 전이시키는 백엔드 로직인데, 이번 세션은 백엔드 파일을 수정할 수 없는 범위 제약을 받아 구현하지 않았다(unit-14-note.md도 이 배치를 REQ-033/unit-15의 후속 책임으로 이미 명시해둔 상태였다). 마이페이지 삭제요청 이력 화면은 `status` 값을 그대로 표시하므로 배치가 없으면 모든 요청이 "처리 중"으로 계속 보인다 — 기능 결함이 아니라 배치 미구현의 자연스러운 결과다.
- **REQ-031 스키마 강제 부분 미해당**: REQ-031의 "합격/불합격 확정 필드 자체를 스키마에 만들지 않는다"는 `EVALUATION_REPORTS` 테이블 설계에 관한 요구인데, 그 테이블 자체가 아직 없다(unit-10/11 미착수, `backend/app/schemas/recruiter.py` 주석에서도 확인). 이번 유닛은 "원칙을 문구로 고지"하는 부분만 커버했고, 스키마 레벨 강제는 해당 테이블이 생기는 시점에 재검토가 필요하다.
- **DEC-023 재확인**: 텍스트 전용 지원자는 `biometric_voice` 동의 없이 "동의하고 시작" 버튼이 활성화된다(필수 체크박스는 `ai_interview_notice`뿐). 실제 음성 제출 차단은 unit-4/5의 `/turns` 실시간 재조회 책임이며 이 화면은 관여하지 않는다.

## 3. 게이트1 — 정적 분석/린트

- 프로젝트에 ESLint(`npm run lint` → `eslint .`)와 TypeScript(`tsc --noEmit`)가 설정되어 있어 둘 다 실행했다. 백엔드는 이번 세션에서 파일을 수정하지 않았으므로 ruff는 실행하지 않았다(수정 없는 파일에 대한 린트는 이 유닛의 책임 범위가 아님).
- 최초 실행 시 `frontend/app/mypage/page.tsx`에서 `react-hooks/set-state-in-effect` 에러 발견: 마운트 `useEffect`가 `useCallback`으로 메모이즈된 `loadAll(accessToken)`을 직접 호출하는 패턴이 "effect 안에서 setState를 동기 호출"로 플래그됨(같은 패턴이라도 effect 내부에 인라인으로 정의한 `async function`을 호출하는 경우는 플래그되지 않음을 최소 재현으로 확인). `useEffect` 본문을 인라인 `async function run() { await loadAll(accessToken!); } run();`로 감싸 수정.
- 수정 후 재실행 결과: `npm run lint` → 0 errors, 1 warning(`app/interviews/new/page.tsx`의 `<a>` 태그 경고 — 이 유닛이 만들지 않은 다른 파일이라 범위 밖, 손대지 않음). `npx tsc --noEmit` → 에러 없음. `npm run build`(Next.js production build) → 성공, `/legal`·`/mypage`는 정적(○), `/interviews/[id]/consent`는 동적(ƒ) 라우트로 정상 생성됨.
- 게이트1 **통과**.

## 4. 게이트2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 04-ux-design.md v2 §2 [C-04]/[C-13]/[C-14] 명세(스크롤 완독 게이트, 동의 이력 테이블, 삭제요청 확인 다이얼로그 등)와 코드가 1:1 대응함을 라인 단위로 재확인했다.
- [x] 에러 처리가 누락된 경로가 없는가 — 401(로그인 리다이렉트), 403(`CONSENT_REQUIRED_NOTICE` 재동의 유도), 409(충돌 메시지 노출), 네트워크 오류(공통 배너) 모두 처리. `biometric_voice` 선택 동의 실패 시에도 조용히 삼키지 않고 배너로 알린 뒤 필수 흐름은 계속 진행(주석으로 의도 명시).
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 유닛은 자유 텍스트 입력 폼이 없고(체크박스/버튼뿐) 서버 응답은 `ApiError`를 통해 상태코드별로 분기 처리한다. 별도 클라이언트 검증 로직이 필요한 입력 필드는 없음.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(정적 문구·API 호출만).
- [x] 새로 추가한 외부 의존성이 있는가 — 없음. 신규 npm/pip 패키지를 추가하지 않았다(백엔드 로컬 실행 환경에 기존 `requirements.txt`의 `python-jose`, `psycopg` 등이 누락되어 있어 curl 검증을 위해 로컬 python 환경에 설치했으나, 이는 이미 `requirements.txt`에 명시된 기존 의존성을 로컬 환경에 맞춘 것이지 신규 의존성 추가가 아니다.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `git status`로 변경 파일을 재확인: 이번 세션에서 실제로 diff가 발생한 파일은 `frontend/app/mypage/page.tsx`(lint 수정), `docs/harness/traceability.md`(REQ-031~034 갱신), 본 노트 파일뿐이다. `consents.py`/`interviews.py`/`ops.py` 등 백엔드 파일, 다른 유닛의 프론트 파일(면접장/코드에디터/웹캠/화이트보드/운영자/recruiter)은 일절 수정하지 않았다.

## 5. 수동 확인 필요 부분 (6단계 인계)

- 브라우저 실제 조작 자동화 도구가 이 환경에 없어, 스크롤 완독 → 체크박스 활성화 → "동의하고 시작" 클릭까지의 UI 흐름은 코드 리뷰로만 검증했고 실제 브라우저(또는 headless 자동화)로 재현하지 못했다. 06단계에서 실제 브라우저로 재현 필요.
- 마이페이지의 "생체정보 즉시 삭제 요청" 2단계 확인 UI(확인/취소 버튼 토글)도 동일하게 코드 리뷰로만 검증했다.
- 백엔드 API 자체(`POST /consents`, `POST /consents/{id}/revoke`, `GET /users/me/consents`, `DELETE /users/me/biometric-data`, `GET /users/me/deletion-requests`)는 로컬에서 uvicorn 기동 후 신규 candidate 계정으로 curl 전체 플로우(등록→로그인→동의생성→목록조회→철회→삭제요청→이력조회)를 직접 실행해 200/201/202 응답과 필드값(`revoked_at`, `status=pending` 등)을 확인했다(수정은 하지 않음, 재확인만).

## 6. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

1. `/interviews/{id}/consent` 접속 시(상태가 `scheduled`인 세션), 고지 박스를 끝까지 스크롤하기 전에는 필수 체크박스가 비활성화(disabled)여야 한다. 끝까지 스크롤하면 활성화된다.
2. 필수 체크박스만 체크한 상태(선택 체크박스 미체크)에서 "동의하고 시작" 클릭 시: `POST /consents {consent_type: "ai_interview_notice"}` → `POST /interviews/{id}/start` 순서로 호출되고, 성공 시 `/interviews/{id}`로 이동해야 한다.
3. 선택 체크박스(`biometric_voice`)까지 체크한 경우, `ai_interview_notice` 동의 후 `biometric_voice` 동의도 등록되어야 하며, 이 호출이 실패해도(예: 네트워크 오류 모킹) 세션 시작 흐름은 막히지 않고 배너 경고만 떠야 한다.
4. 세션 상태가 이미 `live`/`paused`이면 이 화면은 자동으로 `/interviews/{id}`로 리다이렉트되어야 하고, `completed`/`expired` 등이면 "이미 종료/만료" 오류 메시지를 보여줘야 한다(재로그인 없이 401이면 `/login`으로 이동).
5. `/legal` 페이지는 로그인 여부와 무관하게 접근 가능해야 하며, "AI는 보조 도구", "법적 효력 없음", "전문가 자문 권고" 문구가 모두 표시되어야 한다.
6. `/mypage`는 미로그인 시 `/login`으로 리다이렉트되어야 한다. 로그인 상태에서는 동의 이력 테이블에 `granted_at`/`revoked_at`이 표시되고, 철회되지 않은 동의만 "철회" 버튼이 활성화되어야 한다.
7. "철회" 클릭 → `POST /consents/{id}/revoke` 성공 후 해당 행이 "철회됨"으로 즉시 갱신되어야 한다(재조회 반영).
8. "생체정보 즉시 삭제 요청" → 확인 다이얼로그 → "확인" 클릭 시 `DELETE /users/me/biometric-data` 호출 후 삭제요청 이력 테이블에 새 행(`target=biometric_only`, `status=pending`, "처리 중 — 24시간 이내 완료 예정")이 추가되어야 한다. "취소" 클릭 시 아무 API도 호출되지 않아야 한다.
9. 사전고지 문구(`PRE_NOTICE_TEXT`)와 법률고지 문구(`LEGAL_DISCLAIMER_TEXT`) 모두 "보관기간 180일은 법률자문 미확정 임시값"이라는 문장을 포함해야 한다(값 자체의 정확성이 아니라 "임시값임을 숨기지 않는다"는 조건 검증).
10. (부채, 07/08 이전 정산 필요) 존재하지 않는 `consent_id` 철회 시도(404), 타인 소유 동의 철회 시도(403), 이미 철회된 동의 재철회 시도(409) 등 예외 경로는 이번 05단계에서 프런트 코드 리뷰로만 다루었고 06단계가 아직 독립 재현하지 않았다.

## 7. 변경 이력 (재작업)

- **2026-09-19, DEF-001 재작업 (규칙 F)**: unit-15-test.md 06단계 검증에서 `LEGAL_DISCLAIMER_TEXT`(43~58행)에 "보관기간 180일은 법률자문 미확정 임시값" 취지의 문장이 누락되어 인수조건 #9를 위반한다는 FAIL 판정(DEF-001, High)을 받았다. `frontend/lib/complianceContent.ts`의 `LEGAL_DISCLAIMER_TEXT` 마지막 문단에 "현재 안내 중인 보관기간 ${RETENTION_DAYS_PROVISIONAL}일은 아직 법률자문을 거치지 않은 임시값이며, 실제 운영 정책은 추후 법률 검토 후 확정됩니다."를 추가해 `PRE_NOTICE_TEXT`와 동일한 취지를 반영했다. 이 파일 외 다른 파일은 수정하지 않았다(범위 외 변경 금지 준수). 수정 후 `grep -n "180\|임시값" frontend/lib/complianceContent.ts`로 `PRE_NOTICE_TEXT`(27~30행)와 `LEGAL_DISCLAIMER_TEXT`(신규 59행)에 모두 해당 문장이 존재함을 재확인했고, `npm run lint`(0 errors, 기존과 동일한 무관 warning 1건만 유지)와 `npm run build`(성공, 라우트 구성 동일)를 재실행해 게이트1을 재통과시켰다. 인수조건 #9 문구는 변경하지 않았으며, 그대로 재검증 기준으로 유효하다.
