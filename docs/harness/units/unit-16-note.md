# unit-16 구현 노트 — Feature H. 부가 UX: 웹캠 프리뷰(비분석) (REQ-015)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/04-ux-design.md`(v2, PASS) [C-05] 면접 준비/장치테스트 화면 §2, [C-06] 면접장 웹캠 프리뷰 소형 타일 §2, §4 `WebcamPreviewTile` 컴포넌트 명세, §5-5(접근성: 웹캠 프리뷰는 장식 요소 → `aria-hidden`), §5-9(대체 입력 경로 보장), `docs/harness/traceability.md` REQ-015 행

## 0. 병렬 작업 격리 확인

이 유닛은 unit-4(면접장 메인/채팅)·unit-9·unit-14(동의/삭제)·unit-18(운영자 모니터링)과 동시에 병렬 진행 중이라는 지시를 받았다. 오케스트레이터 지시에 따라 **신규 독립 컴포넌트 하나만** 만들고 다른 유닛이 다루는 파일(면접장 메인 레이아웃 `frontend/app/interviews/[id]/page.tsx`, 채팅, 코드에디터, 인증/동의, 운영자 화면, `frontend/lib/api.ts`, `frontend/app/globals.css`, 백엔드 전체)은 전혀 건드리지 않았다.

- 신규 생성 파일: `frontend/components/WebcamPreview.tsx` **(단 하나, 신규 디렉터리)**.
- 기존 파일 수정: **없음**(백엔드 변경 없음 — REQ-015는 03-system-design상 클라이언트 전용, 서버 API 불필요가 정상임이 traceability.md에 이미 명시되어 있음).
- 작업 시작 전/후 `git status`로 `frontend/app/interviews/`, `frontend/app/admin/`, `frontend/lib/api.ts`, `frontend/app/globals.css`, `backend/` 하위 파일에 이 유닛이 손댄 흔적이 없음을 확인함. **파일 범위 충돌 없음.**
- 메인 화면([C-05]/[C-06])에 실제로 삽입(wiring)하는 작업은 지시대로 하지 않았다 — 이후 통합 작업(면접장 메인 레이아웃을 담당하는 유닛)에서 `import WebcamPreview from "@/components/WebcamPreview"`로 가져다 쓰면 된다.

## 1. 구현 범위

### 프론트엔드 (신규 파일 1개)

`frontend/components/WebcamPreview.tsx` — 순수 클라이언트 컴포넌트(`"use client"`).

- `navigator.mediaDevices.getUserMedia({ video: true, audio: false })`로 로컬 웹캠 스트림을 받아 `<video>` 엘리먼트(`muted`, `playsInline`, `autoPlay`, 좌우반전 `scaleX(-1)` — 셀피 미러링 관례)에 미리보기로 표시한다.
- **서버로 영상을 전송하는 코드가 전혀 없다.** `fetch`/`WebSocket`/`FormData` 등 네트워크 API를 이 파일에서 일절 import하지 않았고, 받은 `MediaStream`은 컴포넌트 스코프(`useRef`) 밖으로 나가지 않는다. DEC-008(표정/감정 분석 Out-of-Scope)과 REQ-015("AI 분석 없음")를 코드 구조로 보장.
- Props: `autoStart?: boolean`([C-05] 장치 테스트 화면처럼 진입 시 자동으로 권한 요청), `variant?: "panel" | "tile"`([C-05] 큰 패널 vs [C-06] 소형 타일, 04-ux-design §6 모바일 규칙 "웹캠 프리뷰는 기본 최소화" 대응 — `tile`은 160×120 고정), `className?: string`.
- 상태 머신은 04-ux-design §4 `WebcamPreviewTile` 명세(`active, permission-denied, off, unsupported`)에 §2 [C-05]의 로딩 상태(`requesting`)와 일반 오류(`error`)를 더해 6종으로 구현:
  - `off` — 빈 상태. "웹캠이 꺼져 있습니다" + "웹캠 미리보기 켜기" 버튼.
  - `requesting` — 로딩. `aria-live="polite"`로 "카메라 권한 요청 중..." 안내(스피너 대신 텍스트 — §5-7 `prefers-reduced-motion` 대응 겸용, 이 컴포넌트에는 애니메이션 자체가 없어 별도 reduce 분기 불필요).
  - `active` — 정상. 비디오 표시 + "끄기" 버튼(`aria-label="웹캠 미리보기 끄기"`).
  - `permission-denied` — 에러. `role="alert"`로 "카메라 권한이 거부되었습니다" + "웹캠 없이 텍스트로 계속 진행할 수 있습니다"(§5-9 대체 입력 경로 안내, 이 컴포넌트 자체가 텍스트 모드를 강제하지는 않지만 문구로 명시) + 재시도 버튼.
  - `unsupported` — 에러. 브라우저/장치 미지원(`getUserMedia` 자체가 없거나 `NotFoundError`/`OverconstrainedError`) 안내 + 동일한 대체 경로 문구.
  - `error` — 기타 예외(`NotReadableError` 등 하드웨어 충돌 포함) + 재시도 버튼.
