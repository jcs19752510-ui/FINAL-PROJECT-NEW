# unit-20 구현 노트 — Feature I. 면접장 화면 통합 배선 (REQ-008 · REQ-015 · REQ-017)

- 입력: `04-ux-design.md` [C-05]/[C-06]/[C-07]/[C-08]/§3(토큰)/§4(컴포넌트)/§5(접근성)/§6(반응형), `03-system-design.md` §4.2(`/code-submissions`, `/whiteboard`)·§4.3(`control` enum)·§6.2/§6.3, `decisions.md` DEC-029/031/032, `unit-9/16/17-note·test`, `unit-16-test.md` §6 DEF-001
- **속도 트랙: L3(일반)** (DEC-031) — 06단계는 정식(10섹션 전체) + 브라우저 자동화 포함, 07 정식, 규칙 B 원문(Tier=High)
- 범위: 프런트 전용. `backend/**`, `frontend/package.json`/`package-lock.json`, `playwright.config.ts`, `e2e/**`, `traceability.md`/`decisions.md`/`02-planning.md`는 수정하지 않았다.
- 작성 시각: 2026-09-20 02:35 KST (05단계 중간에 API 한도로 01:42경 중단 → 02:21 재개, 재개 시 각 파일의 문법 완결성을 다시 점검하고 이어서 완료)

## 1. 구현 범위

| 파일 | 변경 |
|---|---|
| `frontend/app/interviews/[id]/page.tsx` | 툴바(패널 토글 탭 2개 + 웹캠 타일/토글), `.interview-room__body` 분할 컨테이너, `InterviewSidePanel` 삽입, `turn_result.control.action === "switch_to_coding"`이면 코드 패널 자동 노출(live일 때만). 기존 채팅 타임라인/입력창/음성 로직은 **`.interview-room__chat` 래퍼로 감싸기만** 했고(들여쓰기 +4로 diff가 큼 — `git diff -w`로 보면 +117/-3) 동작·텍스트는 그대로다. |
| `frontend/app/interviews/[id]/components/InterviewSidePanel.tsx` (신규) | 보조 패널 컨테이너. 한 번 열린 패널은 닫아도 unmount하지 않고 `hidden`(로컬 편집 유실 방지), 모바일 모달일 때 `role="dialog"` `aria-modal`, 열림 시 제목으로 포커스 이동, Esc 닫기(단, Monaco 내부 Esc는 제외), "채팅으로 돌아가기" 버튼. |
| `frontend/lib/useMediaQuery.ts` (신규) | `useSyncExternalStore` 기반 미디어쿼리 훅(서버 스냅샷 false 고정). |
| `frontend/components/WebcamPreview.tsx` | **DEF-001 해소**(§4 참고). |
| `frontend/app/interviews/[id]/components/CodeEditorPanel.tsx` | Monaco 옵션에 `automaticLayout: true` 1개 추가(분할/모달 전환·창 크기 변경 시 에디터 레이아웃 갱신). |
| `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx` | 래퍼를 고정 px → `width:100% / maxWidth / aspectRatio`로, 도구바·캔버스 테두리 색을 흰색 반투명 → 디자인 토큰(`--color-border` 등)으로 변경. |
| `frontend/app/globals.css` | 툴바/탭/분할 뷰/보조 패널/모바일 모달/포커스 링/터치 타깃 규칙 append(기존 규칙 수정 없음). |
| `frontend/lib/api.ts` | **변경 없음** — 코드 복원 GET은 `CodeEditorPanel`이 자체 fetch로, 화이트보드는 기존 `getWhiteboard/saveWhiteboard`로 이미 복원한다. 추가가 필요한 함수가 없었다. |
| 신규 패키지 | **없음**. |

## 2. 04 디자인서 명세 → 구현 매핑

