# 테스트 결과서 (Test Result Report) — unit-16 (REQ-015, Feature H. 부가 UX)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1/2/3/18-test.md 선례를 따름.
>
> 참고: 이 06 세션은 직전에 API rate limit(세션 한도)로 중단된 시도의 재개다. 재개 시 `.harness-tmp/` 및 작업 트리 잔여물부터 점검했다(규칙 K 3번) — §3/§7 참고.

## 1. 개요
- 테스트 대상: unit-16 — `frontend/components/WebcamPreview.tsx`(신규 클라이언트 전용 컴포넌트, `getUserMedia` 기반 로컬 웹캠 미리보기, 서버 전송 없음) (REQ-015)
- 테스트 유형: 단위
- 적용 Tier: **High**(오케스트레이터 지시 — Feature H 전체 Tier). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부). Tier=High이므로 06·07 병합 조건(Low 등급 전용) 자체가 성립하지 않는다 — 병합 대상 아님.
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 완료한 unit-16 구현이, unit-16-note.md §5의 정상 경로 인수조건 중 L1 범위(정상 경로 1~2케이스)를 실제로 만족하는지 **06단계 자신이 독립적으로 재현**하여 증명한다. 5단계 자체 검증 기록(unit-16-note.md §8, 임시 라우트 `frontend/app/wcpreview-check/`을 이용한 curl 확인)은 참고만 하고 그대로 승계하지 않았다 — 이번 06 세션은 그 임시 라우트가 이미 삭제되어 있음을 확인한 뒤, 06 전용의 별도 라우트를 새로 마운트해 독립적으로 curl/빌드/린트를 재실행했다.
- 관련 산출물: `docs/harness/units/unit-16-note.md`, `docs/harness/04-ux-design.md` [C-05]/[C-06]/§4 `WebcamPreviewTile`/§5-5·§5-9(접근성), `docs/harness/03-system-design.md` §1.2(클라이언트 전용, 서버 미전송)/§6.2(수집최소화), `docs/harness/traceability.md` REQ-015
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정):
  - TC-001: 인수조건 1 — `<WebcamPreview variant="panel" autoStart={false} />`와 `<WebcamPreview variant="tile" autoStart={false} />`를 마운트했을 때 초기 상태(`off`)가 두 variant 모두에서 올바르게 렌더링되는지(빈 상태 문구 + 켜기 버튼 + tile의 160×120 고정 크기).
  - TC-002(정상 경로에 인접한 안전성 보강 케이스, §「필수 원칙」의 "명백히 위험한 케이스는 범위를 벗어나도 테스트" 조항에 따라 06단계가 자체적으로 추가): 인수조건 6(`autoStart={true}`)의 전제 조건인 "SSR 환경(브라우저 `navigator` 없음)에서 크래시 없이 안전하게 폴백되는가"를 확인. 05단계는 `autoStart={false}` 인스턴스만 검증했고(unit-16-note.md §8) `autoStart={true}`의 서버 렌더링 경로는 한 번도 실행되지 않았으므로, 06단계가 처음으로 이 경로를 재현했다.
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 2·3·4·5(실제 브라우저 카메라 권한 허용/거부/미지원 전이, 트랙 stop 확인, OS 카메라 인디케이터 확인) — 실제 브라우저 네이티브 권한 프롬프트 조작이 필요하며, 06단계 환경에 브라우저 자동화 도구(Playwright 등)가 연동되어 있지 않아 독립 재현 불가(unit-16-note.md §4가 이미 명시한 제약과 동일, unit-18-test.md §2에서도 동일 사유로 제외됨). L1 부채로 이관.
  - 인수조건 6의 "client 환경에서 실제로 `requesting→active` 전이"(실제 카메라 권한) 부분 — 위와 동일 사유로 제외. 다만 SSR 안전성 부분(TC-002)만 06 범위에 포함.
  - 인수조건 7(콘솔 `act()`/`setState on unmounted` 경고 없음), 인수조건 8(네트워크 아웃바운드 없음) — 실제 마운트/언마운트 라이프사이클과 브라우저 개발자도구(콘솔/네트워크 탭) 확인이 필요해 완전한 라이브 재현은 불가. 대신 06단계가 **정적 코드 검증**으로 부분 대체했다: `grep -n -E "fetch\\(|WebSocket|XMLHttpRequest|axios|FormData" components/WebcamPreview.tsx` 실행 결과 실제 코드 라인에 매치가 전혀 없음(주석 1건만 매치)을 06단계가 직접 확인 — 05단계 note의 주장(§0/§1)을 그대로 믿지 않고 재확인한 것. 이는 "네트워크 탭에서 확인"을 완전히 대체하지는 못하므로 여전히 L1 부채로 남긴다.
  - 컴포넌트를 실제 화면([C-05]/[C-06])에 wiring한 상태에서의 통합 시나리오 — unit-16-note.md §0/§4에 따라 wiring 자체가 이번 유닛 범위 밖(통합 담당 유닛 몫)이므로 06단계도 별도 임시 라우트로만 확인.