- 접근성: `<video>`는 04-ux-design §5-5 명시대로 `aria-hidden="true"`(장식적 요소, 정보 전달 목적 아님). 단, 상태 안내/버튼(꺼짐·에러·로딩 문구, 켜기/끄기/재시도 버튼)은 숨기지 않아 스크린리더 사용자도 상태를 인지하고 조작할 수 있다(§5-9 대체 입력 경로와 모순되지 않도록, 웹캠이 정보 전달 자체를 안 할 뿐 컨트롤 자체는 접근 가능해야 한다고 판단 — §5-5는 "미리보기 영상"에 한정된 지시로 해석, 근거는 §3 참고).
- 언마운트 또는 "끄기" 클릭 시 `MediaStreamTrack.stop()`으로 모든 트랙을 확실히 정지한다(카메라 인디케이터가 계속 켜져 있는 상태로 남는 사고 방지 — 20년차 관점에서 흔한 실수 지점).
- effect가 언마운트 이후에도 진행 중이던 `getUserMedia` 응답을 받아 setState하지 않도록 `cancelledRef` 취소 플래그를 둠(경쟁 상태 방지: 사용자가 `autoStart` 화면을 빠르게 벗어나는 경우 대비).

## 2. 설계서 대비 편차

없음. `WebcamPreviewTile` 상태 4종(`active/permission-denied/off/unsupported`)을 모두 구현했고, 로딩(`requesting`)·일반오류(`error`)는 04-ux-design [C-05] §2 "상태: 정상/로딩/빈상태/에러" 서술에 이미 근거가 있어 추가 질문 없이 확장했다(규칙 A 대상 아님 — 설계서가 이미 답을 준 경우).

## 3. 규칙 A 관련 — 접근성 `aria-hidden` 범위 판단

04-ux-design §5-5는 "웹캠 프리뷰: 장식적 요소이므로 `aria-hidden="true"`"라고만 되어 있어, 이걸 컴포넌트 전체(켜기/끄기 버튼 포함)에 적용할지 `<video>` 태그에만 적용할지 문언만으로는 두 해석이 가능했다. 그러나 §5-9 "대체 입력 경로 보장"과 §5 전반의 "키보드 내비게이션 모든 인터랙션 요소는 Tab 도달 가능" 원칙이 이미 정해져 있어, 컨트롤(버튼)까지 숨기면 그 두 원칙과 정면으로 충돌한다. 즉 실질적으로 결과가 달라지는 진짜 모호함이 아니라 상위 원칙으로 이미 해소되는 경우라고 판단해 `<video>` 요소에만 `aria-hidden`을 적용하고 질문 없이 진행했다.