| 04 명세 | 구현 |
|---|---|
| [C-06] 구성요소 "코드/화이트보드 패널 토글 탭" | 툴바의 `코드 에디터`/`화이트보드` 토글 버튼 2개(`aria-pressed`, `aria-controls`). 같은 탭을 다시 누르거나 "채팅으로 돌아가기"를 누르면 채팅만 보이는 상태로 복귀. |
| [C-06] "웹캠 프리뷰 소형 타일(로컬 전용)" | `<WebcamPreview variant="tile">`(160×120), **기본 off** — 사용자가 "웹캠 미리보기 켜기"를 눌러야 권한 요청(자동 권한 요청 없음). 서버 전송 코드 추가 없음. |
| §6 Desktop ≥1200px "채팅 60% + 보조패널 40% 분할" | 패널이 열리면 `.interview-room--split`(최대폭 1200px) 그리드 `3fr 2fr`. 실측 채팅 686px : 패널 458px = 0.600. |
| §6 Tablet 768~1199px "2컬럼 가능(예: 채팅+코드)" | 같은 그리드 `1fr 1fr`(코드·화이트보드 모두). 실측 1000px에서 472 : 472. |
| §6 Mobile <768px "코드/화이트보드는 전체화면 모달, 웹캠은 기본 최소화(토글로 펼침)" | 패널: `position:fixed; inset:0`(390×800 뷰포트를 정확히 덮음), `role="dialog" aria-modal`, 배경(툴바+채팅)은 `inert`. 웹캠: 모바일에서만 "웹캠 보기/숨기기" 토글(`aria-expanded`) 노출, 기본 접힘(접히면 언마운트 → 카메라 트랙 정지). |
| §1.1 6-e `switch_to_coding` → [C-07] 노출 | WS `turn_result`의 `control.action`이 `switch_to_coding`이면 코드 패널을 연다(모바일이면 모달로, 이때 포커스를 패널로 이동). |
| [C-07] 상태(restoring/saving/saved/error), [C-08] 상태(로딩/저장 실패 등) | 각 컴포넌트가 이미 구현 — 배선만. 재접속 복원 GET은 패널을 **처음 열 때** 각 컴포넌트가 수행. |
| [C-07] "채팅으로 돌아가기" | 래퍼 헤더의 단일 버튼으로 코드·화이트보드 공통 제공(코드 패널의 `onBackToChat` 프롭은 중복을 피하려고 쓰지 않음). |
| §5-1 대비 / §5-4 포커스 링 / §5-8 터치 타깃 44px | 신규 클래스에 `--color-focus-ring` 2px+오프셋 적용, 모바일에서 탭·토글·패널 내 버튼·웹캠 타일 버튼 최소 44×44(실측 탭 108×44, 웹캠 켜기 125×44). 탭 활성 상태는 색 + `aria-pressed` + 테두리 두께로 구분. |
| §5-5 웹캠 `aria-hidden` | 기존 컴포넌트 그대로(`video aria-hidden="true"` 실측). |
| §5-7 `prefers-reduced-motion` | 이 유닛에서 추가한 애니메이션/트랜지션 없음. |

## 3. 설계서 대비 해석·편차 (전부 기록)