## 3. 테스트 환경
- 실행 환경: Windows 11, Node.js(frontend 프로젝트 기존 의존성 그대로), Next.js 16.3.5(Turbopack). **재개 시 확인**: 세션 시작 직후 `git status`로 `frontend/app/wcpreview-check-unit16-06/page.tsx`가 이미 untracked 상태로 남아 있는 것을 발견 — 직전 rate-limit 중단 시점의 잔여물로 판단(파일 헤더 주석에 "06단계(unit-16) 임시 검증 라우트"라고 명시되어 있어 06단계 자신이 만든 것임을 확인). 내용을 검토한 뒤 재사용 가능하다고 판단해 그대로 이어서 사용했고(TC-002용 3번째 인스턴스만 추가), 최종적으로 §7에서 삭제해 정리했다.
- 이번 06 세션 전용 격리 라우트: `frontend/app/wcpreview-check-unit16-06/page.tsx`(다른 유닛과 이름이 겹치지 않도록 `-unit16-06` 접미사 사용, DEC-027 취지에 따른 유닛별 격리 — 05단계가 쓴 `frontend/app/wcpreview-check/`와도 다른 경로).
- 개발 서버: 이 저장소(monorepo 단일 Next.js 프로젝트)는 `next dev`가 프로젝트 단위로 동시 실행을 잠금(lock) 처리해, 06단계가 별도 포트(3916)로 독립 기동을 시도했으나 "Another next dev server is already running"으로 즉시 종료됨을 실측으로 확인했다(다른 병렬 작업 단위가 이미 포트 4116에서 기동해 둔 공유 dev 서버가 존재). 이는 `.harness-tmp` 임시 리소스가 아니라 Next.js 자체의 프로젝트 잠금 메커니즘이라 06단계가 우회할 수 없었다 — 부득이 이미 떠 있는 공유 dev 서버(포트 4116)에 대해 06단계가 직접 curl 요청을 보내 자신의 라우트(`/wcpreview-check-unit16-06`)만 검증했다. 서버 프로세스 자체를 새로 띄우거나 종료하지 않았으므로 다른 병렬 유닛에 영향을 주지 않았다(규칙 K 3번 취지 — 공유 리소스를 삭제/재시작하지 않음).
- `npm run build`/`npx eslint`는 06단계가 직접 새로 실행한 별도 프로세스(빌드는 백그라운드 프로세스 없이 1회성 CLI 실행)로, 5단계 기록을 승계하지 않고 독립 재현했다.
- 테스트 데이터: 없음(사용자 입력/DB 관련 없는 순수 프론트엔드 컴포넌트).
- 전제 조건 (Preconditions): 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인 — unit-16-note.md §6(`npm run lint`/`npm run build` 통과, `set-state-in-effect` 룰 위반 근거와 함께 명시적 disable 처리)·§7(코드리뷰 체크리스트 6항목 전부 [x])에서 확인했고, **06단계가 note 확인에 그치지 않고 아래 §9에서 직접 재실행해 재확인함**.

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 초기 상태(`off`) 렌더링 — panel/tile 두 variant (인수조건 1) | `frontend/app/wcpreview-check-unit16-06/page.tsx`에 `<WebcamPreview variant="panel" autoStart={false} />`, `<WebcamPreview variant="tile" autoStart={false} />` 마운트, 공유 dev 서버(포트 4116) 기동 상태 | `curl -s http://127.0.0.1:4116/wcpreview-check-unit16-06`로 HTML 응답 수신 후 텍스트/인라인 스타일 grep | HTTP 200. "웹캠이 꺼져 있습니다"/"웹캠 미리보기 켜기" 문구가 두 인스턴스 모두에 존재. tile 인스턴스는 `width:160px;height:120px` 고정 크기(04-ux-design §6 모바일 규칙) | HTTP 200 확인. `grep`으로 "웹캠이 꺼져 있습니다"·"웹캠 미리보기 켜기" 각 2회(두 인스턴스) 검출. tile 인스턴스 인라인 스타일에서 `width:160px;height:120px;...;border-radius:8px` 확인(panel은 `border-radius:12px`와 다른 값이어야 하는데 tile 값만 별도 검사, variant 분기 자체는 코드상 자명해 중복 검사 생략) | Pass | 05단계가 이미 삭제한 자신의 임시 라우트(`wcpreview-check`)를 재사용한 것이 아니라, 06단계가 새로 만든 별도 라우트(`wcpreview-check-unit16-06`)로 독립 재현함 |
| TC-002 | `autoStart={true}` + SSR 환경(navigator 없음) 안전 폴백 (인수조건 6의 SSR 전제 확인, 06단계 자체 추가 안전성 케이스) | 위 라우트에 `<WebcamPreview variant="tile" autoStart={true} />` 3번째 인스턴스 추가 | `curl -s http://127.0.0.1:4116/wcpreview-check-unit16-06`로 SSR 초기 HTML 확인 | 서버(Node.js, `navigator` 미정의) 렌더링 시 `isGetUserMediaSupported()`가 `typeof navigator !== "undefined"` 가드로 안전하게 `false`를 반환해 `unsupported` 상태로 폴백해야 하며, ReferenceError로 인한 500 에러가 발생하면 안 된다 | HTTP 200(크래시 없음). SSR HTML에 "이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다" + "웹캠 없이 텍스트로 계속 진행할 수 있습니다" 문구 확인 — 크래시 없이 안전 폴백됨을 확인 | Pass(크래시 방지 관점) / **리스크 발견**(아래 참고) | **발견 사항**: SSR에서는 `unsupported`로 렌더링되지만, 실제 브라우저(카메라 API 지원)에서 hydration 시 동일 lazy initializer가 `navigator` 존재를 감지해 `requesting`을 계산하게 되어 SSR 출력과 클라이언트 첫 렌더 결과가 달라질 수 있다(hydration mismatch 가능성). 이 컴포넌트가 아직 실제 SSR 라우트에 wiring되지 않아(unit-16-note.md §0) 라이브 임팩트는 없고, 06단계 환경에 브라우저 자동화 도구가 없어 실제 hydration 경고 발생 여부를 라이브로 재현하지는 못했다(정황 근거: SSR 산출물 자체가 다름을 실측 확인) → §6 DEF-001로 기록, L1 부채에 편입 |

