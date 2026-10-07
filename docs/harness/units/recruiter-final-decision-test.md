# 테스트 결과서 (Test Result Report) — 면접 완료 건 최종 합격/불합격 처리 + 안내 메일 자동 발송

> `templates/test-report-template.md` 사용. DB 스키마 변경·권한·메일 발송이 걸린 기능이라 정식(10섹션) 강도로 작성했다.

## 1. 개요
- 테스트 대상:
  - 백엔드: `backend/app/api/v1/recruiter_final_decision.py`(신규 3개 엔드포인트), `backend/app/models/interview.py`, `backend/app/schemas/recruiter.py`, `backend/app/api/v1/recruiter.py`(상세 응답 필드 추가), `backend/alembic/versions/a5d2c8e1f7b3_v18_interview_final_decision.py`
  - 프런트: `frontend/app/recruiter/[id]/page.tsx`(최종 합격/불합격 영역), `frontend/lib/api.ts`
- 테스트 유형: 단위+통합 (백엔드는 실제 PostgreSQL + 실제 HTTP 서버, 프런트는 브라우저 E2E에 API 모킹)
- 적용 Tier: High (DEC-002). 적용 속도 트랙: L4 (스키마 변경 + 외부 메일 발송 + 권한)
- 테스트 목적: 사용자 요청 "면접 완료 건에 이력서 합격 처리와 동일한 최종 합격/불합격 처리를 추가하고, 합격 여부 안내 메일을 이력서 처리와 동일하게 발송"이 요구 결정 4건(최종 전용 문구, 드롭다운 신규 문구, 일정 입력 제외, 1회 처리 후 변경 불가)대로 동작하는지 확인
- 관련 산출물: `개발작업내용/면접최종합격불합격처리_20261007_1130.md`, DEC-120(`docs/harness/decisions.md`), 기준 구현 DEC-116(`recruiter_resumes.py::decide_resume`)
- 테스트 수행자: Claude (본 세션 직접 수행)
- 테스트 일시: 2026-10-07 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): 처리 API 성공/실패 경로, 상태·권한·입력 검증, 1회 처리 보장과 동시성, 메일 자동 발송 성공/실패/미설정/재발송 방지, 수동 발송 완료 표시, 미리보기, 리포트 상세 응답 필드, DB 마이그레이션 up/down, 화면 표시 조건·잠금·오류 처리
- 제외 범위 (Out-of-Scope) 및 사유:
  - **실제 Gmail 로 메일 발송**: 테스트가 실제 지원자에게 메일을 보내면 안 되고 이 세션에는 Gmail 자격증명이 없다. SMTP 호출 함수를 가짜로 바꿔 "호출 여부·수신자·제목·본문"을 검증했다. 실제 발송 경로(`send_notification_email`)는 이력서 합격 처리에서 DEC-116 으로 실측 검증된 동일 함수다. **배포 전 실제 메일 1회 확인 필요(8절).**
  - 실제 면접 진행으로 `completed` 상태가 되는 흐름: 면접 행을 DB에 직접 만들어 상태만 준비했다(면접 진행은 이 기능의 범위가 아님).
  - 프런트–백엔드 실연동 E2E: 프런트는 API 모킹, 백엔드는 HTTP 직접 호출로 각각 검증했다. 두 쪽이 맞물리는 계약(경로·필드명)은 `api.ts` 타입과 백엔드 응답 스키마 대조로 확인했다.
  - 부하·성능, 모바일 레이아웃, 접근성 자동 스캔

## 3. 테스트 환경
- 실행 환경: Linux 6.18, Python 3.11, **PostgreSQL 16.14**(+ pgvector, 임시 인스턴스), FastAPI/SQLAlchemy 2/Alembic(요구 버전), Node 22, Next.js 16.3.5 프로덕션 빌드, Playwright + Chromium
- 테스트 데이터: 테스트 하네스 규약 계정(`harness_test_<uuid>@harness-test.example`) + 면접 행 직접 삽입. 테스트 종료 시 계정은 `cleanup_test_data`가 삭제(정리 후 잔여 0건 확인)
- 전제 조건: 마이그레이션 `upgrade head` 적용, 서버는 `GMAIL_*` 미설정(자동 발송 경로는 프로세스 내 TestClient + SMTP 함수 가짜)
- 환경 메모: 이 샌드박스에는 무거운 AI 의존성(faster_whisper 등)이 없어 테스트 런처가 해당 모듈만 스텁으로 대체했다(저장소 파일 아님, 정리 완료). 앱 코드는 변경하지 않았다.