1. **[C-05] 면접 준비/장치점검 화면은 만들지 않았다.** 저장소에 [C-05] 라우트가 없고(unit-4-note §편차7 확인, 동의 화면은 곧바로 `/interviews/{id}`로 이동), 신설하려면 마이크 레벨 미터·"텍스트로만 진행" 옵션·동의 화면(unit-3 소유) 리다이렉트 변경이 필요해 유닛 범위(REQ-008/015/017 배선)를 벗어난다고 판단. 웹캠은 [C-06] 소형 타일로만 배선. **오케스트레이터 확인 필요(§9 Q1).**
2. **데스크톱 패널 초기 상태 = 닫힘**(채팅만 보임, 탭으로 열림). 04는 "분할 뷰가 기본"이라고만 하고, §1.1 6-e는 "패널을 분할 뷰로 **노출**", [C-06]은 "토글 탭"이라 "열렸을 때의 표현 방식이 분할 뷰(모바일은 모달)"로 해석. 초기값 한 줄(`activePanel` 초기값)로 뒤집을 수 있다. **§9 Q2.**
3. **세션 상태별 활성/비활성**: `live`일 때만 탭 활성. `scheduled/paused/completed/expired`에서는 탭 `disabled` + 안내 문구 "면접이 진행 중(live)일 때만 사용할 수 있습니다." 근거: 턴 제출과 같은 기준(`canSubmitTurn`). 백엔드 `/code-submissions`·`/whiteboard`는 상태를 검사하지 않는다(코드 확인). [C-07]의 `readonly` 상태(완료 세션 열람용)는 컴포넌트에 읽기 전용 모드가 없어 구현하지 않았다. **§9 Q3.**
4. **화이트보드 자동 노출 신호 없음**: 03 §4.3 `control` enum(`next_question|end_interview|switch_to_coding|none`)에 화이트보드용 값이 없어 화이트보드는 사용자 탭 조작으로만 연다(04 §1.1 6-e "화이트보드가 필요하면"은 트리거 미정의).
5. **`WebcamPreview.tsx`(unit-16 소유) 수정 — DEF-001 해소를 위해 필요.** 컴포넌트 계약(props, 상태 6종)은 불변.
6. **`CodeEditorPanel.tsx`(unit-9) `automaticLayout: true` 1개, `WhiteboardCanvas.tsx`(unit-17) 스타일 변경** — 배선 시 실제로 발견된 문제(아래) 때문에 필요했던 최소 수정. 컴포넌트 계약/API 호출 로직은 불변.
   - 화이트보드 래퍼가 640×400 고정 px라 40% 컬럼(≈458px)·태블릿에서 넘침 → 반응형으로 변경(`getCanvasPoint`는 원래 `getBoundingClientRect` 비율로 좌표를 환산하므로 CSS 스케일링과 호환, 저장 좌표계는 640×400 그대로).
   - 도구바/테두리 색이 어두운 배경 전제(흰색 반투명)라 라이트 테마(04 §3.1)에서 버튼·선택된 색상 링·캔버스 경계가 보이지 않음 → 토큰으로 교체.
   - Monaco는 `automaticLayout` 없이는 분할↔모달 전환·창 리사이즈 후 폭을 다시 계산하지 않음.
7. 모바일에서 `switch_to_coding` 자동 노출은 전체화면 모달을 갑자기 띄운다(04 §1.1 6-e + §6 그대로 적용한 결과). 작성 중이던 텍스트 입력은 상태로 보존되지만(`inputText`는 부모 상태) 사용자 경험상 방해가 될 수 있어 06/UX 검토 시 참고.

## 4. DEF-001 조치 (`unit-16-test.md` §6)

- 원인: `useState` 초기값에서 `isGetUserMediaSupported()`를 호출 → SSR은 `unsupported`, 브라우저 첫 렌더는 `requesting`.
- 조치(권장안 (a) 계열, 계약 불변): 초기값을 `autoStart ? "requesting" : "off"`로 서버/클라이언트 동일하게 고정하고, 지원 여부 판정(`unsupported`)은 마운트 후 effect에서만 수행.
- 검증: 임시 라우트(`autoStart`) `curl` SSR 결과가 "카메라 권한 요청 중..."(이전엔 "이 브라우저 또는 장치에서…")으로 바뀜을 확인. Playwright(headless Chromium, dev 모드)로 열어 카메라 없음/가짜 카메라 두 경우 모두 콘솔 error·warning 0건(React dev 모드는 hydration mismatch를 console.error로 보고함) — 가짜 카메라에서 `active`("끄기" 버튼) 전이 확인. 임시 라우트는 삭제함.
- 현재 C-06 타일은 `autoStart`를 쓰지 않으므로(사용자가 켬) 라이브 화면에서 이 경로는 아직 쓰이지 않는다 — [C-05]가 생기면 그대로 안전하게 쓸 수 있다.
- 남은 항목: unit-16의 나머지 L1 부채(권한 전이 등)는 이 배선으로 대부분 브라우저에서 실측됨(§7) — 정산은 06/07에서.

## 5. 코드 에디터 내용 렌더링 확인 (REQ-036 / 03 §6.3 관련)