> L1 경량판(정상 경로/안전성 1~2케이스)이므로 그 외 경계값/예외 입력(실제 권한 거부/미지원 브라우저 재현, 언마운트 시 트랙 정지, 콘솔/네트워크 탭 확인)은 §2에 제외 사유와 함께 명시했다. 다만 TC-002 수행 중 발견한 hydration mismatch 리스크는 인수조건 목록에 없던 것이지만 "명백히 위험한 케이스는 범위를 벗어나도 기록" 원칙에 따라 결함으로 기록했다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | `WebcamPreview`의 초기 상태 lazy initializer(`useState(() => autoStart ? (isGetUserMediaSupported() ? "requesting" : "unsupported") : "off")`)가 서버(Node.js, `navigator` 없음)와 클라이언트(브라우저, `navigator` 있음)에서 서로 다른 값을 계산한다. `autoStart={true}`로 SSR되는 라우트에서는 서버가 `unsupported`를 렌더링하지만, 카메라 API를 지원하는 실제 브라우저가 hydration할 때는 같은 함수가 `requesting`을 계산해 React 19 hydration mismatch(콘솔 경고 및/또는 첫 프레임에 잘못된 문구 노출)를 유발할 가능성이 있다 | 06단계가 curl로 확인: `frontend/app/wcpreview-check-unit16-06`에 `<WebcamPreview variant="tile" autoStart={true} />` 마운트 후 SSR HTML을 확인하면 "이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다"(unsupported)가 출력됨 — 이는 서버에 `navigator`가 없기 때문이며, 동일 컴포넌트를 카메라 지원 브라우저에서 열면 클라이언트 첫 렌더가 "카메라 권한 요청 중..."(requesting)을 기대하게 되어 SSR 결과와 어긋난다(라이브 브라우저로 hydration 경고 자체를 최종 확인하지는 못함 — 06단계 환경에 브라우저 자동화 도구 없음) | Medium | Deferred | 아직 어떤 실제 화면에도 wiring되지 않아(unit-16-note.md §0) 현재 라이브 영향은 없음. 권장 조치안 두 가지를 05단계에 인계: (a) 컴포넌트 자체에서 `autoStart` 초기값을 환경에 무관하게 항상 `requesting`으로 고정하고, 실제 미지원 여부 판정은 `useEffect` 내부의 `acquireStream` 시도 실패 경로에서만 하도록 재구성, 또는 (b) 통합(wiring) 담당 유닛이 `next/dynamic(() => import(".../WebcamPreview"), { ssr: false })`로 이 컴포넌트를 클라이언트 전용으로 로드. 07단계(및 06 정식화) 시 실제 브라우저로 hydration 경고 유무를 확정 재현하고 조치 여부를 결정해야 한다(08 착수 전 정산 대상) |