## 4. 테스트 케이스 및 결과

### 4-1. 백엔드 (pytest 36건, 마이그레이션 3건 별도)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| BE-01 | 완료 면접 합격 처리 | 200, 결정/문구/처리자/처리시각 저장, 메일 미설정이라 발송시각 null | 동일 | Pass |
| BE-02 | 완료 면접 불합격 처리 | 200, rejected 저장 | 동일 | Pass |
| BE-03 | 이미 처리된 건에 합격·불합격 재요청 | 409 "변경할 수 없습니다", 최초 결과 유지 | 동일 | Pass |
| BE-04 | scheduled/live/paused/expired 면접 처리 시도 (4건) | 409, DB 변경 없음 | 동일 | Pass |
| BE-05 | 존재하지 않는 면접 id | 404 | 동일 | Pass |
| BE-06 | candidate 계정으로 처리 | 403, DB 변경 없음 | 동일 | Pass |
| BE-07 | 토큰 없이 3개 엔드포인트 호출 | 401 ×3 | 동일 | Pass |
| BE-08 | 잘못된 입력 7종(빈 문구, 공백 문구, 501자, 문구 누락, status=pending, status=hired, status 누락) | 422, DB 변경 없음 | 동일 | Pass |
| BE-09 | 경계: 앞뒤 공백 포함 500자 문구 | 200, 공백 제거된 500자 저장 | 동일 | Pass |
| BE-10 | 미리보기: 처리 전 | 409 | 동일 | Pass |
| BE-11 | 합격 미리보기 내용 | 수신자=지원자 이메일, 제목 "[채용 안내] 최종 합격 안내", 이름·문구 포함, "서류 전형" 문구 없음 | 동일 | Pass |
| BE-12 | 불합격 미리보기 내용 | 제목 "[채용 안내] 최종 결과 안내", 문구 포함 | 동일 | Pass |
| BE-13 | candidate 가 미리보기 조회 | 403 | 동일 | Pass |
| BE-14 | 수동 발송 완료 표시: 처리 전 409 → 처리 후 200 → 재호출 시 시각 불변(멱등) → candidate 403 | 설명대로 | 동일 | Pass |
| BE-15 | 리포트 상세 응답 필드 | 처리 전 null, 처리 후 결정/문구/처리시각 노출 | 동일 | Pass |
| BE-16 | **동시성**: 합격·불합격 동시 요청 | 정확히 200 1건 + 409 1건 | 동일 | Pass |
| BE-17 | 메일: 발송 성공 | 메일 1회 호출(수신자·제목·본문 일치), 발송시각 저장 | 동일 | Pass |
| BE-18 | 메일: 불합격 내용 | 제목 "최종 결과 안내", "합격하지 못하셨습니다" 포함 | 동일 | Pass |
| BE-19 | 메일: SMTP 실패 | 판단은 저장(200), 발송시각 null("보낸 척" 금지), 수동 표시로 폴백 가능 | 동일 | Pass |
| BE-20 | 메일: 설정 없음 | 발송 호출 0회, 발송시각 null | 동일 | Pass |
| BE-21 | 메일: 재요청(409) 시 재발송 | 메일 총 1회 | 동일 | Pass |
| BE-22 | **메일: 4건 동시 요청** | 200 1건 + 409 3건, 메일 정확히 1회 | 동일 | Pass |
| BE-23 | 마이그레이션 `4381fbfa47d2 → a5d2c8e1f7b3` (기존 행이 있는 DB) | 오류 없이 적용, 기존 행은 NULL 유지, FK 생성 | 동일 | Pass |
| BE-24 | 마이그레이션 downgrade | 5개 컬럼·enum·FK 제거 | 컬럼 0개 확인 | Pass |
| BE-25 | downgrade 후 upgrade 재적용 | 오류 없음 | 동일 | Pass |
| BE-26 | 기존 스모크 테스트 6건(회귀) | 전부 통과 | 동일 | Pass |