- `frontend/` 전체에서 `dangerouslySetInnerHTML`/`innerHTML` 사용 0건(grep). 코드 내용은 Monaco `value`(입력 전용)와 `POST` JSON 본문으로만 오가며 HTML로 그려지는 경로가 없다. 제출 이력을 HTML로 표시하는 화면은 이 유닛에 없고 필요해지지도 않았다(필요해지면 질문할 사항).
- 실측: `<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>`를 코드로 제출 → 재접속 후 복원해도 `window.__xss` 미설정, `img[src='x']` 0개.
- 채팅 영역의 AI 텍스트 렌더링(`{m.content_text}` JSX 텍스트 노드)은 건드리지 않았다(unit-8이 새니타이즈 추가 예정).

## 6. 게이트 1·2

**게이트 1 (frontend, 최종 코드 기준 2026-09-20 02:33 KST 재실행)**
- `npm run lint` → error 0, warning 1(기존 `app/interviews/new/page.tsx` `no-html-link-for-pages`, 본 유닛 무관·미수정). unit-22의 `e2e/`·`playwright.config.ts` 때문에 실패한 항목 없음.
- `npx tsc --noEmit` → 출력 없음(통과).
- `npm run build` → `Compiled successfully`, 라우트 목록에 `ƒ /interviews/[id]` 포함. (실행 전 `package.json`에 `@playwright/test` 반영 확인, 다른 npm/next 프로세스 없음 확인. 다른 사람의 `npm run lint`(PID 11840/29588)가 잠시 떠 있어 끝난 뒤 실행.)
- 빌드/dev가 재생성한 추적 파일 `frontend/next-env.d.ts`, `frontend/tsconfig.tsbuildinfo`는 `git checkout`으로 원상 복구함(내가 바꾼 것만).

**게이트 2 자체 코드 리뷰**
- [x] 설계서/디자인서 일치 — §2 매핑, 편차는 §3에 전부 기록.
- [x] 에러 처리 — 신규 코드는 상태·이벤트 배선 위주이고 API 호출은 기존 컴포넌트의 에러 경로(복원 실패 안내, 제출 실패 인라인, 저장 실패 배지)를 그대로 사용. 삼키는 catch 추가 없음. WS `control`은 enum 비교(`=== "switch_to_coding"`)만 하며 그 외 값은 무시(서버가 화이트리스트로 강제 — 03 §6.3).
- [x] 시스템 경계 입력 — 새 사용자 입력 경로 없음(코드/캔버스 입력 검증은 서버 스키마 소관, unit-9/17에서 검증됨). 클라이언트에서 코드 내용을 HTML로 해석하지 않음(§5).
- [x] 하드코딩 시크릿 없음.
- [x] 신규 의존성 없음(`@monaco-editor/react`는 기존 unit-9 의존성).
- [x] 범위 외 변경 없음 — 기존 채팅/음성 로직은 래퍼로 감싸기만. 다른 유닛 파일 수정은 §3-5·6의 3개 최소 수정만이며 사유 기록.

## 7. 로컬 동작 확인 로그 (2026-09-20 02:24~02:31 KST)