- 위 1건을 제외하면 결함 없음. 근거: TC-001은 06단계가 사전에 정의한 기대값(HTTP 200, 특정 한국어 문구, tile 고정 크기 인라인 스타일)과 실제 curl 응답을 필드/문구 단위로 대조해 전부 일치함을 확인했다("에러 없이 렌더링됨"이 아니라 문구·스타일 값 단위 비교로 PASS 판정). 정적 코드 검증(`grep`)으로 네트워크 API 미사용도 06단계가 직접 재확인했다(§2).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성/재사용한 임시 아티팩트 목록:
  - `frontend/app/wcpreview-check-unit16-06/page.tsx` — **재개 시 발견한 직전(rate-limit 중단) 06 세션의 잔여물**을 재사용 후 TC-002용 3번째 인스턴스를 추가해 이어서 사용함(신규 생성 아님, 기존 파일 이어쓰기).
  - `.harness-tmp/next_dev_06_unit16.log`, `.harness-tmp/next_dev_06_unit16.pid` — 06단계가 독립 dev 서버(포트 3916) 기동을 시도한 로그/PID(§3에서 설명한 대로 Next.js 프로젝트 잠금으로 즉시 종료됨).
  - `.harness-tmp/unit16_06_ssr_output.html` — TC-002 SSR 출력 캡처본.
  - `frontend/tsconfig.tsbuildinfo` — `npm run build`/`npx eslint`/타입체크 실행 중 생성된 것으로 추정되는 재생성 가능한 빌드 캐시(unit-18-test.md와 동일 판단 기준 적용).
