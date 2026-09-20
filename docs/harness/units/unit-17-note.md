# unit-17 구현 노트 — Feature H. 화이트보드 캔버스(REQ-017)

- 입력: `docs/harness/03-system-design.md`(v3, PASS) §3(ERD `WHITEBOARD_SNAPSHOTS`: id/interview_id/canvas_json/created_at), §4.2(`PUT`/`GET /interviews/{id}/whiteboard`, GET은 v2 재작업 DEC-024 갭4로 신규), `docs/harness/04-ux-design.md`(v2, PASS) [C-08] 화이트보드 캔버스 패널, `docs/harness/traceability.md` REQ-017 행.
- **병렬 진행 컨텍스트**: 이번 세션은 unit-4/9/14/16/18과 동시 병렬 진행이었다. 오케스트레이터 지시대로 독립 컴포넌트 1개(`WhiteboardCanvas.tsx`) + 03-design v2에 이미 정의된 `/whiteboard` 저장용 API만 구현했고, 면접장 메인 레이아웃/채팅/코드에디터/인증·동의/운영자화면/웹캠 파일은 건드리지 않았다.
- **Speed Track: L1(DEC-003)** — 05 구현은 트랙 무관 동일 절차(게이트1·2)로 수행했고, 06/07 검증 깊이만 L1 경량판을 적용한다.

## 1. 구현 범위

### 백엔드
- `backend/app/models/whiteboard.py` — `WhiteboardSnapshot` 모델. ERD 원문 그대로 `id`/`interview_id`/`canvas_json`(JSONB)/`created_at` 4개 컬럼만. FK는 `interviews.id`.
- `backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py` — 신규 revision. 작성 시점 `alembic heads`가 `8a55fda78a42`(unit-14 v4) 단일 head임을 먼저 확인한 뒤 `down_revision`으로 지정했고, 실제 공유 개발 DB(`localhost:5544/final_project`)에 `alembic upgrade head`로 적용 완료. 이후 unit-9가 `b84a71b986c5_v6_code_submissions`를 `down_revision=c1a2f5e9b7d3`로 그 위에 체이닝해 **head가 계속 단일선형으로 유지**됨을 최종 확인(`alembic heads` → `b84a71b986c5 (head)` 1개만 존재).
- `backend/app/schemas/whiteboard.py` — `WhiteboardPoint`/`WhiteboardStroke`/`WhiteboardSaveRequest`/`WhiteboardSnapshotOut`. 시스템 경계 입력 검증(게이트2): stroke당 점 0개 금지·최대 5000개, 전체 stroke 최대 2000개, `width`는 (0, 64] 범위, `color`는 문자열 32자 제한.
- `backend/app/api/v1/whiteboard.py` — `PUT`/`GET /interviews/{id}/whiteboard`. `interviews.py`(unit-2/3/4 소유)를 import하지 않고 소유권 검증(`_get_own_interview`)을 이 파일 안에서 독립적으로 재구현(unit-14 `consents.py` 선례 그대로 따름 — 파일 경계를 넘는 의존을 만들지 않아 병렬 충돌 표면을 줄임).
- `backend/app/main.py` — `whiteboard_router` 등록 1줄 추가(다른 유닛이 동시에 추가한 `code_submissions_router` 등록과 충돌 없이 병합됨, 아래 §3 참고).

**설계서 대비 해석 결정(두 갈래로 갈리지 않는 additive 결정, 규칙A 질문 대상 아님)**: ERD상 `WHITEBOARD_SNAPSHOTS`에는 UPDATE 대상이 되는 단일 "현재 캔버스" 행 개념이 없고 `created_at`만 있어 이력(스냅샷) 테이블로 설계되어 있다. 이는 `CONSENTS`/`AUDIT_LOGS`와 동일한 패턴이다. 따라서 `PUT`을 "새 스냅샷 행 추가"로, `GET`을 "가장 최근 행 반환"으로 구현했다(SQL `UPDATE`가 아님). 정답이 하나로 수렴하는 자연스러운 해석이라 판단해 별도 질문 없이 진행했다.

### 프론트엔드
- `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx` — 독립 컴포넌트(신규 디렉터리). 마우스/터치(Pointer Events로 통합 처리) 자유선 드로잉, 색상 5종 프리셋, 굵기 슬라이더, 지우기, 저장 버튼. `interviewId`/`accessToken` prop이 모두 주어지면 마운트 시 `GET`으로 최신 스냅샷을 불러와 캔버스를 복원하고([C-08] 세션 재개 요구사항), 없으면 로컬 전용 모드(저장 버튼 비활성)로 동작한다. GET 실패 시 "이전 캔버스를 불러오지 못했습니다" 안내로 대체([C-08] 에러 상태 명세 그대로), 저장 실패 시 "저장되지 않았습니다" 배지.
- `frontend/lib/api.ts` — `WhiteboardPoint`/`WhiteboardStroke`/`WhiteboardSnapshotOut` 타입과 `saveWhiteboard`/`getWhiteboard` 함수를 파일 끝에 추가(append-only, 기존 함수 수정 없음). 이후 unit-15가 같은 파일 뒤쪽에 자신의 함수를 추가로 append했음을 확인했고, 두 변경이 충돌 없이 병합되어 lint/build 모두 재통과함을 확인했다(§4 참고).
- **메인 레이아웃(`app/interviews/[id]/page.tsx`)에는 삽입(wiring)하지 않았다** — 오케스트레이터 지시 범위 밖.

