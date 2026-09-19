# unit-5 구현 노트 — Feature C. 대화형 인터뷰 엔진: 음성 턴제 STT 파이프라인 연동 (REQ-004, REQ-005)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §2.3(STT: faster-whisper 실측 RTF 0.22), §4.2/§4.3(턴 제출은 REST 단일 경로, 텍스트 JSON/음성 multipart), §6.2(DEC-023 — `biometric_voice` 동의 게이트, 실시간 재검사, 실제 차단), `docs/harness/04-ux-design.md`(v2, PASS) [C-06] `AudioRecorderControl`, `docs/harness/units/unit-4-note.md`/`unit-4-test.md`(기존 텍스트 턴 구조), `docs/harness/units/unit-14-note.md`(동의 API), `docs/harness/traceability.md` REQ-004/REQ-005 행

## 1. 구현 범위

### 백엔드

- `backend/app/services/stt_engine.py`(신규): `faster-whisper`(`small`, CPU, int8 — 03-design §2.3 실측 그대로) 어댑터. 모듈 전역 싱글턴으로 모델을 1회만 로드하고, `transcribe_audio(audio_bytes: bytes) -> str`이 업로드된 오디오를 **디스크에 쓰지 않고** `io.BytesIO`로 직접 디코딩해 텍스트를 반환한다. 언어는 한국어(`ko`)로 고정(02-planning §2 대상 시장, 언어자동감지 오버헤드 제거).
- `backend/app/api/v1/interviews.py`: `POST /interviews/{id}/turns`를 텍스트 전용에서 **텍스트/음성 겸용**으로 확장했다. 03-design §4.3이 "턴 제출은 항상 REST `POST /interviews/{id}/turns` 하나의 경로로만 이루어진다"라고 명시했으므로 별도 엔드포인트를 신설하지 않고, `Content-Type` 헤더로 분기(`multipart/form-data` → `_submit_voice_turn`, 그 외 → 기존 JSON 파싱 경로)했다.
  - `_submit_voice_turn`: (1) `_has_active_consent(db, user_id, ConsentType.biometric_voice)`를 **매 요청 실시간 DB 재조회**로 검사 — 실패 시 오디오를 전혀 읽지 않고(멀티파트 파싱조차 하지 않고) 즉시 `403 CONSENT_REQUIRED_VOICE`. (2) 통과 시 `request.form()`으로 `audio` 필드를 읽어 `stt_engine.transcribe_audio()`로 실제 변환. (3) 변환된 텍스트만 `TRANSCRIPTS(input_mode=voice, audio_ref=None)`로 영구 저장(오디오 바이트는 함수 종료와 함께 GC 대상, 어떤 파일도 디스크에 남지 않음 — 03-design §6.2 최소수집 원칙). (4) AI 응답 생성(LLM)은 unit-7 범위라 텍스트 턴과 동일하게 `enqueue_turn_job` 스텁으로 202 계약만 충족.
  - 공통 로직(`_ensure_turn_submittable`, `_next_turn_index`)을 텍스트/음성 양쪽에서 재사용하도록 추출했다(unit-4의 `submit_text_turn` 본문을 리팩터링한 것 — 동작은 그대로 보존, §4 게이트2 참고).
  - 입력 검증: 빈 오디오/필드 누락(422), 25MB 초과(422, 구현 세부값 — 설계서 미명시), STT 디코딩 실패(504 AI_SERVICE_TIMEOUT), 인식 결과 빈 문자열(422).
- `backend/requirements.txt`: `faster-whisper>=1.0,<2.0` 추가(실제 PyPI 존재 확인 — pip install 성공, §4 참고).

### 프론트엔드