- 위 아티팩트를 전부 `.harness-tmp/` 하위 또는 06단계 전용 임시 라우트에서만 생성했는가 (규칙 K 1번): [x] 예 — `frontend/app/wcpreview-check-unit16-06/`은 `.harness-tmp/`가 아니지만 다른 유닛과 경로가 겹치지 않는 06 전용 임시 검증 라우트이며, 테스트 종료 시 삭제 대상으로 명확히 구분해 관리했다(DEC-027 취지 — 유닛별 격리, 공유 리소스 미훼손).
- 정리(삭제) 완료 여부: 완료.
  - `frontend/app/wcpreview-check-unit16-06/` 디렉터리 전체 삭제 후, 공유 dev 서버(포트 4116, 06단계가 기동한 것이 아니므로 종료하지 않음)에 재요청해 `HTTP 404`로 라우트가 실제로 사라졌음을 확인.
  - `.harness-tmp/next_dev_06_unit16.log`, `.harness-tmp/next_dev_06_unit16.pid`, `.harness-tmp/unit16_06_ssr_output.html`, `frontend/tsconfig.tsbuildinfo` 전부 삭제 완료. 06단계가 3916 포트에 기동 시도했던 프로세스(PID 4057)는 Next.js 자체 잠금으로 이미 스스로 종료되어 있었음을 `tasklist`로 재확인(별도 kill 불필요).
  - `.harness-tmp/` 하위에 남아있는 `u5_stt_result.txt`, `u5_test_audio.mp3`, `unit12_server.log`, `unit9_server.log`, `venv_05_unit12`, `venv_05_unit5`, `venv_05_unit9`, `venv_06_unit9`는 전부 다른 병렬 작업 단위(unit-5/9/12) 소유 산출물로 확인되어(파일명 접두사로 식별) 이번 unit-16 06 세션이 삭제하지 않았다(규칙 K 3번 취지 — 다른 유닛 리소스 임의 삭제 금지).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   backend/alembic/env.py
	modified:   backend/app/api/v1/interviews.py
	modified:   backend/app/main.py
	modified:   backend/app/services/job_queue.py
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   frontend/app/globals.css
	modified:   frontend/lib/api.ts
	modified:   frontend/next-env.d.ts
	modified:   frontend/package-lock.json
	modified:   frontend/package.json

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	backend/alembic/versions/0df1434883f2_v3_transcripts.py
	backend/alembic/versions/8a55fda78a42_v4_deletion_requests.py
	backend/alembic/versions/b84a71b986c5_v6_code_submissions.py
	backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py
	backend/app/api/v1/code_submissions.py
	backend/app/api/v1/consents.py
	backend/app/api/v1/ops.py
	backend/app/api/v1/recruiter.py
	backend/app/api/v1/whiteboard.py
	backend/app/api/v1/ws.py
	backend/app/models/code_submission.py
	backend/app/models/deletion_request.py
	backend/app/models/transcript.py
	backend/app/models/whiteboard.py
	backend/app/schemas/code_submission.py
	backend/app/schemas/consent.py
	backend/app/schemas/ops.py
	backend/app/schemas/recruiter.py
	backend/app/schemas/transcript.py
	backend/app/schemas/whiteboard.py
	backend/app/services/stt_engine.py
	docs/harness/units/unit-12-note.md
	docs/harness/units/unit-14-note.md
	docs/harness/units/unit-14-test.md
	docs/harness/units/unit-16-note.md
	docs/harness/units/unit-17-note.md
	docs/harness/units/unit-18-note.md
	docs/harness/units/unit-18-test.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	docs/harness/units/unit-9-note.md
	frontend/app/admin/
	frontend/app/interviews/
	frontend/app/legal/
	frontend/app/mypage/
	frontend/app/recruiter/
	frontend/components/
	frontend/lib/complianceContent.ts

