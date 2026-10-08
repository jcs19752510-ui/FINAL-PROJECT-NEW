# 테스트 결과서 (Test Result Report) — 채용담당자 [R-01] 면접 상태 조회 selectbox + 상단 탭 순서 변경

> `templates/test-report-template.md` 사용. 변경 규모가 작은 프런트엔드 전용 변경이라 단위+통합 병합 형태로 작성했다.

## 1. 개요
- 테스트 대상: `frontend/app/recruiter/page.tsx`(면접 상태 selectbox, 클라이언트 필터), `frontend/app/recruiter/recruiter.module.css`(스타일), `frontend/components/RecruiterListTabs.tsx`(상단 탭 4개 순서)
- 테스트 유형: 단위+통합 병합 (브라우저 E2E, 백엔드 API는 모킹)
- 적용 Tier: High (DEC-002, 프로젝트 전체 선언값). 변경 위험도가 낮아 속도 트랙은 L2 수준으로 운영했다.
- 적용 속도 트랙: L2 (판단 근거: 화면 표시 로직 변경, 백엔드·DB·인증 변경 없음)
- 테스트 목적: ① 상단 탭이 이력서 검토 / 지원자 리포트 / 제출 절차 안내 / 채용담당자 추가 순서로 노출되는지 ② 설명 문구 바로 밑 selectbox가 면접 상태(전체·예정·진행 중·일시중지·완료·만료)로 목록을 정확히 거르는지 확인
- 관련 산출물: `개발작업내용/지원자리포트상태필터_탭순서변경_20261007_1059.md`, `docs/harness/04-ux-design.md` [R-01]
- 테스트 수행자: Claude (본 세션 직접 수행)
- 테스트 일시: 2026-10-07 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): 탭 순서·활성 표시, selectbox 위치·옵션·기본값, 상태별 필터 결과, 결과 0건 안내, 목록 0건 기존 안내 유지, 추가 API 호출 없음, 행 클릭 이동, 키보드 조작, 권한 경계(candidate), 콘솔 오류 0
- 제외 범위 (Out-of-Scope) 및 사유:
  - 실제 백엔드·DB 연동: 이번 변경이 서버 응답을 그대로 화면에서 거르기만 하므로 API를 모킹했다. 서버 변경 없음.
  - 시각 디자인 픽셀 비교, 모바일 레이아웃: 기존 `.page` 컨테이너 규칙을 그대로 따르며 별도 스냅샷 기준이 없다.
  - 다른 채용담당자 화면(이력서 검토 등)의 탭 활성 동작: 같은 컴포넌트를 공유하므로 `startsWith` 판정 로직은 변경하지 않았고, 이번에는 `/recruiter` 경로만 검증했다. (8절 리스크 참고)

## 3. 테스트 환경
- 실행 환경: Linux 6.18, Node v22.22.0, Next.js 16.3.5 **프로덕션 빌드**(`next build` + `next start -p 3011`), Playwright + 설치된 Chromium(`/opt/pw-browsers/chromium`, headless)
- 테스트 데이터: 면접 5건 모킹 (완료 1, 진행 중 2, 예정 1, 만료 1, 일시중지 0)
- 전제 조건: `sessionStorage.access_token` 주입, `/api/v1/auth/me`·`/api/v1/recruiter/reports`를 `page.route`로 모킹
- 참고: 개발 서버(`next dev`)에서는 이 샌드박스의 HMR 웹소켓 문제로 화면이 "불러오는 중"에서 멈춰 프로덕션 빌드로 전환했다. 코드 결함이 아니라 환경 문제다.

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-01 | 탭 순서 | recruiter 로그인 | `/recruiter` 열기 | 이력서 검토, 지원자 리포트, 제출 절차 안내, 채용담당자 추가 | 동일 | Pass | |
| TC-02 | 활성 탭 | 〃 | `aria-current` 조회 | 지원자 리포트 1개만 활성 | 동일 | Pass | 접근성 |
| TC-03 | selectbox 위치·옵션·기본값 | 5건 로드 | 설명 문구·selectbox·표 y좌표 비교, 옵션 조회 | 설명 문구 < selectbox < 표, 옵션 6개, 기본 "전체" | 동일 | Pass | |
| TC-04a | 예정 선택 | 〃 | selectbox "예정" | 1건, 면접 상태 열 모두 "예정" | 동일 | Pass | |
| TC-04b | 진행 중 선택 | 〃 | "진행 중" | 2건 | 동일 | Pass | |
| TC-04c | 완료 선택 | 〃 | "완료" | 1건 | 동일 | Pass | |
| TC-04d | 만료 선택 | 〃 | "만료" | 1건 | 동일 | Pass | |
| TC-05 | 해당 건 없는 상태(경계) | 일시중지 0건 | "일시중지" 후 "전체" | 안내 문구 표시·표 숨김 → 전체 복원 시 5건 | 동일 | Pass | |
| TC-06 | 추가 API 호출 없음 | 목록 호출 카운트 | 필터 3회 변경 | 목록 API 호출 1회 | 1회 | Pass | 성능 |
| TC-07 | 필터 후 행 클릭 | "만료" 선택 | 행 클릭 | 해당 지원자 상세로 이동 | `/recruiter/…0005` 이동 | Pass | 통합 |
| TC-08 | 목록 0건(예외) | 빈 배열 | 열기 | 기존 안내 문구 유지 + selectbox 표시 | 동일 | Pass | |
| TC-09 | 키보드·label 연결 | 5건 | selectbox 포커스 후 ↓ | "예정" 선택, 1건 | 동일 | Pass | 접근성 |
| TC-10 | 권한 경계 | role=candidate | `/recruiter` 열기 | "권한이 없습니다", selectbox 없음 | 동일 | Pass | 보안 |
| TC-11 | 콘솔 오류 | 5건 | 열기 + "진행 중" 선택 | pageerror/console error 0 | 0 | Pass | |