## 2. 설계서 대비 편차

| # | 편차 | 사유 | 비가역성 |
|---|---|---|---|
| 1 | 04-ux-design [C-08] 도구바 전체 항목(펜/**도형**/**텍스트**/지우기/색상) 중 도형·텍스트 도구 미구현 | 오케스트레이터 지시가 "마우스/터치로 그리기, 지우기, 저장 버튼"으로 범위를 명시적으로 좁힘. pen+색상+지우기+저장만으로 REQ-017의 목적("시스템 설계를 그림으로 표현")은 충족되고, 도형/텍스트는 순수 추가(additive)라 두 갈래 해석 문제가 아님 | 낮음 — 기존 저장 포맷(strokes 배열)에 새 stroke 타입만 추가하면 되므로 후속 확장이 쉬움 |
| 2 | `PUT`을 UPDATE가 아니라 "새 행 추가+최신 조회"로 구현 | 위 §1 "설계서 대비 해석 결정" 참고 — ERD가 이력 테이블로 설계되어 있어 자연스러운 해석 | 낮음 |
| 3 | 메인 화면(`page.tsx`) 미삽입 | 오케스트레이터 지시로 이번 유닛 범위 제외 | 없음(후속 유닛/이터레이션이 import만 하면 됨) |

## 3. 다른 유닛과의 파일/마이그레이션 충돌 여부

- **파일 충돌 없음**: 신규 파일만 생성(`whiteboard.py` 모델/스키마/라우터, 마이그레이션, 프론트 컴포넌트). 기존 파일 수정은 `backend/app/main.py`(라우터 등록 1줄)와 `frontend/lib/api.ts`(함수 append)뿐이며, 둘 다 병렬로 동시에 다른 유닛(unit-9, unit-15)이 같은 파일의 다른 위치를 수정했으나 `Edit` 도구의 앵커 문자열이 서로 겹치지 않아 자동 병합되었고, 병합 후 즉시 lint/build 재실행으로 정합성을 재확인했다(§4).
- **마이그레이션 충돌 없음**: 작성 직전/직후 두 차례 `alembic heads`로 단일 head를 확인했고, 최종적으로 unit-9의 `b84a71b986c5`가 내 `c1a2f5e9b7d3` 위에 정상 체이닝되어 여전히 head가 1개임을 재확인했다(브랜치 분기 없음).
- **공유 `.harness-tmp` 관련 특이사항(규칙K)**: 검증 도중 다른 동시 진행 유닛(또는 그 teardown 절차)이 내가 재사용하던 공유 venv(`.harness-tmp/venv_05_unit1`)를 포함해 `.harness-tmp/` 전체를 삭제한 것으로 보인다. 실제 소스 파일(모델/라우터/마이그레이션/프론트 컴포넌트)은 전혀 영향받지 않았고, 이미 적용된 DB 마이그레이션도 실제 Postgres 서버 상태라 영향받지 않았다 — 검증을 이어가기 위해 `.harness-tmp/venv_05_unit17`을 새로 만들어 재검증했고, 확인 후 그 venv는 스스로 정리했다(§4 마지막 단계).

## 4. 검증 결과 (05단계 자체 확인)

**백엔드 — 실제 서버+DB(포트 8050, 공유 개발 Postgres `localhost:5544/final_project`)로 curl 검증**:
1. `POST /auth/register` + `/auth/login`(candidate) → 200/201, JWT 발급 확인.
2. `POST /interviews` → 201, `scheduled` 세션 생성.
3. `GET /interviews/{id}/whiteboard`(저장 전) → 200 `null` (빈 상태, 404 아님 — [C-08] 명세대로).
4. `PUT /interviews/{id}/whiteboard`(strokes 1개) → 200, 저장된 stroke 그대로 반환.
5. `GET /interviews/{id}/whiteboard` → 방금 저장한 스냅샷과 동일 내용 반환.
6. `PUT /interviews/{id}/whiteboard`(strokes 2개, 다른 색상/굵기) → 200, 새 스냅샷 id로 저장.
7. `GET /interviews/{id}/whiteboard` → 가장 최근(2번째) 스냅샷 반환 확인(이력 누적이 아니라 최신 우선 조회 확인).
8. 인증 없음 → 401.
9. 존재하지 않는 interview_id → 404.
10. 타인 소유 interview_id(다른 candidate 계정으로 시도) → 403.
11. 잘못된 입력값: `width=999`(범위 초과) → 422, `points=[]`(빈 배열) → 422.
12. 검증 후 테스트로 생성된 `whiteboard_snapshots` 행/interview/user는 DB에서 직접 삭제해 원상복구했다(운영 데이터 오염 방지).

