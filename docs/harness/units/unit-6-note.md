# unit-6 구현 노트 — Feature C. 대화형 인터뷰 엔진: 오픈소스 TTS 연동 (REQ-006)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §2.5(TTS: Piper 선정, 실측 RTF 0.056, GPL-3.0-or-later 라이선스 리스크·격리 대응, DEC-017), §4.3(WS `turn_result.audio_url` 표기), §4.5(어댑터 인터페이스 원칙), §5.4(TTS 단계 타임아웃 10초), `docs/harness/units/unit-4-note.md`/`unit-5-note.md`(기존 턴 구조, STT 어댑터 선례), `docs/harness/traceability.md` REQ-006 행

## 1. 구현 범위

### 백엔드

- `backend/app/services/tts_engine.py`(신규): `ITTSEngine` 어댑터 인터페이스(§4.5) + `PiperTTSEngine` 구현체.
  - **DEC-017 격리 원칙을 STT보다 한 단계 더 엄격하게 적용**: `stt_engine.py`(faster-whisper)는 라이브러리를 프로세스 내에 직접 import해 싱글턴으로 상주시키지만, Piper는 GPL-3.0-or-later 라이선스 리스크(§2.5, §8-2)가 있어 **이 프로세스에 Piper 파이썬 패키지를 전혀 import하지 않는다** — 매 합성마다 `python -m piper`를 별도 서브프로세스로 실행하고, 텍스트 입력 파일 → WAV 출력 파일이라는 표준 파일 인터페이스로만 연동한다(설계서 §2.5 완화책 1번 그대로).
  - 한국어 음성모델 `ko_KR-kss-medium`(03-design §2.5 실측 선정 그대로)을 최초 합성 요청 시점에 `python -m piper.download_voices`(이 역시 별도 서브프로세스)로 `backend/var/piper_voices/`에 1회 다운로드하고 이후 재사용한다(lazy, 스레드 락으로 동시 다운로드 경쟁 방지 — `stt_engine.py`의 lazy 싱글턴 패턴과 동일 원칙).
  - `synthesize_speech_file(text: str) -> str`: 합성된 WAV 바이트를 `backend/var/media/tts/{uuid}.wav`에 저장하고 `/media/tts/{uuid}.wav` 형태의 상대 URL을 반환한다 — §4.3의 `turn_result.audio_url` 표기(`/media/xxx.wav`)와 동일한 경로 규칙.
  - 서브프로세스에 텍스트를 stdin 파이프로 넘기지 않고 **UTF-8 임시 파일**(`-i` 옵션)로 넘긴다 — stdin 파이프 경유 시 Windows 콘솔/서브프로세스 인코딩 문제로 한글이 surrogate로 깨지는 것을 실측으로 확인(§4)하고 이 방식으로 우회했다(unit-4/5-note.md가 이미 겪은 것과 동일 계열 현상).
  - 예외는 `TtsSynthesisError` 단일 계약으로 승격(모델 다운로드 실패/서브프로세스 비정상종료/타임아웃 모두 포함).
- `backend/app/api/v1/interviews.py`: `POST /interviews/{id}/tts-preview`(신규) 엔드포인트 추가.
  - **03-design §4.2 REST 표에는 없는 엔드포인트**(§2 편차 참고) — 본인 소유 인터뷰 세션 컨텍스트에서 임의 텍스트(1~500자)를 `tts_engine.synthesize_speech_file()`로 실제 합성해 `{"audio_url": "..."}`을 반환한다.
  - 오케스트레이터 지시("(a) TTS 서비스 모듈이 임의의 텍스트를 받아 음성을 합성해 저장/반환하는 것을 실제로 동작시키고 curl/직접 호출로 검증, (b) 클라이언트가 재생할 수 있는 API 엔드포인트를 준비")를 그대로 충족하기 위한 준비/검증 경로다. LLM(unit-7)이 아직 없어 "AI가 생성한 응답 텍스트" 자체가 존재하지 않으므로, 이 엔드포인트는 실제 인터뷰 턴 흐름(`turn_result`)에 연결되어 있지 않다 — unit-7이 `speak_text`를 만들면 동일한 `synthesize_speech_file()` 함수를 호출해 `turn_result.audio_url`을 채우면 된다(연결 지점은 §3에 명시).
  - 실패 시 `AI_SERVICE_TIMEOUT`(504)로 매핑(§5.4 TTS 단계 장애 대응과 동일 원칙).