- `frontend/app/interviews/[id]/page.tsx`: [C-06] `AudioRecorderControl`(idle/recording/uploading/error) 마이크 녹음 UI 추가.
  - 마이크 버튼 클릭 → (로컬에 알고 있는 `biometric_voice` 동의가 없으면) 인라인 동의 팝업 → `POST /consents`(biometric_voice) → `getUserMedia`+`MediaRecorder`로 녹음 시작 → 버튼 재클릭으로 정지 → `submitVoiceTurn()`으로 업로드.
  - 서버가 `403 CONSENT_REQUIRED_VOICE`를 반환하면(세션 도중 철회된 경우 등) 다시 동의 팝업을 띄운다 — DEC-023이 요구하는 "서버가 항상 최종 판정자"라는 원칙을 클라이언트도 그대로 반영(로컬 상태는 UX 편의용 선제 확인일 뿐).
  - 음성은 텍스트와 달리 클라이언트가 인식 결과를 미리 알 수 없으므로, 업로드 성공(202) 직후 `GET /transcripts`를 한 번 다시 호출해 서버가 실제로 저장한 STT 텍스트를 화면에 반영한다(텍스트 턴의 낙관적 UI와의 유일한 차이).
  - 마이크 미지원 브라우저(`MediaRecorder`/`getUserMedia` 없음)에서는 버튼 자체를 렌더링하지 않고 텍스트 입력만 노출(04-ux-design [C-06] "마이크 권한 없음" 원칙과 동일한 그레이스풀 디그레이드).
  - 무제한 업로드 방지를 위해 클라이언트에서 120초 녹음 후 자동 정지(구현 세부값, 백엔드 25MB 업로드 상한과 동일한 목적의 프런트 측 안전장치).