- 백엔드: `.harness-tmp/venv_05_unit7` python(읽기 전용 사용, 설치/삭제 없음)으로 uvicorn **포트 8320**(PID 32372/31732), `CORS_ORIGINS`·`REDIS_URL=…/14`(다른 유닛의 워커가 내 잡을 가져가지 않도록 논리 DB 분리)을 환경변수로만 지정. 프런트는 `next dev -p 3320`(PID 12160 + 자식 2개), `NEXT_PUBLIC_API_BASE_URL`을 환경변수로 지정.
- 테스트 데이터: 신규 candidate 계정 1개 + 세션 2개(live 1, `POST /end`로 completed 1) — 모두 신규 생성.
- **브라우저 확인은 unit-22 산출물이 아니라, 설치된 Chromium(headless)을 `playwright-core`로 직접 구동한 임시 스크립트(`.harness-tmp`, 종료 후 삭제)로 수행했다.** 저장소의 `e2e/`·`package.json`은 건드리지 않았다. 47개 체크 **47/47 통과**(최종 실행). 통과 항목 요약:
  - 데스크톱 1280×900: 탭 2개 활성, 패널 초기 숨김, 웹캠 타일 off+토글 숨김, 코드 탭 클릭 시 분할 60:40(686:458), `aria-pressed`, 데스크톱에서는 dialog 시맨틱 없음, Monaco 로드, 편집→"미저장"→제출 `201`→"저장됨", **닫았다 다시 열어도 미저장 로컬 편집 유지**, 화이트보드 표시·캔버스가 패널 안에 맞음(424×266), 마우스로 그린 뒤 저장 `PUT 200`, **새로고침 후 화이트보드(GET 픽셀 복원)와 코드(GET) 복원**, 웹캠 오류/권한거부 상태에서도 입력창 사용 가능, 네트워크 요청 호스트는 `localhost:3320/8320`과 Monaco CDN(`cdn.jsdelivr.net`)뿐, 콘솔 error/warning 0(자체 테스트 코드의 `getImageData` 경고 제외).
  - 가짜 카메라: 켜기→`active`→끄기, `video[aria-hidden=true]`, 끄면 `srcObject=null`, blob 요청 없음. `getUserMedia`를 `NotAllowedError`로 모킹 → "카메라 권한이 거부되었습니다." + "웹캠 없이 텍스트로 계속 진행할 수 있습니다." 표시.
  - 태블릿 1000px: 472:472 분할, 캔버스가 패널에 맞게 축소(438).
  - 모바일 390×800(터치): 웹캠 토글 기본 접힘→펼침(`aria-expanded`), 탭 높이 44px·웹캠 버튼 44px, 패널이 뷰포트 전체(390×800)를 덮음, `role=dialog aria-modal=true`, 채팅·툴바 `inert`, 포커스가 패널 안으로 이동, Esc로 닫힘, 닫힌 뒤 포커스가 열었던 탭으로 복귀, 닫기 버튼 동작, 가로 스크롤 없음. (이 과정에서 실제 결함 1건 발견·수정: 데스크톱용 `align-self:start`가 fixed 패널을 내용 높이(620px)로 줄이던 문제 → 모바일 규칙에 `align-self: stretch` 추가.)
  - WS 모킹(`routeWebSocket` + `/turns` 202 모킹): `turn_result{control:switch_to_coding}` 수신 시 코드 패널 자동 노출, `ai_text`가 채팅에 그대로 표시.
  - completed 세션: 탭 2개 `disabled` + 안내 문구.
  - HTML 형태 코드 제출 → 렌더링/스크립트 실행 없음(§5).
- 실제 워커가 만든 `turn_result`(진짜 LLM 경로)로 `switch_to_coding`이 오는 경우는 확인하지 못함(WS 모킹으로만 검증) — 06/07에서.

## 8. 미검증 항목 (사실대로)

- axe/Lighthouse 등 자동 접근성 검사 미실행(색 대비는 토큰 값만 사용했고 실제 렌더 대비 측정은 안 함). 스크린리더 실기 낭독 미확인.
- 실제 카메라 하드웨어, Safari, 320px 이하 폭, 브라우저 확대 200% 미확인. Chromium headless만 사용.
- 모바일에서 Monaco 안의 Tab 키 포커스 이동(키보드 트랩) 실측 안 함 — Monaco 기본 동작(Tab=들여쓰기, Esc 후 Tab으로 이탈)에 의존.
- Monaco는 `@monaco-editor/react` 기본 설정대로 **jsdelivr CDN에서 로드**된다(요청 호스트에서 확인). CDN 차단/오프라인/엄격한 CSP 환경에서는 에디터가 뜨지 않는다 — 09/10단계에서 CSP·자체 호스팅 여부 판단 필요(이 유닛의 변경 아님).
- `CodeEditorPanel`은 복원 시 언어 드롭다운의 현재 값(기본 python)의 최신 제출만 불러온다. 마지막 제출이 다른 언어(예: go)였다면 재접속 직후 python 빈 템플릿이 보이고 드롭다운을 바꿔야 복원된다(04 "최신 제출본 복원"과의 갭 가능성, unit-9 컴포넌트 동작이라 수정하지 않음). **§9 Q4.**