- `backend/app/main.py`: `/media` 경로에 `StaticFiles`를 마운트해 `backend/var/media/`를 정적 서빙한다 — §4.3 `audio_url` 표기(`/media/xxx.wav`)와 동일한 URL 규칙, `/api/v1` 프리픽스 없음(ws.py의 `/ws/interviews/{id}`와 동일하게 프리픽스 예외 처리).
- `backend/requirements.txt`: `piper-tts>=1.8,<2.0` 추가(실제 PyPI 존재 확인, 설치 성공, §4 참고).
- `.gitignore`: `backend/var/`(Piper 음성모델 다운로드 캐시 + 합성된 오디오 산출물, 런타임 생성물이라 커밋 대상 아님) 추가.

### 프론트엔드

- 변경 없음. 오케스트레이터 지시가 백엔드(`interviews.py`) 확장만 명시했고, 실제 AI 음성 응답을 재생할 UI(오디오 플레이어)는 unit-7이 실제 `turn_result.audio_url`을 채운 뒤에 붙이는 것이 자연스럽다 — 지금 프런트에 재생 버튼을 추가하면 연결될 데이터가 없어 죽은 UI가 된다.

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `POST /interviews/{id}/tts-preview`가 03-design §4.2 REST 표에 없는 신규 엔드포인트 | 오케스트레이터 지시가 "TTS 서비스 자체는 실제로 완성하되 실제 턴 흐름 연결은 unit-7 이후"라고 명시했고, LLM이 없는 지금 시점에는 §4.3의 `turn_result.audio_url` 경로로 검증할 방법이 구조적으로 없다(어떤 "AI 응답 텍스트"도 존재하지 않음). 이 엔드포인트는 그 대신 (1) TTS 어댑터가 실제로 텍스트→음성 변환을 하고 (2) 그 결과를 API로 내려받아 재생 가능함을 증명하는 최소 경로로, unit-4의 `GET /transcripts` 추가 선례(구조적으로 필요 + 설계서 공백)와 동일한 논리다 — 다만 이번 것은 unit-7이 실제 파이프라인을 완성하면 **더 이상 필요 없어질 수 있는 임시 성격의 준비 엔드포인트**라는 점이 다르다(unit-4 편차와 달리 영구 존재가 목적이 아님, 이후 유닛/07단계가 존치 여부를 재확인해야 함) | 낮음(신규 라우트 함수 하나, 호출부 의존 없음 — 제거해도 다른 기능에 영향 없음) |
| 2 | `text` 필드 최대 길이 500자로 제한(설계서 미명시 구현 세부값) | 이 엔드포인트는 실제 AI 응답이 아니라 진단/검증용 임의 텍스트 입력이므로, unit-4의 `TurnCreate.text`(4000자, 사용자 답변 길이 기준)보다 짧게 잡아도 목적(합성 동작 증명)에 지장이 없고 남용 범위를 줄인다. 전역 레이트리밋(REQ-038)은 unit-8 범위라 이 엔드포인트에는 적용되어 있지 않다 — 06/07단계가 이 점을 알아야 한다(§3) | 낮음(상수 하나) |
| 3 | Piper를 프로세스 내부에 전혀 import하지 않고 매 호출마다 서브프로세스로 재기동(모델을 상주시키지 않음) | DEC-017(§2.5)이 "정적 링크 금지, 별도 프로세스로만 연동"을 요구했고, faster-whisper(STT, MIT)처럼 인프로세스 싱글턴으로 상주시키면 GPL 코드가 이 애플리케이션 프로세스 주소공간에 실제로 로드되어 격리 의도가 약해진다고 판단했다. 대가로 매 요청마다 Python 인터프리터 기동+ONNX 모델 로드 오버헤드(약 2~3초)가 반복된다(§4 실측: 162자 텍스트 합성에 총 3.2초 소요, RTF 자체는 여전히 실시간보다 훨씬 빠름) — 03-design §5.1의 TTS 추정치(0.5~1.5초)보다 느리지만 §5.4의 TTS 단계 타임아웃(10초) 예산 안에는 충분히 들어온다. unit-7/08단계가 실제 부하테스트에서 이 오버헤드가 문제가 되면(동시 다중 요청 시 프로세스 기동 비용 누적) 상주 서버 방식(예: Piper HTTP 서버 모드나 장수명 서브프로세스+파이프 통신)으로 전환을 검토해야 한다(§3 인수인계) | 중간(모델 상주 방식으로 바꾸려면 GPL 격리 논리를 다시 검토해야 함 — 법무 검토 결과에 따라 방향이 달라질 수 있는 사안, §2.5 리스크와 직결) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **격리 venv 필수(DEC-027)**: 이 유닛은 `.harness-tmp/venv_05_unit6`를 새로 만들어 사용했다. 06단계도 별도 venv를 새로 만들거나 이 venv를 재사용할 수 있으나(재사용 시 `pip install -r backend/requirements.txt` + `pip install -r backend/requirements-dev.txt` 재확인 권장), **다른 병렬 유닛의 venv를 건드리지 말 것**.
- **음성모델 다운로드**: `backend/var/piper_voices/ko_KR-kss-medium.{onnx,onnx.json}`가 이미 이 유닛 작업 중 다운로드되어 로컬에 남아 있다(약 63MB, `.gitignore`로 커밋 제외). 06단계가 같은 머신에서 재현하면 이미 캐시된 파일을 그대로 재사용해 다운로드 없이 즉시 합성이 시작된다. 만약 이 캐시가 없는 새 환경이라면 최초 요청 시 자동으로 다운로드를 시도하며(네트워크 필요, DEC-007상 허용), 최대 120초까지 기다린다.
- **첫 호출 지연 없음(매 호출이 사실상 "첫 호출")**: §2 편차#3 때문에 이 TTS는 STT(`stt_engine.py`)와 달리 "최초 1회만 느리고 이후 빠른" 패턴이 아니라 **매 요청이 항상 서브프로세스 기동+모델 로드 비용(약 2~3초)을 포함**한다. 06단계가 "두 번째 요청부터 빨라진다"를 기대하면 안 된다 — 이는 결함이 아니라 §2 편차#3의 의도된 트레이드오프다.
- **엔드포인트 성격**: `POST /interviews/{id}/tts-preview`는 실제 인터뷰 대화 흐름(턴 제출/응답)과 무관한 **진단/검증 전용** 엔드포인트다. 세션 상태(`scheduled`/`live`/`completed` 등)와 무관하게 본인 소유 세션이기만 하면 호출 가능하다(턴 제출처럼 `live` 상태를 요구하지 않음 — 의도적 설계, §1 참고). `TRANSCRIPTS`에는 어떤 레코드도 남기지 않는다.
- **PostgreSQL**: 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용. 이번 유닛은 스키마 변경이 없어 신규 Alembic 리비전이 없다(`alembic current` → `d3f7a2c9e1b4 (head)`, 변경 없음).
- **병렬 작업 알림**: `git status` 기준 `backend/alembic/env.py`, `backend/app/services/job_queue.py`(unit-4/5가 만든 기존 변경분)는 이 유닛이 만든 변경이 아니다 — 이 유닛(unit-6)이 만든 변경은 위 §1에 열거한 파일/구간뿐이다(신규: `tts_engine.py`, `unit-6-note.md`; 수정: `interviews.py`의 `tts-preview` 엔드포인트 구간, `main.py`의 `/media` 마운트, `requirements.txt`, `.gitignore`).