- `frontend/lib/api.ts`: `submitVoiceTurn()` 추가 — 공통 `request()` 헬퍼가 항상 `Content-Type: application/json`을 강제하므로 이 함수는 별도로 `fetch`를 호출해 브라우저가 `FormData`의 boundary를 스스로 설정하게 한다.
- `frontend/app/globals.css`: `.mic-button`/`.mic-button--recording`/`.voice-consent-prompt`/`.ghost-button` 클래스 추가(04-ux-design §3 토큰 재사용, 신규 토큰 없음).

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | STT를 별도 AI Worker(Celery)가 아니라 **HTTP 요청 핸들러 내에서 동기 실행** | 03-design §1.3의 큐/워커 아키텍처는 아직 실제로 존재하지 않는다(unit-2/4가 이미 `job_queue.py`를 "정당한 순서상 스텁"으로 남겨둠, unit-4-note.md §2-2 선례). 오케스트레이터 지시 3번이 "AI 응답 생성(LLM)은 스텁 처리하되 STT 변환 자체는 실제 동작해야 한다"고 명시했고, STT는 CPU 작업으로 실측 RTF 0.22(03-design §2.3)라 수 초 내 완료되므로 텍스트 턴이 이미 하던 것과 동일한 패턴(요청 핸들러 내 동기 처리 후 커밋)으로 구현하는 것이 범위에 맞다고 판단했다. §6.2가 요구한 "워커 단계에서도 STT 착수 전 동일 검사를 한 번 더(이중검사)"는 별도 워커 단계 자체가 없어 해당사항 없음 — 유일한 검사 지점(요청 핸들러)이 이미 매 요청 실시간 재조회이므로 요구 의도(캐시 금지, 즉시 반영)는 100% 충족한다 | 낮음(unit-7이 실제 Celery 워커를 만들 때 이 함수 본문을 워커 task로 옮기기만 하면 됨, 호출 시점의 검증 로직은 그대로 재사용 가능) |
| 2 | `audio` multipart 필드명은 설계서에 명시되지 않아 이 유닛이 확정 | 03-design §4.2/§4.3은 "음성은 multipart 오디오 파일로 동일 엔드포인트에 제출"이라고만 하고 필드명을 정의하지 않았다. `audio`로 확정(관례적 명명, 비가역성 낮음) | 낮음(프런트/백엔드 양쪽 다 이 유닛이 함께 구현해 필드명 불일치 리스크 없음, 바꿔도 두 파일만 수정) |
| 3 | 음성 파일 업로드 상한 25MB, 클라이언트 녹음 상한 120초 | 설계서 미명시 구현 세부값. 무제한 업로드로 서버 메모리를 소모하지 않기 위한 최소 안전장치(§6.2 최소수집과도 정합 — 애초에 오래 붙잡을 데이터를 만들지 않음) | 낮음(상수 변경만으로 조정 가능) |
| 4 | `POST /turns`가 FastAPI의 자동 pydantic 바디 파싱 대신 `Request`를 직접 받아 `Content-Type`으로 수동 분기 | 03-design §4.3이 텍스트/음성을 **같은 경로**로 강제했고, FastAPI/Starlette 라우팅은 같은 (path, method)에 두 개의 핸들러를 등록할 수 없어(무엇을 먼저 매칭할지 content-type으로 나누는 선언적 방법이 없음) 불가피한 구현 방식이다. 부작용: OpenAPI 자동생성 문서에서 이 엔드포인트의 JSON 바디 스키마가 더 이상 표시되지 않는다(Swagger UI "Try it out"에서 텍스트 요청 예시가 안 보임) — 실제 요청/응답 계약 자체는 curl로 전부 검증했으므로(§4) 기능 결함은 아니고 문서화 편의 손실만 있다 | 중간(다시 두 개의 명시적 pydantic 파라미터로 나누려면 별도 경로가 필요해 03-design §4.3의 "단일 경로" 원칙과 충돌 — 설계서가 바뀌지 않는 한 이 구조 유지가 맞음) |
| 5 | AI Worker의 STT 완료 후 실제 `stage_update`(`stage=stt`)/`turn_result` WS push는 여전히 오지 않음 | unit-4와 동일한 스텁 경계(`enqueue_turn_job`이 job_id만 발급) — LLM 응답 생성 자체가 unit-7 범위이므로 이번 유닛은 그 전 단계(STT)까지만 실제로 채운다. 프런트는 음성 제출 성공 후 `GET /transcripts` 재조회로 STT 결과만 보여주고, 이후 AI 응답은 텍스트 턴과 동일하게 12초 타임아웃 후 안내 문구로 전환된다 | 해당 없음(unit-7 완료 시 자연히 해소) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **격리 venv 필수**: 이 유닛은 `.harness-tmp/venv_05_unit5`를 새로 만들어 사용했다(DEC-027 재발 방지 지시 그대로 — 다른 유닛과 공유하지 않음). 06단계도 별도 venv를 새로 만들거나 이 venv를 그대로 재사용할 수 있으나(재사용 시 `pip install -r backend/requirements.txt` 재확인 권장), **다른 병렬 유닛의 venv를 건드리지 말 것**.
- **첫 요청 지연**: faster-whisper 모델은 프로세스당 1회 로드되며 로드 자체는 서버 기동 후 첫 음성 요청이 들어올 때 지연 로딩(lazy singleton)된다. 이번 실측 환경에서는 로드 2~3초 내외였으나(03-design §2.3 최초 실측 17.78초와 차이가 있음 — 캐시/디스크 상태에 따른 편차로 추정) 첫 음성 테스트 요청은 모델 로드 시간이 더해져 응답이 다소 늦을 수 있다(관측된 첫 요청 전체 소요 약 17초 — 모델 로드+실제 변환 포함, 두 번째 요청부터는 수 초 이내). 이는 결함이 아니라 설계서 §5.3이 이미 언급한 "모델 로드는 1회성, 워커 상시 기동으로 상쇄 가능" 특성 그대로다.
- **테스트용 실제 음성 파일이 필요함**: 이 유닛은 실제 사람 음성이 없어 `gTTS`(Google TTS, 인터넷 필요 — DEC-007상 허용됨)로 한국어 문장을 합성해 테스트 오디오를 만들었다. `gTTS`는 **런타임 의존성이 아니며 requirements.txt에 없다** — 순수 테스트 도구다. 06단계가 자체 재현하려면 동일하게 임의의 실제 한국어 음성 파일(mp3/wav/webm 등 PyAV가 디코딩 가능한 포맷)을 준비해야 하며, 무음/화이트노이즈만 있는 파일은 "인식 결과 빈 문자열 → 422" 경로로 빠질 수 있다(정상 동작).
- **동의 순서**: `biometric_voice` 동의가 없는 상태에서 음성을 제출하면 `403 CONSENT_REQUIRED_VOICE`이고, 이때 서버는 오디오를 전혀 읽지 않는다(TRANSCRIPTS에도 아무것도 남지 않음) — 이는 06단계가 "혹시 거부된 요청도 뭔가 저장되지 않았는지" 확인할 때 기준이 되는 정상 동작이다.
- **브라우저 실사용 검증 한계**: unit-4와 동일하게 이 환경에 브라우저 자동화 도구가 없어, 마이크 녹음 버튼의 실제 클릭→녹음→정지→업로드 상호작용은 코드 리뷰 + 백엔드 API 동일 계약의 curl/multipart 테스트로 갈음했다. `getUserMedia`/`MediaRecorder` 관련 브라우저 API 자체는 실제 브라우저(headless 포함)에서만 재현 가능하므로, 06/07단계가 실제 브라우저로 재검증할 것을 권장한다(unit-4-test.md가 이미 동일한 부채를 남긴 것과 같은 성격).
- **PostgreSQL**: 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용. 이번 유닛은 스키마 변경이 없어(TRANSCRIPTS는 unit-4가 이미 `input_mode=voice`/`audio_ref` 컬럼까지 만들어둠) **신규 Alembic 리비전이 없다**.