## 9. 미해결 질문 (규칙 A — 오케스트레이터 판단 필요, 진행은 아래 "현재 선택"으로 했음)

- **Q1 [05/C-05]** [C-05] 장치점검 화면(마이크 레벨 미터·웹캠 큰 미리보기·텍스트 전용 옵션·"시작하기")을 이 유닛에서 신설할지? 근거: 라우트가 없어 웹캠 `variant="panel" autoStart`가 쓰일 곳이 없음. 선택지 (a) 이번엔 C-06 타일만(현재 선택, 범위 유지), (b) 새 유닛으로 분리해 `/interviews/[id]/ready` 신설 + 동의 화면 리다이렉트 변경(unit-3 파일 수정 필요, 마이크 미터는 REQ-004 UX). 
- **Q2 [05/C-06]** 데스크톱에서 보조 패널을 처음부터 열어 둘지(현재: 닫힘, 탭/`switch_to_coding`으로 열림). 한 줄 변경.
- **Q3 [05/C-07·08]** 비-live(완료/만료) 세션에서 코드·화이트보드를 읽기 전용으로 열람하게 할지(현재: 탭 비활성). 하려면 두 컴포넌트에 읽기 전용 모드 추가 필요.
- **Q4 [05/C-07]** 재접속 시 마지막 제출의 언어를 자동 선택하도록 `CodeEditorPanel`을 확장할지(현재: 미수정).

## 10. 06단계(L3 정식) 인수 조건

전제: 세션은 `POST /interviews` → `POST /consents`(ai_interview_notice) → `POST /interviews/{id}/start`로 `live`가 된 것을 사용. 토큰은 `sessionStorage["access_token"]`. 프런트가 백엔드를 바라보도록 `NEXT_PUBLIC_API_BASE_URL` 지정, 백엔드 `CORS_ORIGINS`에 프런트 origin 포함.

### A. curl/HTTP·정적으로 검증 가능
- A1. `GET /interviews/{live}` 화면 SSR 응답 200(스켈레톤 "면접장을 불러오는 중입니다..."), `npm run lint/tsc/build` 통과.
- A2. 정적 확인: `frontend/`에 `dangerouslySetInnerHTML`/`innerHTML` 0건, `WebcamPreview.tsx`에 `fetch`/`WebSocket`/`MediaRecorder`/`captureStream` 없음(서버 전송 코드 없음), `package.json`에 이 유닛이 추가한 의존성 없음(`@playwright/test`는 unit-22).
- A3. 백엔드 API(변경 없음) 회귀: 코드 제출 POST 201 / GET 최신순, 화이트보드 PUT 200 / GET 최신 1건 또는 `null`.
- A4. DEF-001: `autoStart` 임시 라우트의 SSR HTML에 "카메라 권한 요청 중..."이 나오고 "이 브라우저 또는 장치에서…"가 나오지 않음.