## 4. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app alembic/env.py`(`.harness-tmp/venv_05_unit6`, `requirements-dev.txt`의 pinned `ruff==0.16.8` 사용 — 시스템 anaconda의 `ruff 0.12.0`이 PATH에 먼저 잡히는 것을 확인하고 프로젝트 지정 버전으로 재확인함) → **통과(에러 0건)**.
- 프론트엔드: 이번 유닛은 프런트 파일을 변경하지 않아 해당 없음.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2.5(Piper `ko_KR-kss-medium`, GPL-3.0-or-later 격리, 서브프로세스 연동), §4.5(어댑터 인터페이스), §5.4(TTS 타임아웃→`AI_SERVICE_TIMEOUT`) 그대로 구현. `tts-preview` 엔드포인트는 §4.2 표에 없는 신규 항목이며 §2에 편차와 사유를 명시했다.
- [x] 에러 처리 누락 경로 없음 — 텍스트 검증(1~500자, 422), 모델 다운로드 실패/타임아웃/서브프로세스 비정상종료/합성 타임아웃(모두 `TtsSynthesisError`→504), 인증 없음(401), 소유권 없음(403), 존재하지 않는 세션(404)까지 명시적으로 처리. `tts_engine.py`의 `finally` 블록은 임시 입출력 파일을 항상 정리하며(§4에서 `.tts_tmp` 디렉터리가 실행 후 비어있음을 실측 확인), 예외를 조용히 삼키는 `except: pass`류 코드는 없다.
- [x] 시스템 경계(사용자 입력) 검증 — `TtsPreviewRequest.text`는 Pydantic으로 1~500자 강제(실제 curl로 빈 문자열/필드 누락/501자 케이스 검증, §4). `interview_id`는 FastAPI가 UUID로 강제. 서브프로세스 호출은 `subprocess.run`에 리스트 인자를 전달해(`shell=True` 미사용) 커맨드 인젝션 경로가 없다.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — `piper-tts`는 `pip install piper-tts`로 실제 설치 성공(PyPI 실존, 버전 1.8.0, 저장소 `OHF-voice/piper1-gpl`, 라이선스 `GPL-3.0-or-later` — 03-design §2.5의 기존 실측 기록과 정확히 일치함을 재확인). 한국어 음성모델 `ko_KR-kss-medium`은 `python -m piper.download_voices`로 실제 다운로드 성공(63,221,984 bytes).
- [x] 범위 외 변경 없음 — `recruiter.py`, `ops.py`, `consents.py`, `whiteboard.py`, `code_submissions.py` 등 다른 유닛 파일은 건드리지 않았다(`git status`/`git diff --stat`으로 재확인). LLM(unit-7)/실제 턴 파이프라인 연결은 만들지 않았다 — `job_queue.py`도 건드리지 않았다(§3 명시).