### 4-2. 프런트 (Playwright E2E, 새 파일 12시나리오 + 상태 필터 14건 = 29건)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| FE-01 | 완료 건 화면 | "최종 합격/불합격 결정" 영역, 문구 드롭다운 각 3개, 일정 입력란 없음 | 동일 | Pass |
| FE-02 | scheduled/live/paused/expired 건 (4건) | 최종 처리 영역 없음 | 동일 | Pass |
| FE-03 | candidate 계정 | "권한이 없습니다", 영역 없음 | 동일 | Pass |
| FE-04 | 문구 미선택 | 두 버튼 비활성, 합격 문구만 고르면 합격 버튼만 활성 | 동일 | Pass |
| FE-05 | 합격 처리 | PATCH 1회(status/문구 일치), 결과 표시·잠금, 안내 영역(자동 발송 문구·안내 완료 시각) | 동일 | Pass |
| FE-06 | 불합격 처리 | status=rejected 로 전송, "최종 불합격" 표시 | 동일 | Pass |
| FE-07 | 더블클릭 | PATCH 1회만 | 동일 | Pass |
| FE-08 | 자동 발송 실패 상태 | 경고 문구, 미리보기(받는 사람·제목), "발송 완료로 표시" 동작 | 동일 | Pass |
| FE-09 | 이미 처리된 건 재진입 | 잠금 + 저장된 문구 표시, 처리 API 호출 0회 | 동일 | Pass |
| FE-10 | 서버 409 | 오류 배너 + 최신 상태로 잠금 | 동일 | Pass |
| FE-11 | 서버 500 | 오류 배너, 버튼 재활성(재시도 가능) | 동일 | Pass |
| FE-12 | 처리 전체 흐름 콘솔 오류 | 0건 | 동일 | Pass |
| FE-13 | 상태 필터·탭 순서 회귀 (기존 14건) | 전부 통과 | 동일 | Pass |

- 정적 검증: `tsc --noEmit` 오류 0, `eslint` 오류 0, `ruff check`(변경 파일 + 신규 테스트) 오류 0, `ruff format` 적용. (`ruff check app` 전체의 기존 3건은 이번 변경 이전부터 있던 것으로 stash 비교로 확인)

## 5. 커버리지
- 커버리지 지표: 요구사항(결정 4건 + 이력서 처리와 동일 동작) × 엔드포인트 3개 × 오류 경로 전부를 위 케이스에 1:1 매핑. 라인 커버리지는 측정하지 않았다.
- 커버되지 않은 부분과 사유: 실제 SMTP 발송(제외 범위 참고), 면접 행의 실제 생성 흐름, 프런트–백엔드 실연동 E2E

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | 문구 앞뒤 공백 때문에 500자 문구가 422 로 거부됨 | 공백 포함 504자 문구 전송 | Low | Fixed | 공백 제거를 길이 검사보다 먼저 수행하도록 검증기를 `mode="before"`로 변경, BE-09 로 재검증 |
| DEF-002 | (테스트 코드 결함) E2E locator 가 화면 전환 안내용 `role=alert` 요소와 겹쳐 간헐 실패 | 2회차 이상 반복 실행 | Low | Fixed | `.banner-error` 로 한정, 3회 반복 87건 통과로 재검증 |
| DEF-003 | (테스트 코드 결함) E2E 가 같은 이메일을 가진 두 요소를 구분하지 못함 | TC-F08 | Low | Fixed | "받는 사람:" 포함 텍스트로 한정 |
| DEF-004 | 개발 서버(`next dev`)에서 화면이 "불러오는 중"에서 멈춤 | 이 샌드박스에서 `next dev` 접속 | Low(환경) | Deferred | HMR 웹소켓 문제로 제품 코드와 무관, 프로덕션 빌드로 검증 |

- 제품 코드 결함은 DEF-001 1건(수정·재검증 완료). 나머지는 테스트 코드/환경 문제다.