### B. 브라우저 자동화 필요 (unit-22 Playwright 사용 권장; 아래는 05단계에서 이미 통과한 항목 = 회귀 기준)
화면 상태별 기대 동작:
1. **live, 데스크톱(≥1200)**: 탭 2개 활성·`aria-pressed=false`, 보조 패널 안 보임, 웹캠 타일 "웹캠이 꺼져 있습니다"+켜기 버튼, "웹캠 숨기기/보기" 토글은 안 보임. 카메라 권한 프롬프트는 켜기를 누르기 전엔 뜨지 않음.
2. **코드 탭 클릭**: 패널 열림, 채팅:패널 ≈ 60:40(±3%p), `role`/`aria-modal` 없음, 제목 "코드 에디터", Monaco 표시. 편집→"미저장"→제출 `201`→"저장됨". 닫기("채팅으로 돌아가기") 후 다시 열면 **미제출 편집 내용 유지**. 새로고침 후 다시 열면 마지막 제출(python) 복원.
3. **화이트보드 탭**: 캔버스가 패널 폭을 넘지 않음, 그리기→저장 `PUT 200`→새로고침 후 복원(픽셀 존재). 코드 탭과 번갈아 눌러도 각 패널 상태 유지.
4. **웹캠**: 권한 거부(또는 `getUserMedia`를 `NotAllowedError`로 모킹) → "카메라 권한이 거부되었습니다."+"웹캠 없이 텍스트로 계속 진행할 수 있습니다.", 입력창·전송 정상. 가짜 카메라(`--use-fake-device-for-media-stream`) → 켜기→`active`("끄기" 버튼)→끄기→`srcObject` 해제. `video[aria-hidden="true"]`. 웹캠 관련 네트워크 요청 없음(허용 호스트: 앱 origin + Monaco CDN).
5. **태블릿(768~1199)**: 패널 열면 채팅:패널 ≈ 1:1 나란히, 캔버스 축소 표시.
6. **모바일(<768)**: 웹캠 토글이 보이고 기본 접힘(타일 없음)→클릭 시 펼침(`aria-expanded=true`), 패널은 전체화면(뷰포트 전체), `role=dialog`+`aria-modal=true`, 채팅/툴바 `inert`, 포커스가 패널 안으로, Esc 닫힘(Monaco 안에서의 Esc는 닫지 않음), 닫히면 열었던 탭에 포커스 복귀, 탭/웹캠 버튼 높이 ≥44px, 가로 스크롤 없음.
7. **`switch_to_coding`**: `/turns`를 202로, WS를 모킹해 `turn_result{control:{action:"switch_to_coding"}}` 전송 → 코드 패널이 자동 노출되고 `ai_text`가 채팅에 표시. `control.action="none"|"next_question"`이면 패널이 열리지 않음(**05단계 미확인 — 06에서 추가**).
8. **비-live(completed 등)**: 탭 2개 `disabled` + "면접이 진행 중(live)일 때만 사용할 수 있습니다." 문구, 채팅 이력 열람은 기존대로.
9. **재접속 복원 경계**: GET 실패(네트워크 차단) 시 "이전 세션의 코드를 불러오지 못했습니다."/"이전 캔버스를 불러오지 못했습니다." 안내 후 빈 상태로 계속 편집/그리기 가능(**05단계 미확인 — 06에서 추가**). 제출 실패(POST 5xx 모킹) 시 인라인 에러 + 본문 유지(**미확인**).
10. **회귀**: 기존 채팅 흐름 — 텍스트 전송 낙관적 표시, 음성 버튼 동의 프롬프트, 대기/처리중 문구 — 이 유닛 이전과 동일해야 함(**05단계에서는 텍스트 전송+WS 모킹 경로만 확인, 음성/동의 프롬프트는 미확인**).
11. **콘솔**: 위 시나리오 전체에서 hydration mismatch/React error 없음.
12. **HTML 형태 코드 제출**(`<img onerror>` 등) 복원 시 스크립트 실행·DOM 주입 없음.

### C. 수동/도구 필요 (자동화 밖 또는 미검증)
- axe 등 접근성 자동 검사, 실제 렌더 색 대비 측정, 스크린리더 낭독 확인, 실기 카메라·Safari·320px·확대 200%.
- 실제 AI 워커 경로(`control` 실값)로 `switch_to_coding` 유입 확인(07 통합).

## 11. Teardown / 규칙 K