## 6. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit6` 신규 생성(DEC-027) → `pip install -r backend/requirements.txt` + `pip install -r backend/requirements-dev.txt`(ruff 포함) 성공. `pip show piper-tts` → 버전 1.8.0, 라이선스 GPL-3.0-or-later 확인.
2. `python -m piper.download_voices ko_KR-kss-medium --download-dir backend/var/piper_voices` 실제 실행 → `ko_KR-kss-medium.onnx`(63,221,984 bytes) + `.onnx.json` 다운로드 성공(약 5초).
3. **TTS 단독 실증(서브프로세스 방식 그대로 CLI 재현)**: UTF-8 텍스트 파일(`안녕하세요, 자기소개 부탁드립니다.`)을 `-i`로 넘겨 `python -m piper` 실행 → WAV 생성 확인, `wave` 모듈로 열어 `channels=1, rate=22050Hz, duration≈3.03초`로 유효한 오디오임을 직접 검증. (참고: 최초 시도 시 bash `echo`로 stdin 파이프 전달을 시도했다가 Windows 콘솔 인코딩 문제로 `UnicodeEncodeError: surrogates not allowed`가 발생해 실패 사례를 실측으로 확인했고, 이 경험을 반영해 `tts_engine.py`는 항상 UTF-8 파일 경유 방식을 사용하도록 구현했다.)
4. 기존 `final-project-db`(Docker, 포트 5544) 재사용, 신규 마이그레이션 없음(`alembic current` → `d3f7a2c9e1b4 (head)`, 변경 없음).
5. `ruff check app alembic/env.py`(pinned 버전) 통과.
6. `uvicorn app.main:app --port 8062`로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인 → `POST /interviews`(세션 생성, `scheduled` 상태 그대로)
   - `POST /interviews/{id}/tts-preview`(한국어 문장, UTF-8 JSON 파일 경유로 인코딩 문제 우회) → `200 {"audio_url":"/media/tts/{uuid}.wav"}` 확인
   - `GET {audio_url}`(정적 파일 서빙) → `200`, `Content-Type: audio/wav`, 151,596 bytes 다운로드 성공
   - 다운로드한 WAV를 `wave` 모듈로 직접 열어 `channels=1, rate=22050Hz, duration≈3.44초`로 유효한 오디오임을 재확인(서버가 실제로 만든 파일이 손상 없이 그대로 전달됨을 증명)
   - 빈 문자열(422), 필드 누락(422), 501자(422) 확인
   - 토큰 없이 호출(401), 존재하지 않는 interview id(404), 다른 candidate 토큰으로 남의 세션 호출(403) 확인
   - 실제 AI 응답 길이에 가까운 162자 한국어 문장으로 재호출 → 총 소요 3.23초(서브프로세스 기동+모델 로드 포함)에 22.62초 분량 오디오 생성 확인(§5.4의 10초 타임아웃 예산 안에 충분히 들어옴, §2 편차#3에서 이 트레이드오프를 이미 문서화)
   - 서버 로그(`uvicorn_05_unit6.log`)에 기대하지 못한 스택트레이스/예외 없음을 grep으로 확인
   - `backend/var/media/.tts_tmp/`가 요청 처리 후 비어있음을 확인(임시 입력/출력 파일이 매번 정리됨)
7. 정리: uvicorn(8062) 프로세스 종료 확인(이후 curl 연결 거부). 테스트로 만든 candidate 계정 2개는 DB에서 직접 DELETE로 정리(연쇄로 해당 계정 소유 interview도 함께 삭제). 생성한 임시 파일(`.harness-tmp/u6_*.json`, `u6_*.wav`, `uvicorn_05_unit6.log`, `tts_out/`)은 전부 삭제. `backend/var/piper_voices/`(음성모델 캐시)와 `backend/var/media/tts/*.wav`(테스트 중 합성된 실제 산출물 2건)는 `.gitignore` 대상이라 커밋되지 않으며, 06단계의 재검증 편의를 위해(재다운로드 회피) 삭제하지 않고 남겨두었다 — 필요 시 06단계가 자유롭게 지워도 무방하다(재생성됨). `.harness-tmp/venv_05_unit6`도 다른 유닛들의 선례와 동일하게 재사용 가능하도록 보존했다. `git status` 재확인 결과 이 유닛이 만든 변경(§1)과 기존에 남아있던 다른 작업 단위의 미커밋 변경만 남고, 이 유닛이 만든 임시 산출물은 없음 — 규칙 K 준수.

## 7. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 본인 소유 인터뷰 세션(어떤 `status`든 무방)에 대해 로그인 사용자가 `POST /interviews/{id}/tts-preview`에 `{"text":"<1~500자 한국어 문장>"}`을 보내면 `200`과 함께 `{"audio_url":"/media/tts/{uuid}.wav"}` 형태의 응답이 온다.
2. 1에서 받은 `audio_url`을 그대로 `GET {audio_url}`로 호출하면(예: `GET /media/tts/{uuid}.wav`) `200`과 `Content-Type: audio/wav`가 반환되고, 응답 바디를 파일로 저장해 파이썬 `wave` 모듈(또는 임의의 오디오 재생 프로그램)로 열면 손상 없이 재생 가능한 유효한 WAV(모노, 22050Hz)로 확인된다.
3. `text` 필드가 빈 문자열이거나 필드 자체가 없으면 `422`가 반환되고, 501자 이상이면 `422`가 반환된다(500자는 통과).
4. 인증 토큰 없이 호출하면 `401`, 존재하지 않는 interview id면 `404`, 다른 candidate 계정 소유의 세션에 호출하면 `403 AUTH_FORBIDDEN`이 반환된다.
5. 동일한 텍스트로 두 번 연속 호출하면 매번 새로운(서로 다른) `audio_url`이 발급되고(파일명이 UUID 기반), 두 응답 모두 1/2와 동일하게 유효한 오디오로 확인된다(멱등하지 않은 것이 정상 — 매 호출이 새 합성 결과).
6. 이 엔드포인트가 만든 어떤 레코드도 `GET /interviews/{id}/transcripts`(unit-4)에 나타나지 않는다 — TTS 미리듣기는 실제 인터뷰 대화 이력에 영향을 주지 않는 별도 진단 경로임을 확인한다.
7. (참고, 결함 아님) 매 호출은 서브프로세스 기동+모델 로드 비용으로 인해 약 2~4초 내외 걸릴 수 있다(§3 참고) — 이는 STT처럼 "두 번째부터 빨라지는" 패턴이 아니다.