no changes added to commit (use "git add" and/or "git commit -a")
```
  (`frontend/app/wcpreview-check-unit16-06/`가 위 목록에 더 이상 없음을 확인 — 삭제 성공. `docs/harness/traceability.md`(M)는 이번 06 세션이 §「traceability.md 갱신」에서 수정한 것이고, `frontend/components/`(??, `WebcamPreview.tsx` 포함)는 05단계 산출물로 06단계가 건드리지 않았다. `frontend/next-env.d.ts`(M)는 여러 병렬 세션이 `next dev`/`next build`를 동시에 실행하며 공통으로 갱신되는 자동 생성 파일로 판단해(unit-18-test.md §7과 동일 판단), 어느 세션 소유인지 특정할 수 없어 되돌리지 않았다. 나머지 항목은 unit-3/4/5/9/12/14/17/18 등 다른 병렬 작업 단위 산출물로 unit-16과 무관하다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 있음 — **직전 06 세션이 API rate limit(세션 한도)로 중단됨**. 재개 시 규칙 K 3번에 따라 `.harness-tmp/` 및 작업 트리를 먼저 점검했고(§3), 직전 세션이 남긴 `frontend/app/wcpreview-check-unit16-06/page.tsx`(06 전용 명명 규칙을 따르고 있어 다른 유닛 소유가 아님을 확인) 외에는 unit-16 관련 잔여물이 없음을 확인한 뒤 이어서 진행했다. 이번(재개된) 세션 자체는 중단 없이 끝까지 완료됨.
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실 및 DEF-001은 규칙에 따라 `docs/harness/traceability.md`에도 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 2~5·6의 실제 브라우저 부분·7·8은 06단계가 브라우저 자동화 도구 부재로 독립 재현하지 않았다(§2). DEF-001(hydration mismatch 가능성)도 라이브 브라우저로 최종 확정하지 못했다. 이 셋 모두 07(및 L1 06 정식화) 정산 시 실제 브라우저(Playwright 등)로 재현해야 한다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능 (7절 Teardown 확인 완료됨). **단, 이 PASS는 L1 경량판 범위(TC-001·TC-002)에 한정된 판정이며, DEF-001(Medium, Deferred)과 인수조건 2~5·7·8은 미해결 L1 부채로 traceability.md에 별도 기록한다.**
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-16-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-015 행의 "단위테스트" 컬럼과 비고란을 갱신하고(DEF-001 포함), 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용). 다만 아래 두 차례는 최소한의 자기 점검으로 실제 수행했다:
- 1차 검증(인수조건 커버리지·근거): unit-16-note.md §5의 인수조건 1~8 중, L1 범위인 1(TC-001)은 1:1로 커버했다. 6은 실제 카메라 권한 전이까지는 아니지만 그 전제인 SSR 안전성을 TC-002로 커버했고, 완전한 client 전이(requesting→active)는 §2에 제외 사유와 함께 명시했다(임의 누락이 아님). 2·3·4·5·7·8은 명시적으로 범위 밖으로 남겼다. TC-001/TC-002의 예상 결과는 unit-16-note.md §5(인수조건 원문)와 WebcamPreview.tsx 소스 코드(§26~47행의 `isGetUserMediaSupported`/lazy initializer 로직)를 06단계가 직접 읽고 근거로 삼아 사전에 정의한 것이며, 실행 후 짜맞춘 것이 아니다.
- 2차 검증(다음 단계로 넘겨도 되는가 / 놓친 경계 조건 재검토): 최초 TC-002 설계 의도는 단순히 "SSR에서 크래시가 나지 않는다"만 확인하려 했으나, SSR 출력이 `unsupported`로 나온다는 실측 결과를 보고 "그렇다면 실제 카메라 지원 브라우저의 client 첫 렌더와 다르지 않은가?"를 재검토했고, 이 재검토에서 hydration mismatch 가능성(DEF-001)을 발견했다. 이 재검토가 없었다면 TC-002를 단순 "크래시 없음 = Pass"로만 얕게 판정하고 넘겼을 것이다 — 이는 "실행해보니 에러 없음만으로 PASS 처리하지 않는다"는 필수 원칙에 정면으로 해당하는 재점검이었다. 07/06 정식화로 넘길 때 남는 주요 미검증 경계는 실제 브라우저 권한 전이(§2)와 DEF-001의 라이브 확정이며, 둘 다 §6·§8·§9에 명시했으므로 놓치지 않고 이관된다.
- 검증 로그 파일 경로: 별도 `verification-log-template.md` 파일을 생성하지 않고(L1 경량판, 검증 생략 조항 적용) 본 절과 §3·§4에 검증 내역을 직접 서술로 남겼다.