## 4. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app alembic/env.py`(`.harness-tmp/venv_05_unit5`) → **통과(에러 0건)**. `stt_engine.py`, `interviews.py` 변경분 전부 포함.
- 프론트엔드: `npx eslint "app/interviews/[id]/page.tsx" lib/api.ts`(unit-5 소유 파일 한정) → **에러 0건**(globals.css는 프로젝트 ESLint 설정 대상이 아니라는 경고만 출력, 다른 유닛에서도 동일하게 관찰된 무해한 경고). `npx tsc --noEmit`(프로젝트 전체, `.next` 캐시 재생성 후) → **에러 0건**(재생성 전에는 다른 병렬 유닛이 만들었다가 삭제한 `app/wcpreview-check-unit16-06/` 경로를 참조하는 stale `.next/types/validator.ts` 캐시 때문에 에러가 났으나, 이 유닛의 코드 문제가 아니라 `.next`가 gitignore 대상 빌드 캐시라 삭제 후 재생성해 해결함 — 소스 변경 없음). `npm run build`(Next.js 프로덕션 빌드) **성공**(`/interviews/[id]`가 동적 라우트로 정상 포함됨).

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 모든 편차와 사유 기록. 나머지(단일 `/turns` 경로, DEC-023 실시간 재검사, faster-whisper small/CPU/int8, 오디오 미저장, [C-06] AudioRecorderControl 변형)는 03-design §2.3/§4.2/§4.3/§6.2, 04-ux-design [C-06]/§4 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — 동의 없음(403), multipart 파싱 실패(422), 오디오 필드 누락(422), 빈 파일(422), 파일 과대(422), STT 디코딩 실패(504), 빈 인식 결과(422)까지 명시적 `AppError`로 처리. `stt_engine.py`의 `except Exception`은 다양한 하위 디코딩 예외를 단일 `SttTranscriptionError` 계약으로 승격하는 의도된 경계이며 조용히 삼키지 않고 `raise ... from exc`로 원인을 보존한다. 프런트의 `getUserMedia` 실패도 권한거부/미지원 안내로 명시 처리.
- [x] 시스템 경계(사용자 입력) 검증 — 업로드 오디오 크기 상한(25MB), 빈 파일/필드 누락 검증, STT 디코딩 실패를 사용자에게 노출 가능한 에러로 변환. `interview_id`는 FastAPI가 UUID로 강제. 텍스트 경로는 기존 `TurnCreate`(1~4000자) 검증을 그대로 유지.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — `faster-whisper`는 `pip install faster-whisper`로 실제 설치 성공(PyPI 실존, 버전 1.2.1 확인, `pip show faster-whisper` 결과 첨부 가능) 후 requirements.txt에 반영했다. 함께 설치된 `av`(PyAV, 18.1.0)/`ctranslate2`(4.8.2)는 faster-whisper의 선언된 의존성으로 자동 설치된 것이며 이 유닛이 직접 추가하지 않았다. 테스트 전용 `gTTS`는 requirements.txt에 추가하지 않았다(§3 명시).
- [x] 범위 외 변경 없음 — 코드에디터/웹캠/화이트보드/동의화면/운영자화면/대시보드 파일은 건드리지 않았다. LLM/TTS(unit-6/7)는 만들지 않았다 — `enqueue_turn_job` 스텁을 그대로 재사용(단, 텍스트 경로는 리팩터링으로 함수만 분리했을 뿐 동작은 완전히 동일하게 보존 — 아래 §6에서 회귀 없음을 curl로 재확인).