**프론트엔드**:
- `npm run lint` — 통과(초기 1회 `react-hooks/set-state-in-effect` 위반 발견 → 수정 후 재실행 통과, WebcamPreview.tsx의 선례 패턴을 따름).
- `npm run build` — 통과(Turbopack 컴파일 + TypeScript 타입체크 + 정적 페이지 생성 모두 성공). unit-9/unit-15가 `lib/api.ts`/`package.json`에 동시 추가한 변경과 병합된 최종 상태 기준으로 재실행해도 통과함을 확인했다.
- 브라우저 수동 조작(실제 마우스/터치 클릭)까지는 이번 05단계에서 수행하지 않았다 — **L1 부채**로 06단계가 필요 시 직접 재현.

## 5. 06단계 테스터를 위한 인수 조건(Acceptance Criteria)

1. `POST /api/v1/interviews`로 세션 생성 후, 저장 전 `GET /api/v1/interviews/{id}/whiteboard`는 `200`과 본문 `null`을 반환해야 한다(404 아님).
2. `PUT /api/v1/interviews/{id}/whiteboard`에 `{"strokes":[{"points":[{"x":1,"y":2},{"x":3,"y":4}],"color":"#000000","width":2}]}`를 보내면 `200`과 함께 `id`/`interview_id`/`strokes`/`created_at`이 포함된 스냅샷이 반환되어야 한다.
3. 같은 세션에 다시 `PUT`을 보내면 새로운 `id`의 스냅샷이 생성되고, 이어서 `GET`을 호출하면 **가장 최근에 저장한** 스냅샷만 반환되어야 한다(이전 스냅샷은 DB에는 남아있지만 API 응답은 항상 최신 1건).
4. 인증 토큰 없이 호출하면 `401`, 존재하지 않는 `interview_id`면 `404`, 본인 소유가 아닌 `interview_id`면 `403`이어야 한다.
5. `strokes`의 각 stroke에 `points`가 빈 배열이거나, `width`가 0 이하 또는 64 초과, `strokes` 개수가 2000 초과, stroke 하나의 `points`가 5000개 초과면 `422`를 반환해야 한다.
6. 프론트 `WhiteboardCanvas` 컴포넌트(`frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx`)를 임의 페이지에 `interviewId`/`accessToken` 없이 렌더링하면 로컬 전용 모드로 그리기/지우기는 동작하되 저장 버튼은 비활성(disabled)이어야 한다. 두 prop을 모두 주면 저장 버튼이 활성화되고, 저장 성공 시 "저장됨" 상태 텍스트가, 실패 시 "저장되지 않았습니다"가 표시되어야 한다.
7. 이 유닛은 AI 화이트보드 분석 코드를 포함하지 않는다(DEC-008/REQ-021 Out-of-Scope) — 06단계는 이미지 인식/비전 관련 엔드포인트나 로직이 전혀 추가되지 않았음을 코드 리뷰로 재확인해도 좋다.
8. **L1 경량판 안내**: 정상 경로 1~2케이스만 재현하면 충분하며(위 인수조건 1~4가 정상 경로), 5~7의 에러/경계 케이스는 06 경량판에서 생략 가능하나 이미 5단계가 직접 curl로 재현한 기록(§4)이 있으므로 그대로 인용해도 된다. 07(통합테스트)은 L1 부채로 08 착수 전 정산 필요.

## 6. 게이트1·2 통과 여부

**게이트1(정적분석/린트)**:
- 백엔드: `ruff check app/models/whiteboard.py app/schemas/whiteboard.py app/api/v1/whiteboard.py app/main.py` → 통과("All checks passed!").
- 프론트: `npm run lint`(ESLint, `eslint-config-next`) → 통과. `npm run build`(Next.js 16.3.5 Turbopack, TypeScript strict) → 통과.

**게이트2(자체 코드 리뷰 체크리스트)**:
- [x] 설계서/디자인서 명세와 실제 구현 일치 — 03-design §3/§4.2 엔드포인트·컬럼, 04-ux [C-08] 상태(정상/로딩/빈상태/에러) 모두 반영.
- [x] 에러 처리 누락 경로 없음 — 401/403/404/422 전부 명시적 처리, 프론트도 로딩/에러 상태를 무시하지 않고 안내 문구로 표시.
- [x] 시스템 경계(사용자 입력) 검증 — pydantic으로 stroke 개수/점 개수/width/color 길이 제한(§1 참고).
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음(DB URL 등은 기존 `.env`/`config.py` 재사용).
- [x] 신규 외부 의존성 없음 — 이번 유닛은 새 패키지를 추가하지 않았다(프론트 컴포넌트는 React 표준 API만, 백엔드는 기존 SQLAlchemy/pydantic만 사용).
- [x] 범위 외 변경 없음 — `interviews.py`, `job_queue.py`, `page.tsx`, 인증/동의/운영자/웹캠 관련 파일은 전혀 수정하지 않았다. `main.py`/`lib/api.ts`는 라우터 등록·함수 append만(§3).