- 정적 검증: `tsc --noEmit` 오류 0, `eslint`(app/recruiter, components, e2e/recruiter-filter) 오류 0.

## 5. 커버리지
- 커버리지 지표: 기능 커버리지 — 변경된 기능 요구사항(탭 순서 1, selectbox 5개 상태+전체) 100% 케이스 매핑. 라인 커버리지는 측정하지 않았다(E2E 도구에 커버리지 계측 미설정).
- 커버되지 않은 부분과 사유: 다른 탭 화면에서의 활성 표시(범위 밖), 실제 백엔드 연동(서버 변경 없음)

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | 개발 서버(`next dev`)에서 화면이 "불러오는 중"에서 멈춤 | 샌드박스에서 `next dev` 후 접속 | Low(환경) | Deferred | HMR 웹소켓 문제로 제품 코드와 무관. 프로덕션 빌드로 검증 |

- 제품 코드 결함: 없음. 1차 14건 전부 Pass, 2차(`--repeat-each=2`) 28건 전부 Pass, tsc·eslint 오류 0으로 확인했다.

### 내부 검증 이력 (규칙 B, 2회 이상)
| 회차 | 방법 | 결과 |
|------|------|------|
| 1차 | 14건 실행 | 14 Pass / 0 Fail |
| 2차 | `--repeat-each=2`, workers=4 (28건) | 28 Pass / 0 Fail |
| 정적 | tsc, eslint | 오류 0 |

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: 프로덕션 서버 프로세스(포트 3011), `frontend/pw.local.config.ts`(임시 Playwright 설정), `frontend/e2e/dbg.spec.ts`(진단용), `/tmp/claude-0/` 하위 로그·결과, `frontend/node_modules`(설치), `frontend/.next`(빌드 산출물)
- `.harness-tmp/` 하위에만 생성했는가: 아니오 — 사유: 이 샌드박스에는 `node_modules`가 없어 `frontend/` 안에 설치해야 했고, Playwright 설정은 모듈 해석을 위해 `frontend/` 안에 있어야 했다. 서버 로그·결과물은 세션 임시 디렉터리(`/tmp/claude-0/`)에 두었다. `node_modules`, `.next`는 `.gitignore` 대상이다.
- 정리(삭제) 완료 여부: 서버 종료(포트 3011 응답 없음 확인), `pw.local.config.ts`·`dbg.spec.ts` 삭제, `test-results`·`playwright-report` 삭제, 빌드가 바꾼 `next-env.d.ts`·`tsconfig.tsbuildinfo` 원복
- 정리 후 `git status --short` 결과 (그대로):
```
 M frontend/app/recruiter/page.tsx
 M frontend/app/recruiter/recruiter.module.css
 M frontend/components/RecruiterListTabs.tsx
?? frontend/e2e/recruiter-filter/
```
  (본 결과서와 `개발작업내용/` 로그 파일은 이 확인 이후에 추가됐다.)
- 강제 중단 여부: 있음 — 사용자 요청으로 도구 호출을 2회 중단했고, 그 직후 위 정리 항목을 재점검했다. 이후 `pkill`로 종료한 서버 프로세스가 남지 않음을 확인했다.
- 서비스 헬스체크(규칙 K-6): 이번 테스트는 병렬 부하 테스트가 아니었고 로컬 백엔드를 사용하지 않았다. 포트 3011 종료만 확인했다. 기존 로컬 서비스(3001/8000)는 이 클라우드 세션에서 실행 중이 아니므로 해당 없음.

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - 목록이 서버 페이지네이션으로 바뀌면 클라이언트 필터가 현재 페이지만 거르게 된다. 현재 API는 전체 목록을 반환한다(04-ux-design §7 "경미" 항목).
  - 탭 순서가 바뀌었으므로 외부 문서·E2E가 탭 위치(n번째)에 의존한다면 영향이 있다. 저장소를 검색한 결과 `RecruiterListTabs`를 위치 기준으로 참조하는 테스트는 찾지 못했다.
- 후속 조치: 없음(필터 선택값은 새로고침 시 "전체"로 초기화되며, 요구사항에 유지 조건이 없어 그대로 두었다).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능 (7절 Teardown 확인 완료)
- 근거: 14건 + 28건 전부 Pass, 제품 코드 결함 0건, 정적 검사 오류 0건