## 4. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **실제 카메라 권한 허용/거부 UI는 브라우저 네이티브 프롬프트**라 자동화 스크립트만으로는 "허용" 경로(`active` 상태)를 끝까지 재현하기 어렵다. 06단계는 실제 브라우저(Chrome/Edge)에서 카메라가 연결된 장치로 수동 클릭 확인을 권장한다. 거부/미지원 경로는 브라우저 설정에서 카메라 권한을 차단하거나 카메라가 없는 환경(예: 헤드리스 서버)에서 재현 가능.
- 05단계 자체 검증은 브라우저 UI 클릭 없이 **서버 렌더링(HTTP 200) + 콘솔/서버 로그에 에러 없음**만 확인했다(아래 §6). `getUserMedia`는 브라우저 API라 Node/서버 사이드에서는 애초에 호출되지 않으므로(컴포넌트는 `off` 상태로 정적 렌더링됨), 실제 카메라 스트림 획득 자체는 06단계의 브라우저 수동/자동화 테스트 몫이다.
- 컴포넌트는 아직 어떤 화면에도 import되어 있지 않다(지시대로 wiring 생략). 06단계가 렌더링을 확인하려면 임시로 아무 클라이언트 컴포넌트에 `import WebcamPreview from "@/components/WebcamPreview"` 해서 마운트하거나, 통합 담당 유닛이 [C-05]/[C-06]에 실제로 삽입한 뒤 테스트해야 한다.

## 5. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. `<WebcamPreview variant="panel" autoStart={false} />`를 아무 페이지에 마운트하면 초기 상태는 "웹캠이 꺼져 있습니다" + "웹캠 미리보기 켜기" 버튼(빈 상태)이 렌더링된다.
2. "웹캠 미리보기 켜기" 버튼 클릭 → 브라우저 카메라 권한 프롬프트가 뜬다 → **허용**하면 `<video>`에 실시간 로컬 웹캠 화면이 표시되고 우하단에 "끄기" 버튼이 나타난다.
3. 위 상태에서 "끄기" 클릭 → 비디오가 사라지고 다시 빈 상태로 돌아가며, OS/브라우저의 카메라 사용중 표시기(예: 크롬 탭 아이콘의 카메라 점)가 꺼진다(트랙이 실제로 stop되는지 확인).
4. 카메라 권한을 **차단**한 상태에서 "켜기" 클릭 → "카메라 권한이 거부되었습니다" + "웹캠 없이 텍스트로 계속 진행할 수 있습니다" 문구 + "다시 시도" 버튼이 뜬다(에러 상태). 이 상태에서도 페이지의 다른 기능(텍스트 입력 등, 통합 후 기준)은 막히지 않아야 한다.
5. 카메라 장치가 없는 환경에서 "켜기" 클릭 → `unsupported` 상태 문구가 뜬다.
6. `<WebcamPreview variant="tile" autoStart={true} />`를 마운트하면 마운트 즉시(권한 요청 없이 대기 없음) "카메라 권한 요청 중..." → 허용 시 자동으로 `active`로 전환된다([C-05] 자동 테스트 화면 시나리오).
7. 개발자도구 콘솔에 이 컴포넌트로 인한 에러/경고가 없어야 한다(특히 React `act()` 경고나 `setState on unmounted component` 경고 없음 — 언마운트 시 스트림 정지 및 `cancelledRef` 확인).
8. 네트워크 탭에서 이 컴포넌트 동작으로 인한 아웃바운드 요청이 전혀 발생하지 않아야 한다(서버 미전송 확인, REQ-015 핵심 검증 포인트).

(05단계 자체 검증에서 1, 7 일부(서버 렌더 시 콘솔/로그 에러 없음)는 §6으로 확인. 2~6, 7의 클라이언트 런타임 부분, 8은 실제 브라우저 카메라 권한 조작이 필요해 06단계 몫으로 남김 — 위 §4에 정직하게 명시.)

## 6. 게이트 1 — 정적 분석/린트

- `npm run lint`(ESLint 9, `eslint-config-next` + `eslint-plugin-react-hooks` v7 `react-hooks/set-state-in-effect` 룰 포함) → **통과**.
  - 최초 시도에서 `useEffect` 안에서 `startPreview()`(내부에서 동기적으로 `setStatus("requesting")` 호출)를 직접 호출해 `react-hooks/set-state-in-effect` 위반 3회 연속 발생. 원인 분석 후: (1) `autoStart` 여부에 따른 초기 상태를 `useState`의 lazy initializer로 옮기고, (2) 지원 여부(`isGetUserMediaSupported()`) 판단을 effect 호출 전으로 끌어올려 `acquireStream`(순수하게 `await` 이후에만 setState하는 함수) 내부에 동기적 setState 분기가 전혀 없도록 재구성했다. 그래도 컴파일러 규칙이 "effect가 직접 호출하는 함수가 setState를 어디서든 호출하면" 정적으로 플래그하는 것을 확인(비동기/동기 위치를 구분하지 않음) → 이는 카메라 같은 외부 시스템과의 정당한 동기화(파생 상태 계산이 아님, `getUserMedia` 자체가 본질적으로 비동기)이므로 해당 줄에 근거 주석과 함께 `eslint-disable-next-line react-hooks/set-state-in-effect`를 명시적으로 남겼다(unit-18-note.md §7이 기록한 것과 동일 계열의 룰이며, 이번엔 순수 외부 브라우저 API 동기화 케이스라 disable 예외로 처리).