- 내가 기동한 PID만 종료: 백엔드 32372(+자식 31732), 프런트 12160(+자식 29460, 7988) — `taskkill /PID … /T /F`. 종료 후 3320/8320 LISTEN 없음(TIME_WAIT 잔여만). 다른 사람 프로세스는 건드리지 않음: Adobe `node`(18736), unit-7 06 테스터의 uvicorn(8181/8322)·celery 워커, 잠시 떠 있던 `npm run lint`(11840/29588).
- DB: 내 계정·세션 2개와 그에 딸린 `code_submissions` 9행, `whiteboard_snapshots` 4행, `consents` 1행을 삭제하고(공유 개발 Postgres, 내가 만든 user id 기준), 재조회로 `user None` 확인. Redis는 내가 쓴 논리 DB 14(키 2개: `ai_pipeline` 큐, kombu 바인딩)만 비움. `highschool-db`/`toyo-db`·Docker 컨테이너 접근·중지 없음.
- `.harness-tmp/u20_*`(서버 스크립트·로그·시드/정리 스크립트·브라우저 검증 스크립트·PID 파일) 삭제(0개 남음). 기존 잔여물(다른 venv/로그)은 손대지 않음. 임시 라우트 `frontend/app/u20-autostart-check/` 삭제.
- 재생성된 추적 파일(`next-env.d.ts`, `tsconfig.tsbuildinfo`) 복구. 최종 `git status`(본 유닛 변경): `frontend/app/globals.css`, `.../[id]/page.tsx`, `.../components/{CodeEditorPanel,WhiteboardCanvas}.tsx`, `frontend/components/WebcamPreview.tsx`(수정), `.../components/InterviewSidePanel.tsx`, `frontend/lib/useMediaQuery.ts`(신규), 이 note. 그 외 표시된 변경은 병렬 유닛(unit-7 06/22/02 문서 갱신) 것이며 커밋/푸시 하지 않음.

## 12. traceability 제안 문구 (오케스트레이터 반영용 — 이 유닛은 파일을 수정하지 않음)

REQ-008 / REQ-015 / REQ-017 행 "작업 단위"에 `unit-20`(배선) 추가, "구현 상태"에 아래를 덧붙임 — 최종 보고에도 동일 문자열 제시.

- REQ-008 구현 상태 추가문구: `unit-20 배선 완료(05단계, L3): [C-06] 면접장에 코드 에디터 패널 배선 — 탭 토글, Desktop 60:40/Tablet 1:1 분할, Mobile 전체화면 모달(dialog·inert·Esc·포커스 복귀), live 세션에서만 활성, switch_to_coding 수신 시 자동 노출, 닫아도 미제출 편집 유지, 재접속 시 GET 복원(브라우저 실측). 코드는 Monaco 입력 전용·HTML 렌더링 경로 없음(XSS 프로브 통과). 06 정식(브라우저 자동화 포함) 대기, docs/harness/units/unit-20-note.md`
- REQ-015 구현 상태 추가문구: `unit-20 배선 완료(05단계, L3): [C-06] 소형 타일(160x120, 기본 off·사용자가 켤 때만 권한 요청, 모바일은 토글로 펼침·접히면 카메라 정지) 배선. 서버 전송 코드 없음(요청 호스트 실측). DEF-001 해소 — WebcamPreview 초기 상태를 서버/클라이언트 동일(autoStart→requesting)로 고정, 지원 여부는 마운트 후 판정, SSR·hydration 경고 0 확인. [C-05] 장치점검 화면은 미구현(질문 Q1 대기). 06 정식 대기, docs/harness/units/unit-20-note.md`
- REQ-017 구현 상태 추가문구: `unit-20 배선 완료(05단계, L3): [C-06] 면접장에 화이트보드 패널 배선(탭 토글, 분할/모달, live에서만 활성, 재접속 시 GET 복원 브라우저 실측). WhiteboardCanvas를 반응형 래퍼·디자인 토큰 색으로 조정(계약·저장 좌표계 불변). 화이트보드 자동 노출 신호는 03 §4.3 enum에 없어 사용자 탭 조작 전용. 06 정식 대기, docs/harness/units/unit-20-note.md`
- 비고란 제안: `unit-20(Feature I, L3) — 06 정식+07 필요. 기존 L1 부채(REQ-008 unit-9 / REQ-015 unit-16 / REQ-017 unit-17)의 브라우저 미검증 항목 다수를 unit-20 06/07에서 정산 가능. 미해결 질문: unit-20-note.md §9 Q1~Q4.`