### 내부 검증 이력 (규칙 B, 2회 이상)
| 회차 | 방법 | 결과 |
|------|------|------|
| 1차 | 백엔드 30건(신규) | 1건 실패(DEF-001) → 수정 |
| 2차 | 백엔드 신규+스모크 36건 | 36 Pass |
| 3차 | 린트·포맷 수정 후 36건 재실행(DB 재기동 후) | 36 Pass |
| 프런트 1차 | 29건 | 1건 실패(DEF-003, 테스트 코드) → 수정 |
| 프런트 2차 | 2회 반복 58건 | 1건 실패(DEF-002, 테스트 코드) → 수정 |
| 프런트 3차 | 3회 반복 87건 | 87 Pass |
| 마이그레이션 | up → down → up | 모두 성공 |

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 임시 PostgreSQL 인스턴스(`/tmp/claude-0/pg`, 포트 5555), 테스트 전용 venv·런처(`.harness-tmp/venv_final`, `.harness-tmp/run_api.py`), 임시 Playwright 설정(`frontend/pw.local.config.ts`), 프로덕션 서버(포트 3011)·API 서버(포트 8765), `frontend/node_modules`, `frontend/.next`
- `.harness-tmp/` 하위에만 생성했는가: 예(venv·런처). 단 `frontend/pw.local.config.ts`(모듈 해석 때문에 `frontend/` 안에 필요)·`node_modules`·`.next`는 예외이며, 앞의 파일은 삭제했고 나머지는 `.gitignore` 대상이다. DB 는 저장소 밖 `/tmp/claude-0/pg`에 두었다.
- 정리(삭제) 완료 여부: 서버 2개 종료, DB 종료·삭제, `.harness-tmp` 전체 삭제, 임시 설정·`test-results`·`playwright-report` 삭제, 빌드가 바꾼 `tsconfig.tsbuildinfo`·`next-env.d.ts` 원복. 테스트 계정은 하네스 정리 헬퍼가 삭제(잔여 0건 확인).
- 정리 후 `git status --short` 결과 (그대로, 본 결과서·로그·DEC 파일 추가 전 시점):
```
 M backend/app/api/v1/recruiter.py
 M backend/app/main.py
 M backend/app/models/interview.py
 M backend/app/schemas/recruiter.py
 M frontend/app/recruiter/[id]/page.tsx
 M frontend/lib/api.ts
?? backend/alembic/versions/a5d2c8e1f7b3_v18_interview_final_decision.py
?? backend/app/api/v1/recruiter_final_decision.py
?? backend/tests/final_decision/
?? frontend/e2e/recruiter-final/
```
  (출력의 파일이 모두 이번 작업 산출물이다. 임시 파일은 없다.)
- 강제 중단 여부: 있음 — 사용자 요청으로 도구 호출이 중단된 적이 있고 그 뒤 임시 서버·파일을 재점검했다. 또한 테스트 중 임시 DB 프로세스가 한 번 내려가(저장소 밖 `/tmp` 권한 변경 때문) 재기동 후 재실행했다.
- 서비스 헬스체크(규칙 K-6): 사용자의 로컬 서비스(3001/8000/DB 5544)는 이 클라우드 세션에서 실행 중이 아니고 건드리지 않았다. 이번 테스트의 서버 3개 포트(8765, 3011, 5555)는 종료돼 응답이 없음을 확인했다.

## 8. 리스크 및 잔존 이슈
- **배포 전 필수**: 로컬 DB(5544)에 마이그레이션 `alembic upgrade head` 적용 필요(이 세션은 사용자의 로컬 DB 에 적용할 수 없다). 적용 전에 화면을 열면 상세 조회가 오류가 난다.
- 실제 Gmail 로 최종 합격/불합격 메일이 1통 정상 도착하는지 사용자 환경(`backend/.env`의 Gmail 설정)에서 1회 확인이 필요하다.
- 채용담당자 계정을 삭제하는 기능이 생기면 `interviews.final_decided_by` FK 때문에 처리 이력이 있는 계정은 삭제가 막힌다(현재 그런 기능 없음, 감사 추적 목적).
- 결정이 되돌릴 수 없으므로(사용자 결정), 잘못 처리한 건은 DB 에서 직접 정정해야 한다. 필요하면 관리자용 정정 기능을 별도 요청으로 정의해야 한다.
- 안내 문구 3개씩은 제가 쓴 초안이다. 표현 변경은 `frontend/app/recruiter/[id]/page.tsx`의 두 배열만 고치면 된다.
- 후속 조치: 위 항목 확인.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능 (7절 Teardown 확인 완료). 단 8절 "배포 전 필수" 2건은 사용자 환경에서 확인해야 한다.
- 근거: 백엔드 36건·프런트 87건(3회 반복)·마이그레이션 up/down/up 전부 통과, 제품 결함 1건(DEF-001)은 수정·재검증 완료.