- `npm run build`(`next build`, Turbopack, TypeScript 타입체크 포함) → **통과**(컴파일 성공, 타입 에러 0건). 컴포넌트가 아직 어떤 라우트에도 import되지 않아 빌드 산출물에는 포함되지 않지만, `tsconfig.json`의 `include: ["**/*.tsx", ...]` 덕분에 타입체크 대상에는 포함됨을 확인.
- 백엔드 변경 없음 — `ruff`/`mypy` 등 백엔드 정적분석 대상 아님.

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2 참고(편차 없음).
- [x] 에러 처리가 누락된 경로 없음 — `getUserMedia` 실패는 `try/catch`로 포착해 `DOMException.name`별로 `permission-denied`/`unsupported`/`error` 상태로 분기하며, 예외를 삼키고 무시하는 `catch {}` 빈 블록이 없다.
- [x] 입력값 검증 — 이 컴포넌트는 사용자 텍스트/폼 입력을 받지 않는다(브라우저 미디어 API 응답만 다룸). 시스템 경계는 "브라우저가 반환하는 `MediaStream`/`DOMException`"이며, `instanceof DOMException` 타입 가드로 안전하게 분기했다(타입 없는 `any` 캐스팅 없음).
- [x] 하드코딩된 시크릿/자격증명 없음.
- [x] 신규 외부 패키지 없음 — `react`(기존 의존성)만 사용, `package.json` 변경 없음. 별도 레지스트리 조회 불필요.
- [x] 범위 외 변경(곁다리 리팩터링) 없음 — 신규 파일 1개만 추가했고 기존 파일은 전혀 수정하지 않았다(§0 참고).

## 8. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `npm run lint`, `npm run build` 모두 통과(§6).
2. 임시로 `frontend/app/wcpreview-check/page.tsx`를 만들어 `<WebcamPreview variant="panel" autoStart={false} />`와 `<WebcamPreview variant="tile" autoStart={false} />` 두 인스턴스를 마운트하고 `npm run dev`(Turbopack)로 기동한 뒤 `curl http://localhost:3000/wcpreview-check` → **HTTP 200**, 렌더링된 HTML에 "웹캠이 꺼져 있습니다"/"웹캠 미리보기 켜기" 텍스트가 두 인스턴스 모두에서 정상 출력됨을 확인. dev 서버 로그에 에러/경고 없음.
   - (참고: 폴더명을 처음 `__wcpreview-check`(언더스코어 prefix)로 만들었더니 Next.js App Router가 이를 "private folder"로 취급해 404가 발생 — 즉시 언더스코어 없는 이름으로 교체해 재확인함. 이 시행착오는 unit-16 구현 자체와 무관한 라우팅 규칙 이슈였음을 기록.)
3. 검증 완료 후 임시 확인용 라우트(`frontend/app/wcpreview-check/`)를 삭제하고 dev 서버 프로세스를 종료했다. `git status` 확인 결과 이 유닛이 남긴 파일은 `frontend/components/WebcamPreview.tsx`(신규) 하나뿐이며, 다른 유닛의 진행 중 변경사항 외에 잔여 임시 파일이 없음(규칙 K 준수).

## 9. traceability.md 갱신

REQ-015 행: "작업 단위"는 기존 `unit-16` 유지, "구현 상태"를 "구현 완료(05단계, L1)"로 갱신. 비고에 "06 경량/07 미실행 — L1 부채, 08 착수 전 정산 필요"와 "메인 화면 wiring은 통합 담당 유닛 몫"을 명시.