## 6. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit5` 신규 생성(DEC-027) → `pip install -r backend/requirements.txt` + `faster-whisper` 설치 성공.
2. **STT 단독 실증**: gTTS로 실제 한국어 발화("안녕하세요, 저는 3년차 백엔드 개발자입니다. 대규모 트래픽 처리 경험이 있습니다.") mp3를 합성 → `WhisperModel('small', device='cpu', compute_type='int8')`로 직접 변환 → 결과 텍스트를 UTF-8 코드포인트 단위로 원문과 대조해 `text.startswith('안녕하세요')` 등 **완전 일치** 확인(터미널 표시는 Windows 콘솔 코드페이지(cp949) 문제로 mojibake처럼 보였으나 실제 UTF-8 바이트는 무결 — unit-4-test.md TC-001이 겪은 것과 동일한 현상이며 동일한 방법(코드포인트/바이트 비교)으로 재확인함).
3. 기존 `final-project-db`(Docker, 포트 5544) 재사용, 신규 마이그레이션 없음(`alembic current` → `b84a71b986c5 (head)`, 변경 없음).
4. `ruff check app alembic/env.py` 통과.
5. `uvicorn app.main:app --port 8041`로 기동 후 Python(`requests`)으로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인 → `POST /interviews` → `ai_interview_notice` 동의 → `/start` → `202 live`
   - **동의 없이 음성 제출** → `403 CONSENT_REQUIRED_VOICE` 확인
   - `biometric_voice` 동의 등록 → **동일 음성 제출** → `202 {job_id}`, 소요시간 약 17.4초(모델 최초 로드 포함, §3 참고)
   - 텍스트 턴 제출(회귀 확인) → `202 {job_id}` — unit-4 동작 그대로 유지됨을 확인
   - `GET /transcripts` → `turn_index=0`(음성, `input_mode=voice`, `audio_ref=null`, `content_text`가 실제 STT 변환 결과), `turn_index=1`(텍스트) 순서로 정확히 반환
   - `biometric_voice` 동의 철회 → **동일 음성 제출 재시도** → `403 CONSENT_REQUIRED_VOICE` 재확인(DEC-023 실시간 재검사가 실제로 작동), transcripts 개수는 여전히 2건(거부된 시도가 저장되지 않음) 확인
   - 빈 오디오 파일 → `422`, `audio` 필드 누락 → `422`, 오디오가 아닌 쓰레기 바이트(가짜 mp3) → `504 AI_SERVICE_TIMEOUT`(디코딩 실패) 확인
   - 서버 로그(`uvicorn_05_unit5.log`)에 기대하지 못한 스택트레이스/예외 없음을 확인 후 삭제
6. 별도 세션으로 STT 변환 결과의 바이트 정확성만 다시 검증: 신규 후보 사용자로 전체 플로우 재현 후 `GET /transcripts` 응답의 `content_text`가 `'안녕하세요'`로 시작하는지 Python으로 직접 단언(`assert text.startswith('안녕하세요')` 상당, 실제로는 `True` 출력 확인).
7. 프런트: `npx eslint`(unit-5 소유 파일 한정 무결점), `npx tsc --noEmit`(프로젝트 전체 무결점, `.next` 캐시 재생성 후), `npm run build`(성공, `/interviews/[id]` 포함) 확인. 이 환경에 다른 병렬 유닛의 `next dev` 서버(포트 4116)가 이미 떠 있어 별도 포트로 SSR curl 검증을 시도했으나 Next 16의 단일 dev-lock 정책 때문에 두 번째 dev 서버가 뜨지 않았다 — **다른 유닛의 서버를 종료하지 않고** 이 검증은 생략했고, 대신 프로덕션 빌드 성공 + 코드 리뷰로 갈음했다(§3에 한계 명시).
8. 정리: uvicorn(8041) 프로세스 종료 확인(이후 curl 연결 거부 `000` 확인). 테스트로 만든 candidate 계정·interview·consent·transcript는 DB에서 직접 DELETE로 정리. 생성한 임시 파일(`.harness-tmp/u5_*.py`, `u5_test_audio.mp3`, `u5_stt_result.txt`, `uvicorn_05_unit5.log`, `nextdev_unit5.log`, `frontend/tsconfig.tsbuildinfo`)은 전부 삭제. `frontend/next-env.d.ts`가 `.next` 캐시 재생성 과정에서 자동으로 바뀌었기에(Next.js가 관리하는 파일, "should not be edited" 명시) `git checkout --`으로 원복. `.harness-tmp/venv_05_unit5`는 다른 유닛들의 선례(venv_05_unit9/12, venv_06_unit17 등)와 동일하게 재사용 가능하도록 보존했다. `git status` 재확인 결과 이 유닛이 만든 변경(§1)과 병렬 진행 중이던 다른 작업 단위의 변경만 남고 임시 산출물은 없음 — 규칙 K 준수.

## 7. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. `live` 상태 세션의 소유자가 `biometric_voice` 동의를 **가지지 않은** 상태에서 실제 오디오 파일을 `audio` 필드로 `POST /interviews/{id}/turns`(multipart)에 제출하면 `403 CONSENT_REQUIRED_VOICE`가 반환되고, `GET /interviews/{id}/transcripts`에는 해당 시도로 인한 레코드가 전혀 추가되지 않는다.
2. 1과 동일한 사용자가 `POST /api/v1/consents`(`{"consent_type":"biometric_voice"}`)로 동의를 등록한 뒤 같은 오디오 파일을 다시 제출하면 `202`와 함께 문자열 `job_id`가 반환된다. 이어서 `GET /transcripts`를 조회하면 새 레코드가 `speaker=user`, `input_mode=voice`, `audio_ref=null`로 저장되어 있고 `content_text`는 실제 음성 내용을 반영한 비어있지 않은 한국어 텍스트다(정확한 워딩이 100% 일치할 필요는 없으나, 완전히 무관한 텍스트이거나 빈 문자열이면 결함).
3. 2 직후 텍스트 턴(`{"text":"..."}`, JSON)을 같은 세션에 제출하면 여전히 `202`가 반환되고 `turn_index`가 이전 음성 턴 다음 번호로 이어진다(텍스트/음성 턴이 같은 `turn_index` 시퀀스를 공유함, unit-4 회귀 없음).
4. 2에서 등록한 `biometric_voice` 동의를 `POST /consents/{id}/revoke`로 철회한 뒤 같은 세션에 다시 음성을 제출하면 `403 CONSENT_REQUIRED_VOICE`가 즉시 반환된다(캐시된 상태가 아니라 매 요청 재조회임을 증명).
5. `audio` 필드 없이(또는 빈 파일로) multipart 요청을 보내면 `422 VALIDATION_ERROR`가 반환되고, 오디오로 디코딩할 수 없는 임의 바이트를 보내면 `504 AI_SERVICE_TIMEOUT`이 반환된다 — 두 경우 모두 `TRANSCRIPTS`에 레코드가 남지 않는다.
6. `scheduled`/`completed` 상태의 세션에 음성을 제출하면(동의 여부와 무관하게) `409 VALIDATION_ERROR`가 반환된다(unit-4의 텍스트 경로와 동일한 상태 검사 로직 재사용 확인).
7. 로그인 상태에서 브라우저로 `/interviews/{live 세션 id}`에 접속하면 마이크 지원 브라우저에서 "음성으로 답변" 버튼이 보이고(마이크/`MediaRecorder` 미지원 환경에서는 버튼 자체가 없음), `biometric_voice` 동의가 없는 상태에서 처음 클릭하면 인라인 동의 안내가 표시된다 — 이 항목은 이 환경에 브라우저 자동화 도구가 없어 06단계도 실제 클릭 상호작용을 재현하지 못할 가능성이 높다(§3 한계, unit-4와 동일한 부채로 traceability.md에 기록 필요).
