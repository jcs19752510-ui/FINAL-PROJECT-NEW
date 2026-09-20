# unit-7 구현 노트 — Feature C. 대화형 인터뷰 엔진: LLM 적응형 꼬리질문 + RAG 질문은행 (REQ-007)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요. 단, 이 유닛이 다루는 LLM/RAG/큐 파이프라인은 Feature C의 핵심이라 09단계(보안검증)·규칙 J 안전장치(REQ-035~039)는 트랙과 무관하게 unit-8에서 예외 없이 별도 검증되어야 한다(DEC-003 원문).
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §2.4(LLM: Qwen2.5-1.5B-Instruct GGUF, DEC-025), §5.1(성능 재검증), §3(QUESTIONS/pgvector), §4.2/§4.3(턴 API, WS 이벤트 계약), §4.4(구조화 출력), §6.3(보안설계 — 이 유닛은 역할분리만 최소 반영, 전체 구현은 unit-8), `docs/harness/units/unit-4-note.md`/`unit-5-note.md`/`unit-6-note.md`(job_queue 스텁, WS 이벤트 계약, `tts_engine.synthesize_speech_file()`), `docs/harness/decisions.md` DEC-016/DEC-019/DEC-025/DEC-027/DEC-028, `docs/harness/traceability.md` REQ-007 행

## 1. 구현 범위

### LLM 실제 동작 (오케스트레이터 지시 1번 — 이 유닛의 존재 이유)

3단계(DEC-016)가 `llama-cpp-python` 설치를 시도했다가 (1) Windows `MAX_PATH`(260자) 제한으로 소스빌드 실패, (2) Python 3.13용 PyPI 프리빌드 휠 부재로 실패했던 것을 이번에도 **먼저 재현·재확인**했다(`pip install llama-cpp-python`이 동일한 두 오류를 그대로 재현함). 이번에는 그 자리에서 멈추지 않고 오케스트레이터 지시 (b)안 — **llama.cpp 공식 GitHub Release의 사전 컴파일된 실행파일(`llama-server.exe`)을 서브프로세스로 띄우고 OpenAI 호환 HTTP API로 통신**하는 방식으로 전환해 실제 동작시켰다.

- `llama.cpp` 릴리즈(`b11050`)에서 Windows용 두 빌드를 모두 내려받아 `backend/var/llm/`에 보관: `bin_vulkan/`(Vulkan GPU 백엔드, CUDA 툴킷 설치 없이 GPU 드라이버만으로 동작) + `bin_cpu/`(CPU 전용, 완전 폴백용).
- `Qwen/Qwen2.5-1.5B-Instruct-GGUF`의 `qwen2.5-1.5b-instruct-q4_k_m.gguf`(약 1.07GB, DEC-025가 확정한 Apache-2.0 라이선스 모델)를 HuggingFace에서 실제 다운로드해 `backend/var/llm/models/`에 저장.
- `backend/app/services/llm_engine.py`: `ILLMEngine` 원칙에 따라 `_ensure_server_running()`이 워커 프로세스 수명 동안 1회만 `llama-server`를 기동(Vulkan 우선 시도 → 실패 시 CPU로 자동 폴백)하고, `generate_turn_response()`가 `/v1/chat/completions`를 `response_format:{"type":"json_object"}`로 호출해 03-design §4.4 스키마(`TurnLLMOutput` pydantic 모델)로 강제 검증한다. 파싱 실패 시 최대 1회 재시도 후 `LlmGenerationError`로 승격해 호출부(worker/tasks.py)가 안전 기본값으로 폴백한다.
- **실측(재현 가능)**: `nvidia-smi`로 GPU 유휴 시 598MiB 사용 중이던 것이, `llama-server`(Vulkan, `-ngl 99`) 기동 후 1717MiB로 증가함을 확인해 **모델이 실제로 GPU에 상주함**을 실측으로 증명했다(`nvidia-smi --query-compute-apps`로 해당 PID가 `backend/var/llm/bin_vulkan/llama-server.exe`임도 확인). 실제 턴 처리 지연은 워밍업 후 약 4.5~7초(§6 로그), 03-design §5.1의 1.5B 추정치(텍스트 전용 2~5초 + TTS)와 정합한다.

### RAG 질문은행 (지시 2번)

- `backend/app/models/question.py`: 03-design §3.1 `QUESTIONS` ERD 그대로 + pgvector `Vector(384)` 임베딩 컬럼.
- **인프라 변경**: `backend/docker-compose.yml`의 DB 이미지를 `postgres:16` → `pgvector/pgvector:pg16`으로 교체(순정 이미지에는 `vector` 확장 파일 자체가 없어 `CREATE EXTENSION vector` 실패를 실측으로 확인) + Redis 서비스(Celery 브로커/WS 중계용, DEC-019) 신설. **기존 데이터 볼륨을 그대로 재사용**해 재기동했고, 재기동 후 기존 8개 테이블 데이터가 전부 그대로 남아있음을 확인했다(§6).
- Alembic `e4b6a1c9f2d7`: `CREATE EXTENSION IF NOT EXISTS vector`, `questions` 테이블 생성, `transcripts.question_id`에 FK 제약 추가(unit-4가 nullable 컬럼만 만들어둔 것을 실제로 연결).
- `backend/app/services/rag_engine.py`: 임베딩 모델 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`(다국어, 384차원, 약 470MB, CPU 실행 — GPU는 LLM 전용으로 유지)를 실제로 설치·로드해 `embed_text()`로 정규화된 벡터를 생성하고, `search_similar_questions()`가 pgvector 코사인 거리(`<=>`)로 pool을 뽑은 뒤 **MMR**(Maximal Marginal Relevance)로 다양성을 반영해 최종 top-k를 선택한다.
- `backend/app/services/seed_questions.py`: 특정 기업 기출문제를 수집하지 않고 이 유닛이 직접 작성한 자체 제작 질문 15건(technical 9, behavioral 5, opening 1)을 임베딩과 함께 시드하는 1회성 스크립트(마이그레이션과 분리, §3.3 원칙).

### LLM 오케스트레이션 (지시 3번)

- `backend/app/services/interview_prompts.py`: 면접관 페르소나(정답 직접 제시 금지, 꼬리질문 유도, 시스템 프롬프트 유출 거부 지침 포함)를 시스템 프롬프트 문자열로 구성하고, RAG 검색 결과(질문 후보)를 그 안에 "읽기 전용 참고자료"로 주입한다. **역할 분리(§6.3 최소 반영)**: 이 시스템 프롬프트 문자열과 지원자의 실제 답변(`user_message`)은 절대 하나의 문자열로 concat되지 않고, `llm_engine.py`가 `{"role":"system",...}`/`{"role":"user",...}`로 분리된 채 llama-server(Qwen2.5 ChatML 템플릿)에 전달한다.
- LLM 출력은 `TurnLLMOutput` pydantic 스키마(§4.4 그대로: `speak_text`, `control` Literal enum, `technical_accuracy`, `communication_clarity`, `key_observations`, `rubric_match`)로 강제 파싱된다 — 스키마를 벗어나는 출력은 pydantic이 자동으로 거부해 재시도/폴백 경로로 넘어간다.

### 파이프라인 연결 (지시 4번)

- `backend/app/services/celery_app.py`: Redis 브로커/백엔드로 Celery 앱 구성. **기동 명령은 반드시 `celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline`**(DEC-019 그대로 — GPU/CUDA류 컨텍스트가 fork와 호환되지 않는 문제를 이 프로젝트는 Vulkan으로 우회하지만, 워커가 여러 개면 `llama-server` 포트/VRAM이 충돌하므로 동일 원칙 적용).
- `backend/app/worker/tasks.py`: `process_opening_question_job`/`process_turn_job` — RAG 검색 → LLM 꼬리질문 생성(실패 시 §4.4/§5.4 안전 기본값 폴백) → TTS 합성(`tts_engine.synthesize_speech_file()`, unit-6 재사용, 실패해도 텍스트는 전달하는 그레이스풀 디그레이드) → `TRANSCRIPTS(speaker=ai)` 저장 → WS `stage_update`/`turn_result` push까지 전부 실제로 수행.
- `backend/app/services/job_queue.py`: `enqueue_opening_question_job`/`enqueue_turn_job`을 uuid4 스텁에서 **실제 Celery `send_task()`**로 전환(반환값이 실제 Celery task id).
- `backend/app/services/ws_publisher.py` + `backend/app/api/v1/ws.py`(`redis_relay_loop`) + `backend/app/main.py`(startup/shutdown 이벤트): AI Worker(Celery, API 서버와 완전히 별도의 OS 프로세스, §1.2)가 `ConnectionManager`를 직접 호출할 수 없으므로, Redis Pub/Sub(`ws:{interview_id}` 채널)로 이벤트를 발행하고 API 프로세스가 구독해 실제 WebSocket으로 중계한다.

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `llama-cpp-python` 대신 llama.cpp 공식 사전컴파일 `llama-server.exe`를 서브프로세스+HTTP API로 연동 | §5.1이 이미 "확인 필요"로 남겨둔 실측 게이트를 이행하는 과정에서, 3단계와 동일한 Windows 긴경로/휠 부재 실패를 재확인했다. 오케스트레이터 지시가 제시한 대안 (b)(순수 실행파일 기반 서버+HTTP API)를 채택 — Python 패키지 빌드 자체가 필요 없어 문제를 원천 회피한다. 어댑터 인터페이스(§4.5) 뒤에 감춰져 있어 향후 `llama-cpp-python`이 실제로 설치 가능해지면(WSL2 전환 등) 이 모듈만 교체하면 된다 | 중간(다른 추론 엔진으로 교체 시 이 모듈만 다시 작성하면 되나, 서브프로세스/HTTP 통신 방식 자체를 바꾸는 것이므로) |
| 2 | Vulkan GPU 빌드 실패 시 CPU 빌드로 자동 폴백하는 코드 경로는 작성했으나, 이 개발 환경(Vulkan 정상 동작)에서는 실제로 CPU 폴백이 트리거된 적이 없어 **end-to-end로 검증되지 못함** | Vulkan이 이 머신에서 안정적으로 동작해(§6 실측) 폴백 조건을 인위적으로 만들 별도 방법(드라이버 언인스톨 등)은 범위를 벗어난 파괴적 조치라 시도하지 않았다. 코드 경로 자체는 `_launch()`가 실패 시 `None`을 반환하고 `_ensure_server_running()`이 그 경우 CPU 빌드로 재시도하는 단순한 조건문이라 로직 검토로 신뢰도를 확보했다 | 낮음(조건문 단위) — 06/07단계가 `bin_vulkan/llama-server.exe`를 임시로 다른 이름으로 바꿔 폴백을 강제 재현하는 것을 권장(§3) |
| 3 | TTS 합성 실패가 전체 job을 실패시키지 않고 `audio_url=null`로 텍스트만 전달(§5.4 "TTS 단계 타임아웃→AI_SERVICE_TIMEOUT" 원문보다 완화) | 텍스트 응답(`speak_text`)은 이미 LLM 단계에서 확보되어 있는데, 음성 합성만 실패했다고 사용자가 AI 응답 자체를 못 받게 하는 것은 과도한 실패 전파라고 판단했다. `_synthesize_or_none()`이 `TtsSynthesisError`를 잡아 로그만 남기고 `None`을 반환하며, `turn_result.audio_url`이 `null`이어도 프런트(unit-5/6이 이미 구현한 `audio_url ?? null` 처리)가 텍스트만 표시하도록 그레이스풀 디그레이드된다 | 낮음(예외 처리 분기 하나 — §5.4 원문대로 되돌리려면 `_synthesize_or_none`을 제거하고 예외를 그대로 전파시키면 됨) |
| 4 | 큐 최대 길이(50, §1.3)/`429 QUEUE_FULL`, WS `queue_status`(대기열 위치/ETA) push를 구현하지 않음 | `job_queue.py` 모듈 docstring이 원래부터 이를 "이후 유닛이 구현해야 할 것"으로 명시해뒀고, REQ-038(레이트리밋, 큐 자원보호)이 명시적으로 unit-8 범위라 이번 유닛이 임의로 선점 구현하지 않았다(범위 외 확장 금지) | 낮음(job_queue.py에 큐 길이 체크 함수 하나 추가하는 수준) |
| 5 | STT(unit-5)를 API 요청 핸들러에서 이 Celery 태스크로 이관하는 리팩터링을 하지 않음 | 오케스트레이터 지시 4번은 "job_queue.enqueue_turn_job()이 실제로 워커에서 처리되어 ... LLM 응답 생성 → TTS 합성까지 이어지는 파이프라인을 연결하라"였고 STT 이관은 명시하지 않았다. unit-5-note.md도 "AI Worker가 실제로 생기면 그때 옮기면 된다"는 전제였으나, 이 유닛 범위를 "사용자 턴이 이미 저장된 시점부터"로 좁게 잡아 곁다리 리팩터링을 피했다(범위 외 변경 금지 원칙) | 낮음(STT 호출부를 `_submit_voice_turn`에서 새 Celery 태스크로 옮기고 job_queue가 넘기는 인자를 오디오 바이트로 바꾸면 됨 — 후속 유닛 인수인계 사항) |
| 6 | opening_question job도 (오프닝 질문을 그대로 말하지 않고) LLM을 거쳐 자연스러운 발화로 재구성하도록 구현 — 그 결과 1.5B 모델이 가끔 오프닝 질문을 무시하고 엉뚱한 자기소개를 지어내는 품질 문제가 실측으로 관찰됨(§6 결과 예시) | 03-design §4.3 DEC-024 갭8이 "AI Worker가 STT 단계 없이 LLM→TTS만 수행"이라고 명시해 오프닝도 LLM 단계를 거치는 것이 설계 문언과 일치한다고 판단했다. 다만 1.5B 모델의 답변 품질 한계(§2.4가 이미 "3B 대비 응답속도는 빠르나 답변 품질은 다소 낮을 수 있음"이라고 경고)가 그대로 드러났다 — 이는 버그가 아니라 DEC-025가 이미 예상한 트레이드오프이며, `opening_question` job 자체가 실패(LLM 호출 예외)하면 §5.4가 정의한 고정 폴백 문구("간단히 자기소개 부탁드립니다")로 대체되는 것도 정상 동작한다 | 낮음(오프닝만 LLM 생략하고 질문 원문을 그대로 speak_text로 쓰도록 바꾸는 것은 조건문 하나로 가능 — 07단계가 품질 문제로 판단하면 이 방향으로 단순화 검토 권장) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **격리 venv 필수(DEC-027)**: 이 유닛은 `.harness-tmp/venv_05_unit7`을 새로 만들어 사용했다. 06단계도 별도 venv를 새로 만들거나 이 venv를 재사용할 수 있으나(재사용 시 `pip install -r backend/requirements.txt` + `requirements-dev.txt` 재확인 권장), **다른 병렬 유닛의 venv를 건드리지 말 것**.
- **프로세스 3종 필요**: 이 기능을 검증하려면 (1) `docker compose up -d`(DB `final-project-db` 포트 5544 + Redis `final-project-redis` 포트 6389), (2) `celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline`, (3) `uvicorn app.main:app` 세 가지가 모두 떠 있어야 한다. Celery 워커가 없으면 `POST /turns`는 202를 반환하지만 WS로 `stage_update`/`turn_result`가 영원히 오지 않는다(job이 Redis 큐에 쌓인 채 대기).
- **첫 요청 콜드스타트(약 13초)**: `llama-server` 서브프로세스 기동(Vulkan 드라이버 초기화+모델 로드, 약 3~4초)과 임베딩 모델 최초 로드(약 4초)가 겹치는 워커 프로세스의 **첫 job**은 총 13초 내외 걸린다(실측). 두 번째 job부터는 4.5~7초로 줄어든다. **프런트(unit-4)의 `AI_WAIT_TIMEOUT_MS`(12초, 클라이언트 구현 세부값)가 이 첫 요청 콜드스타트보다 짧아** 첫 오프닝 질문에서 "AI 응답 엔진은 아직 준비 중입니다" 안내가 뜬 뒤 뒤늦게 실제 응답이 도착하는 것처럼 보일 수 있다 — 결함이 아니라 워커 상시 기동(§5.3 "모델 로드는 1회성, 워커 상시 기동으로 상쇄 가능")을 전제한 설계와 개발 환경(요청마다 워커를 새로 띄움)의 차이다. 운영에서는 워커를 미리 워밍업(더미 요청 1회)해두는 것을 권장(이 유닛 범위 밖 운영 절차, 인수인계).
- **DB 이미지 교체 필요**: `backend/docker-compose.yml`의 `db` 서비스 이미지가 `postgres:16`에서 `pgvector/pgvector:pg16`으로 바뀌었다. 06단계가 기존에 `postgres:16`으로 띄워둔 컨테이너가 있다면 `docker compose up -d`로 재기동해야 하며(같은 볼륨을 재사용하므로 데이터 유실 없음, §6에서 실측 확인), Redis 서비스도 함께 새로 생긴다.
- **모델/음성 파일 캐시**: `backend/var/llm/`(llama-server 바이너리 2종 + Qwen GGUF 약 1.07GB)와 `backend/var/piper_voices/`(unit-6 산출물)가 이미 로컬에 있다(`.gitignore`로 커밋 제외). 새 환경에서 재현하려면 이 유닛 note의 §1(다운로드 URL 절차)을 참고해 동일 파일을 받아야 한다 — 자동 다운로드 스크립트는 만들지 않았다(범위 외, 인수인계 필요).
- **질문은행 시드 필요**: `python -m app.services.seed_questions`를 최초 1회 실행해야 RAG 검색이 결과를 반환한다(실행하지 않으면 `search_similar_questions()`가 빈 리스트를 반환하고, LLM은 "참고 질문 후보 없음" 상태로 생성 — 폴백 아님, 정상 동작이나 응답 품질이 낮아질 수 있음).
- **LLM 응답의 비결정성**: 1.5B 모델은 매 요청마다 문구가 달라진다(temperature=0.6). 06단계가 "정확히 이 문장이 나와야 한다"는 식의 검증을 하면 안 되고, "한국어로 된 비어있지 않은 질문형 문장이며 답변 주제와 관련이 있는가"를 기준으로 판단해야 한다(§6 실측 예시 참고).
- **CPU 폴백 경로 미검증**: §2 편차#2 참고 — 06/07단계가 `backend/var/llm/bin_vulkan/llama-server.exe`를 임시로 이름 변경(`llama-server.exe.bak`)해 Vulkan 기동을 인위적으로 실패시키면 CPU 폴백이 실제로 트리거되는지 확인할 수 있다(끝나면 반드시 원래 이름으로 복구할 것).

## 4. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app alembic/env.py`(`.harness-tmp/venv_05_unit7`, 프로젝트 지정 `ruff` 사용) → **통과(에러 0건)**. `alembic/versions/`는 프로젝트 `pyproject.toml`이 이미 `exclude`로 지정해뒀다(기존 마이그레이션 파일들과 동일 취급, unit-1 선례 그대로 — 명시적으로 개별 지정하지 않는 한 검사 대상 아님).
- 프론트엔드: 이번 유닛은 프런트 파일을 변경하지 않았다(REQ-007이 요구하는 것은 백엔드 AI 파이프라인이며, WS 이벤트 스키마가 unit-4/5가 이미 만들어둔 `frontend/app/interviews/[id]/page.tsx`의 타입과 정확히 일치함을 코드 대조로 확인 — `control?: { action: ... }` 등 필드명이 그대로 일치, §5 참고) — 해당 없음.

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 모든 편차와 사유 기록. 나머지(§2.4 LLM 선정/DEC-025, §3 QUESTIONS/pgvector, §4.3 WS 이벤트 스키마, §4.4 구조화 출력 계약, §4.5 어댑터 인터페이스, DEC-019 `--pool=solo`)는 설계서 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — LLM 서버 기동 실패(GPU→CPU 폴백, 둘 다 실패 시 `LlmGenerationError`), HTTP 호출 실패/타임아웃, 구조화 출력 파싱 실패(재시도 1회 후 안전 기본값), TTS 실패(그레이스풀 디그레이드, §2 편차#3), 세션/턴 상태 불일치(job 스킵+로그), 워커 태스크 최상위 `except Exception`(§4.3 `error` 이벤트로 알림, 조용히 삼키지 않고 `logger.exception`으로 스택트레이스 보존)까지 명시적으로 처리.
- [x] 시스템 경계(사용자 입력) 검증 — 지원자의 실제 답변은 `TurnCreate`(unit-4, 1~4000자)로 이미 검증된 뒤 이 파이프라인에 들어온다. LLM에게 전달하는 시스템 프롬프트와 사용자 입력은 role로 분리되어(§6.3 최소 반영) 문자열 수준에서 시스템 지시를 덮어쓸 수 없다. LLM 출력 자체는 `TurnLLMOutput` pydantic 스키마로 강제 검증되어(화이트리스트 `control` enum 포함) 스키마 밖 값은 통과할 수 없다.
- [x] 하드코딩된 시크릿/자격증명 없음 — Redis URL은 `.env`(`REDIS_URL`, gitignore 대상)로 관리, 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — `celery[redis]`(5.4.0), `redis`(5.3.1), `pgvector`(0.3.6), `sentence-transformers`(3.4.1) 전부 `pip install` 실제 성공 확인(§6). llama.cpp는 PyPI 패키지가 아니라 GitHub Release 바이너리이므로 `pip`로 설치하지 않으며, 다운로드 URL(`github.com/ggml-org/llama.cpp/releases`, `huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF`)이 실제로 응답하고 파일이 정상 실행됨을 실측으로 확인했다(그럴듯하지만 존재하지 않는 패키지/URL을 지어내지 않았음).
- [x] 범위 외 변경 없음 — 프런트엔드 파일, 코드에디터/웹캠/화이트보드/동의/삭제요청/대시보드/운영자화면은 건드리지 않았다. 리포트 생성(`enqueue_report_generation_job`, unit-10 범위)은 스텁 그대로 유지했다. STT 이관(§2 편차#5), 큐 길이 제한(§2 편차#4)도 의도적으로 손대지 않았다.

## 6. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit7` 신규 생성(DEC-027) → `pip install -r backend/requirements.txt`(`celery[redis]`/`redis`/`pgvector`/`sentence-transformers` 포함) 성공.
2. **LLM 실제 동작 검증**: `github.com/ggml-org/llama.cpp` 릴리즈 `b11050`에서 `llama-b11050-bin-win-vulkan-x64.zip`/`llama-b11050-bin-win-cpu-x64.zip` 다운로드·압축해제, `Qwen/Qwen2.5-1.5B-Instruct-GGUF`의 `qwen2.5-1.5b-instruct-q4_k_m.gguf`(1,117,320,736 bytes) 다운로드. `llama-server.exe -m ... -ngl 99`로 단독 기동 후 `nvidia-smi` VRAM 598MiB→1717MiB 증가 확인(GPU 실제 상주). `/v1/chat/completions`에 `response_format:{"type":"json_object"}`로 "MSA/Saga 트랜잭션 경험" 답변을 보내 `{"speak_text":"MSA 환경에서 데이터 정합성을 어떻게 보장했나요?","control":"next_question",...}` 유효 JSON 응답을 2.6초에 수신 확인.
3. **RAG 실제 동작 검증**: `paraphrase-multilingual-MiniLM-L12-v2` 로드(최초 18.5초) 후 "MSA 환경에서 트랜잭션 관리 경험" vs "분산 트랜잭션 데이터 정합성 질문"(코사인 유사도 0.53) vs "오늘 날씨가 좋네요"(0.17) — 무관 문장과 명확히 구분됨을 실측 확인. `docker exec final-project-db psql -c "CREATE EXTENSION vector"` 최초 실패(순정 `postgres:16` 이미지에 확장 없음) → `docker-compose.yml`을 `pgvector/pgvector:pg16`으로 교체 후 재기동 → 기존 8개 테이블 데이터 그대로 유지 확인 + `CREATE EXTENSION vector` 성공 + collation 버전 경고를 `ALTER DATABASE ... REFRESH COLLATION VERSION`으로 해소.
4. `alembic upgrade head`(`e4b6a1c9f2d7`) 적용 → `questions` 테이블 + `fk_transcripts_question_id` 생성 확인(`\d questions`). `python -m app.services.seed_questions` 실행 → 신규 15건 삽입 확인(`SELECT category, count(*) FROM questions GROUP BY category` → technical 9/behavioral 5/opening 1). `search_similar_questions()` 직접 호출로 "MSA/Saga" 질의에 대해 관련 질문 3건이 관련도 순으로 반환됨을 확인.
5. `ruff check app alembic/env.py` 통과.
6. **전체 파이프라인 end-to-end 검증**(3개 프로세스 모두 기동 — DB+Redis 컨테이너, `celery ... --pool=solo -Q ai_pipeline`, `uvicorn app.main:app --port 8071`): Python(`requests`+`websockets`) 스크립트로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인 → `POST /interviews` → `ai_interview_notice` 동의 → WS 연결 → `POST /interviews/{id}/start`(202) → WS로 `stage_update(llm)` → `stage_update(tts)` → `turn_result` 수신(오프닝 질문 음성 포함, `audio_url` 실제 WAV 파일 — `wave` 모듈로 모노/22050Hz/5.28초 유효성 확인).
   - 텍스트 턴 제출("MSA 환경에서 여러 서비스 간 트랜잭션을 관리한 경험... Saga 패턴") → WS로 `stage_update(llm)` → `stage_update(tts)` → `turn_result` 수신: `ai_text="MSA 환경에서 MSA(마이크로서비스 아키텍처)로 전환하며 겪은 가장 큰 기술적 어려움은 무엇을 경험했나요?"`(RAG 검색 결과 질문과 연계된 꼬리질문, `question_id`가 실제 매칭된 질문은행 항목을 가리킴), `control.action="next_question"`.
   - 두 번째 텍스트 턴("Kubernetes 기반 무중단 배포/롤백 전략") 제출 → `ai_text="무중단 배포와 롤백 전략을 Kubernetes 기반으로 어떻게 적용했나요?"` 수신 — **3턴 연속으로 문맥이 이어지는 적응형 대화**를 실측 확인(`GET /transcripts`로 `turn_index` 0~4, `speaker`/`content_text`/`question_id` 전부 정합성 확인).
   - Celery 로그로 실측 처리 시간 확인: 첫 opening job(콜드스타트, llama-server+임베딩모델 최초 로드 포함) 13.55초 → 두 번째 opening job(워밍업 후) 7.14초 → turn job(워밍업 후) 4.47초.
   - `nvidia-smi --query-compute-apps`로 GPU 점유 프로세스가 실제로 `backend/var/llm/bin_vulkan/llama-server.exe`임을 재확인.
7. 정리: Celery 워커/uvicorn/llama-server 프로세스를 **각각 실제로 기동한 PID만 지정해**(`Stop-Process -Id <PID>`) 종료(DEC-028 — 이미지 이름 기준 광범위 종료 금지 준수), 종료 후 `nvidia-smi` VRAM이 576MiB로 원복됨을 확인. 테스트로 만든 candidate 계정 3개와 연쇄 데이터(interviews/transcripts/consents)는 DB에서 직접 DELETE로 정리. 생성한 임시 파일(`.harness-tmp/u7_*.py`, `u7_*.json`, `u7_*.txt`, `u7_*.wav`, `celery_unit7.log`, `uvicorn_unit7.log`, 다운로드한 릴리즈 zip 2개, 시험용 llama_cpu/llama_vulkan 폴더)은 전부 삭제. `.harness-tmp/venv_05_unit7`은 다른 유닛 선례와 동일하게 재사용 가능하도록 보존. `backend/var/llm/`(바이너리+모델), `backend/var/piper_voices/`, `backend/var/media/`는 `.gitignore` 대상이라 커밋되지 않으며, 06단계의 재현 편의를 위해(재다운로드 회피) 삭제하지 않고 남겨두었다. `git status` 재확인 결과 이 유닛이 만든 변경(§1)만 남고 임시 산출물은 없음 — 규칙 K 준수.

## 7. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

**사전 조건(06단계 필수 확인)**: `docker compose up -d`(DB+Redis), `celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline` 기동, `python -m app.services.seed_questions` 최초 1회 실행, `uvicorn app.main:app` 기동 — 4가지가 모두 되어 있어야 아래 조건을 검증할 수 있다.

1. `live` 상태 세션에서 `POST /interviews/{id}/start` 성공 후 WebSocket(`/ws/interviews/{id}`)에 연결해 두면, 약 5~15초 내(콜드스타트 여부에 따라, §3 참고) `stage_update`(`stage:"llm"` → `stage:"tts"`) 이벤트에 이어 `turn_result` 이벤트가 도착한다. `turn_result.ai_text`는 비어있지 않은 한국어 문장이고, `audio_url`이 `null`이 아니면 그 URL을 `GET`해 유효한 WAV 파일(모노, 22050Hz)을 받을 수 있다.
2. 1 이후 `POST /interviews/{id}/turns`에 기술 관련 텍스트 답변(예: "MSA 환경에서 트랜잭션을 Saga 패턴으로 관리했습니다")을 제출하면 `202 {job_id}`가 즉시 반환되고, 같은 WebSocket으로 동일한 `job_id`의 `stage_update(llm)` → `stage_update(tts)` → `turn_result`가 도착한다. `turn_result.ai_text`는 답변 주제(MSA/트랜잭션 등)와 **의미적으로 관련된 질문형 한국어 문장**이어야 한다(정확한 워딩 일치는 요구하지 않음 — 매번 달라지는 것이 정상, §3 참고). `turn_result.control.action`은 `next_question`/`end_interview`/`switch_to_coding`/`none` 중 하나다.
3. 2 직후 `GET /interviews/{id}/transcripts`를 조회하면 `speaker=ai`인 새 레코드가 추가되어 있고, 그 `question_id`가 null이 아니면 실제 `questions` 테이블에 존재하는 UUID다(RAG 매칭 결과가 실제로 저장됨).
4. 서로 다른 주제의 텍스트 답변을 2회 연속 제출하면(예: "MSA 트랜잭션" 다음 "Kubernetes 무중단배포"), 두 번째 `turn_result.ai_text`가 첫 번째 답변이 아니라 **두 번째(가장 최근) 답변 주제**를 따라가는 꼬리질문이어야 한다(대화 맥락이 최신 답변에 반응함을 확인).
5. Celery 워커 프로세스를 죽인 상태에서 `POST /turns`를 호출하면 여전히 `202 {job_id}`가 반환되지만(사용자 텍스트는 `TRANSCRIPTS`에 저장됨), WebSocket으로 `stage_update`/`turn_result`가 오지 않는다(job이 Redis에 쌓인 채 대기) — 이는 정상 동작이며, 워커를 다시 기동하면(Celery는 큐에 남은 job을 순서대로 소비하므로) 뒤늦게 이벤트가 도착한다.
6. (참고, 결함 아님) LLM 응답 내용은 온도(temperature)가 0이 아니라 매 호출마다 문구가 달라진다. "정답 문자열 일치"가 아니라 "한국어/질문형/주제 관련성"으로 판단할 것 — §3, §6 실측 예시 참고.

## 재작업(Rework) v2 (2026-09-20, DEC-035 응답 반영)

> **append-only 원칙**: 위 §1~7(최초 05 구현 기록)은 그대로 보존한다. 아래 내용이 실제 최신 동작이며, §2 편차#6(오프닝도 LLM을 거침)은 이 재작업으로 **대체**됐다(오프닝은 더 이상 LLM을 거치지 않음) — 원문은 감사 이력으로만 남긴다.

### R0. 트랙 표기 및 근거
이번 재작업이 속한 feature(Feature C, REQ-007)의 05 최초 구현은 **L1**(DEC-003)이었으나, 이번 재작업 지시에는 명시적인 트랙 지정이 없었다. ORCHESTRATOR.md 1장("트랙 표기 없으면 L3 기본값")에 따라 **L3(일반)**로 표기한다. 근거: (1) 이번 재작업은 보안(Redis 인증/노출), DB 스키마(유니크 제약), 다수 결함(DEF-001~011)에 대한 정정이라 L1/L2의 "경량 검증"보다 정식 검증이 적합하고, (2) 실제로 06(unit-7-test.md)이 이미 "사용자 요구로 전 섹션·규칙 B 2회 이상 정식 수행"했던 선례가 있어 재검증도 동일 수준으로 이어가는 것이 일관적이다. **06단계는 이 재작업에 대해 `test-report-template.md` 10섹션 전체를 정식으로 수행해야 한다** (L1 경량판 적용 금지).

### R1. 재작업 배경
`docs/harness/units/unit-7-test.md`(06, CONDITIONAL PASS) §6 결함표 DEF-001~011, §8 리스크/미해결질문 Q1~Q5, `docs/harness/decisions.md` DEC-034(결정 대기)·**DEC-035(오늘 사용자 확정 답)**을 전부 반영했다. DEC-035 확정 사항(Q1~Q5)과 DEF-004/006/007/009/010(정책 판단 불필요한 순수 구현 결함)까지 포함해 **DEF-001~011 전부**를 대상으로 재작업했다.

### R2. 변경/생성 파일 전체 목록
- **생성**:
  - `backend/alembic/versions/f2a9c4d81e36_v9_transcripts_unique_turn_index.py` — `(interview_id, turn_index)` 유니크 제약(DEF-002).
  - `backend/app/services/turn_numbering.py` — 원자적 채번 공용 모듈(DEF-002).
  - `backend/app/services/job_watchdog.py` — 처리 중 워커 크래시 실패 통지(DEF-008).
- **수정**:
  - `backend/app/worker/tasks.py` — DEF-001(오프닝 LLM 생략)·002(채번 통일)·003/004(품질 가드+재시도+폴백)·005(잘라내기)·007(RAG exclude+threshold) 전부 반영.
  - `backend/app/services/interview_prompts.py` — `validate_followup_speak_text()` 신설(DEF-003/004), 더 이상 쓰이지 않는 `build_opening_system_prompt`/`_OPENING_INSTRUCTION` 제거(DEF-001의 직접적 결과).
  - `backend/app/services/rag_engine.py` — `search_similar_questions()`에 `exclude_categories`/`min_similarity` 파라미터 추가(DEF-007).
  - `backend/app/services/llm_engine.py` — `TurnLLMOutput.speak_text` 공백 검증(DEF-006), `_ensure_server_running()` 이중 기동 방지 + PID 파일 기록(DEF-009).
  - `backend/app/services/celery_app.py` — 전 모델 명시적 import로 워커 메타데이터 완결성 확보(DEF-010).
  - `backend/app/services/job_queue.py` — enqueue 직후 `job_watchdog.register_job()` 호출(DEF-008).
  - `backend/app/main.py` — `job_watchdog_loop()` 백그라운드 태스크 기동/취소 추가.
  - `backend/app/api/v1/interviews.py` — `_next_turn_index`(count 기반) 제거, `insert_transcript_with_retry()`로 교체(DEF-002).
  - `backend/app/api/v1/ws.py` — `redis_relay_loop()`에 서버→클라이언트 이벤트 dict/type 화이트리스트 검증 추가(DEF-011).
  - `backend/docker-compose.yml` — Redis `127.0.0.1` 바인딩 + `--requirepass`(DEF-011).
  - `backend/app/core/config.py`, `backend/.env`(gitignore 대상, git status에는 안 보임), `backend/.env.example` — `REDIS_URL`에 인증정보 반영(DEF-011).

### R3. DEF별 대응 상세

**DEF-001(오프닝 품질, High) — DEC-035 Q1(a) 채택.** `process_opening_question_job`이 더 이상 LLM을 호출하지 않는다. RAG로 선정한 `category=opening` 질문은행 항목의 `content`를 그대로 `speak_text`로 사용하고(TTS만 거침), 항목이 없으면 고정 폴백(`_OPENING_FALLBACK_TEXT`)을 쓴다. 이로써 지원자 사칭 자기소개·미치환 플레이스홀더·비한국어 조각이 원천적으로 발생할 수 없다(LLM을 거치지 않으므로). 스모크 테스트로 실제 확인(R6 참고).

**DEF-002(turn_index 중복, Medium) — DEC-035 Q5 채택.** Alembic `f2a9c4d81e36`으로 `(interview_id, turn_index)` 유니크 제약을 추가했고, `app/services/turn_numbering.py::insert_transcript_with_retry()`로 오프닝/사용자 턴 채번을 통일했다(`MAX(turn_index)+1` 계산 → 유니크 제약 위반 시 재계산 후 재시도, 최대 5회). API 프로세스(사용자 턴)와 워커 프로세스(AI 턴)가 서로 다른 트랜잭션이라 "완전한 분산 락"은 택하지 않았고, DB 제약을 최종 방어선으로 둔 "낙관적 재시도" 패턴을 택했다(근거는 `turn_numbering.py` 모듈 docstring). 로컬 테스트로 유니크 제약이 실제로 중복 INSERT를 거부하고, 재시도 로직이 충돌 후에도 정상 배정하는 것을 확인(R6).

**DEF-003/004(후속 질문 품질/페르소나 낭독, Medium) — DEC-035 Q1(a) 채택, 가드 재사용.** `interview_prompts.validate_followup_speak_text()`가 4가지 조건(질문형 여부·플레이스홀더 없음·한국어 비율·시스템 프롬프트 문구 미포함)을 검사한다. `tasks.py::_generate_validated_followup()`이 1차 생성 → 검증 실패 시 1회 재시도 → 그래도 실패하면 질문은행 원문(또는 고정 폴백)으로 대체한다.
  - **질문형 판정**: 정규식 `[?？]|나요|까요|주세요|말씀해|설명해|알려`(unit-7-test.md TC-005/TC-045 표본 기반). 완벽한 자연어 이해는 과설계이므로 휴리스틱을 택했다.
  - **한국어 비율 합격선 0.5**: 기술 면접 답변에는 영어 약어(MSA, Kubernetes 등)가 정상적으로 섞이므로 100%를 요구하지 않는다. TC-046에서 관측된 "전체가 영어인 응답"은 걸러내고 기술 용어 혼용은 통과시키는 절충값이다.
  - **"질문형 비율 합격선"(DEC-035 지시, 예시 90%)**: 이 가드+재시도+질문은행 폴백 구조상, 최종적으로 클라이언트에 전달되는 `speak_text`는 이론상 100%가 질문형이어야 한다(질문은행 폴백 문항은 전부 질문형이므로). 다만 정규식 휴리스틱이 놓칠 수 있는 극단적 표현(예: 드물게 관측되지 않은 변형 종결어미)까지 완벽히 잡아낸다고 보장할 수 없으므로, **06 재검증 시 다표본(예: 20건 이상) 질문형 비율이 90% 이상이면 이 가드가 의도대로 동작한다고 판단할 것을 권고**한다(100% 미달 시에도 즉시 결함으로 보지 말고, 실제로 걸러지지 않은 표본의 문장 자체를 검토해 정규식 보강 여부를 판단).
  - **페르소나 유출 마커**: `_BASE_PERSONA` 대표 문구 4개를 하드코딩 리스트로 검사(완전한 유출 방지는 REQ-039/unit-8 범위, 이 가드는 "가장 흔한 관측 패턴"만 잡는 1차 방어선).

**DEF-005(긴 답변 컨텍스트 초과, Medium) — DEC-035 Q4 채택(서버측 잘라내기).** `tasks.py`가 LLM에 보내기 전 최신 답변을 1,500자, 이력 각 줄을 300자로 잘라낸다(`_truncate_for_llm`). 경계값은 unit-7-test.md TC-028 실측(1,500자 성공/2,500자 HTTP 400 실패)에서 여유를 둔 값이다. **DB에는 원본 전문이 그대로 저장된다** — 이 잘라내기는 LLM에 보내는 프롬프트 구성 단계에만 적용되며 데이터 손실이 아니다.

**DEF-006(공백 speak_text, Low) — 즉시 수정.** `TurnLLMOutput.speak_text`에 `field_validator`를 추가해 `strip()` 후 빈 문자열이면 `ValueError`(pydantic `ValidationError`)를 던지도록 했다. 이미 존재하던 "스키마 위반 → 재시도 → 폴백" 경로에 자연스럽게 편입된다(별도 분기 불필요).

**DEF-007(RAG 무관 후보, Low) — 즉시 수정.** `search_similar_questions()`에 `exclude_categories`/`min_similarity` 파라미터를 추가했고, `tasks.py`의 후속 검색 호출에 `exclude_categories={QuestionCategory.opening}`, `min_similarity=0.30`을 전달한다. **임계치 0.30의 근거**: unit-7-test.md TC-035 실측값(무관 질의 최고 유사도 0.17~0.18, 관련 질의 약 0.53) 사이의 보수적인 중간값으로, 명백히 무관한 질문은 걸러내되 실제 관련 질문의 재현율을 과도하게 낮추지 않는 절충값이다. 미달 시 후보 리스트가 비어 `question_id=NULL`(무관한 매칭을 DB에 남기지 않음)이 된다.

**DEF-008(워커 크래시 job 유실, Medium) — DEC-035 Q3 채택(단순 실패 통지, acks_late+멱등 재처리 기각).** 신설 모듈 `app/services/job_watchdog.py`: `job_queue.py`가 enqueue 직후 Redis에 `job_watch:{job_id}` 감시 키를 남기고, `main.py` startup에서 기동하는 `job_watchdog_loop()`가 5초 주기로 Celery task 상태를 확인한다. STARTED 상태가 **150초**(콜드스타트 최대 60s + LLM 재시도 2회×25s + TTS 10s ≈ 120s의 최악 시나리오에 여유를 둔 값) 넘게 지속되면 WS `error`(`code=AI_SERVICE_TIMEOUT`) 이벤트를 대신 발행한다. PENDING(워커 다운으로 대기 중, AC5 정상 시나리오)에는 타임아웃을 적용하지 않아 기존 AC5 동작을 깨지 않는다. Celery `task_acks_late`는 그대로 `False`(기본값) 유지 — 재처리·중복 응답 위험을 만들지 않는다.

**DEF-009(고아 프로세스/이중 기동, Medium) — 부분 수정(핵심 증상 해소, 완전한 Job-Object 기반 보장은 범위 밖).** `_ensure_server_running()`이 새 서브프로세스를 띄우기 전에 `_health_check()`로 "이미 포트가 응답하는 서버가 있는지"를 먼저 확인한다. 이미 응답하면(고아 서버 재사용 가능) 새 프로세스를 띄우지 않고 그대로 반환한다 — TC-041이 관측한 "이중 바인드+VRAM 2.8GB" 증상을 직접 해소한다. `_PID_FILE`(`backend/var/llm/llama-server.pid`)에 기동한 PID를 기록해 ops가 사후 식별할 수 있게 했다. **완전한 해결(부모 프로세스 강제종료 시 자식이 자동으로 함께 죽는 것, Windows Job Object)은 pywin32/ctypes가 필요한 별도 구현이라 이번 재작업 범위에서 다루지 않았다** — atexit 기반 `_shutdown()`은 정상 종료(SIGINT 등)에서만 작동하고 `taskkill /F`/`Stop-Process -Force`에는 작동하지 않는다는 한계가 남아있다(실측: 아래 R6에서 이 한계가 실제로 재현됨 — 고아가 생겼고 PID 파일로 식별해 수동 종료했다).

**DEF-010(워커 메타데이터 미완결, Low/잠복) — 즉시 수정.** `celery_app.py`가 `alembic/env.py`와 동일한 원칙으로 9개 모델 전부를 명시적으로 import한다. `Base.metadata.tables`에 9개 테이블이 전부 등록됨을 확인(R6).

**DEF-011(Redis 무인증 노출, High) — DEC-035 Q2 채택(즉시 반영).** `docker-compose.yml`의 Redis 서비스에 `command: ["redis-server", "--requirepass", "final_redis_pw"]`를 추가하고 포트를 `127.0.0.1:6389:6379`로 바인딩했다(이전 `6389:6379`는 전 인터페이스 공개). `REDIS_URL`(`core/config.py` 기본값, `.env`, `.env.example`)을 `redis://:final_redis_pw@localhost:6389/0`으로 갱신했다. **비밀번호를 코드/compose에 직접 적은 것은 이 저장소가 `POSTGRES_PASSWORD: final_app_pw`에 이미 적용한 것과 동일한 관례**(로컬 개발 전용 compose, DEC-007 — 실제 배포 인프라는 아직 없음)를 따른 것이며, 새로운 보안 저하가 아니라 기존 관례와의 일관성이다. 실제 배포 시에는 반드시 비밀 관리자로 외부화해야 한다(R-8과 함께 09/10 확인 대상, 이 note에서 처음 언급된 리스크가 아님). 추가로 `ws.py::redis_relay_loop()`에 서버→클라이언트 이벤트 화이트리스트(`{queue_status, stage_update, turn_result, report_ready, error}`) 검증을 넣어 비객체/미정의 타입 페이로드를 무시하도록 했다(TC-044의 두 번째 관측, "릴레이는 비객체 JSON도 그대로 전달"을 해소). **Redis pub/sub을 통한 위조 이벤트 자체(로컬호스트 내에서 앱과 동일한 신뢰 경계를 가진 프로세스가 발행)는 이번 범위에서 다루지 않았다** — HMAC 서명 등 이벤트 무결성 검증은 DEC-035가 지시한 범위(바인딩+인증+타입 화이트리스트)를 넘어서는 추가 설계라 임의로 확장하지 않았다.

### R4. 설계서 대비 추가 편차
- 오프닝이 더 이상 LLM을 거치지 않으므로 03-design §4.3 "STT 단계 없이 LLM→TTS만 수행"의 "LLM" 부분이 오프닝에 대해서는 더 이상 문언 그대로가 아니다(대신 "질문은행 원문→TTS"). §4.4 구조화 출력 계약(`TurnLLMOutput`)은 오프닝에도 여전히 내부적으로 사용된다(LLM이 만드는 대신 코드가 직접 채움) — 클라이언트에 보이는 `turn_result` 스키마는 완전히 동일해 API 계약 변경은 없다. 되돌리기 난이도: 낮음(조건문 하나, DEF-001 대응 시 이미 이 방향을 note §2 편차#6이 "권장 검토 방향"으로 예견했었다).

### R5. 06단계 인수조건(Acceptance Criteria) — 재작업분 추가 (기존 §7 AC1~AC6은 그대로 유효)

**사전 조건**: 기존 §7과 동일 + `docker compose up -d`로 Redis를 재기동해 새 `--requirepass`/바인딩을 적용해야 한다(기존 컨테이너를 그대로 쓰면 이전 무인증 설정이 남아있을 수 있음 — `docker compose up -d redis`로 recreate 필요). `alembic upgrade head`로 `f2a9c4d81e36`까지 적용되어야 한다(`alembic current`로 확인).

- **AC-R1(DEF-001)**: `/start` 응답의 `turn_result.ai_text`가 매번 `questions` 테이블의 `category=opening` 항목의 `content`와 **정확히 일치**한다(오프닝은 이제 비결정적이지 않다 — 기존 §7 AC6/§3 "LLM 비결정성"은 후속 질문에만 적용됨을 06이 인지할 것).
- **AC-R2(DEF-002)**: 오프닝 job이 지연/사망 중인 상태에서 사용자가 먼저 답변을 제출해도(TC-030 재현 절차) `GET /transcripts`의 `turn_index`가 중복되지 않는다. DB에서 `(interview_id, turn_index)`로 강제 중복 INSERT를 시도하면 `IntegrityError`(unique violation)로 거부된다.
- **AC-R3(DEF-003/004)**: 서로 다른 주제 20건 이상 반복 제출 시 질문형 비율(정규식 기준, 위 R3 설명 참고) ≥90%. "네"/공백/이모지 등 짧은 입력에 `_BASE_PERSONA`의 대표 문구(예: "시니어 기술 면접관", "정답이나 모범답안")가 낭독되지 않는다.
- **AC-R4(DEF-005)**: 2,500자·4,000자 답변을 제출해도 `turn_result.ai_text`가 고정 폴백문(`_TURN_FALLBACK_TEXT`)이 아닌 LLM 생성 응답이어야 한다(잘라내기 후 컨텍스트 초과가 재발하지 않음 확인). 그 답변 이후의 다음 턴도 연쇄 폴백되지 않아야 한다.
- **AC-R5(DEF-006)**: (목서버 필요) `speak_text`가 공백만인 응답은 `ValidationError`로 거부되어 재시도/폴백 경로로 진입한다.
- **AC-R6(DEF-007)**: 기술 관련 답변의 후속 검색 결과(`question_id`)가 `category=opening`인 항목을 가리키지 않는다. 명백히 무관한 답변(예: 날씨/음식 이야기)에는 `question_id=NULL`이어야 한다(유사도 0.30 미달).
- **AC-R7(DEF-008)**: `stage_update(llm)` 수신 후 워커 프로세스를 강제 종료하고 **150초 이상** 대기하면 WS로 `error`(`code=AI_SERVICE_TIMEOUT`) 이벤트가 도착한다(장시간 대기가 필요하므로, 06이 원하면 `job_watchdog._STARTED_TIMEOUT_SECONDS`를 테스트 중에만 임시로 낮춰(예: 10초) 재현 시간을 단축하는 것을 권장 — 반드시 테스트 후 원복).
- **AC-R8(DEF-009)**: `bin_vulkan/llama-server.exe`를 미리 독립적으로 기동해 포트 8091을 점유한 상태에서 워커를 시작해도, 워커 로그에 "포트 8091에 이미 응답하는 llama-server가 있어 재사용합니다"가 남고 **두 번째 llama-server 프로세스가 뜨지 않는다**(`Get-CimInstance`/`tasklist`로 `llama-server.exe` 프로세스 수가 1개임을 확인).
- **AC-R9(DEF-010)**: 워커 프로세스에서 `python -c "import app.services.celery_app; from app.db.session import Base; print(sorted(Base.metadata.tables))"`가 9개 테이블(`code_submissions, consents, deletion_requests, interviews, questions, rubric_templates, transcripts, users, whiteboard_snapshots`)을 전부 출력한다.
- **AC-R10(DEF-011)**: 호스트에서 `redis-cli -h 127.0.0.1 -p 6389 PING`(비밀번호 없이)이 `NOAUTH Authentication required.`로 거부된다. LAN IP(예: `192.168.x.x`)로의 접속 자체가 연결되지 않는다(바인딩이 127.0.0.1로 좁혀졌으므로 — 기존 TC-044처럼 LAN에서의 접근 가능성 자체를 재확인). Redis pub/sub에 비객체(JSON 배열/숫자/문자열) 또는 정의되지 않은 `type`을 담은 페이로드를 publish해도 WS 클라이언트에 전달되지 않는다(로그에 "화이트리스트 밖 페이로드 무시" 기록).

### R6. 로컬 최소 동작 확인 (실제 실행 로그 요약)
- `alembic heads`로 재작업 착수 전 현재 head가 `e4b6a1c9f2d7`(단일 head) 확인 → 마이그레이션 작성 → `alembic upgrade head` 성공 → `f2a9c4d81e36` 적용, `\d transcripts` 대응 쿼리로 `uq_transcripts_interview_id_turn_index` 확인. 적용 시점 `transcripts` 0건(영향 없음, 재작업 전 사전 확인).
- `ruff check app alembic/env.py` — 통과(0 에러, 3건 발견 후 즉시 수정: `E501` 2건, `UP035` 1건).
- 단위 수준 스모크: `validate_followup_speak_text()` 7개 케이스(질문형/평서문/플레이스홀더/페르소나유출/공백/영어/질문형) 전부 기대값과 일치. `TurnLLMOutput(speak_text="   ")` → `ValidationError` 확인, strip 동작 확인. `insert_transcript_with_retry()`를 실제 DB(임시 candidate+interview)로 호출해 순차 배정(0,1) 확인 후 `turn_index=0` 중복 INSERT를 직접 시도해 `IntegrityError`로 거부됨을 확인, 충돌 이후 호출이 정상적으로 다음 번호(2)를 배정함을 확인(테스트 데이터 삭제로 정리). `search_similar_questions(exclude_categories={opening}, min_similarity=0.30)`을 k8s 질의/무관 질의로 각각 호출해, k8s 질의는 opening 미포함 1건, 무관 질의는 0건 반환됨을 확인.
- **전체 파이프라인 실제 e2e**(3개 프로세스 기동 — DB+Redis 컨테이너, `celery ... --pool=solo -Q ai_pipeline`, `uvicorn app.main:app --port 8181`, 포트 8620/8720/frontend 관련 파일은 건드리지 않음): candidate 회원가입/로그인 → 동의 → interview 생성 → WS 연결 → `/start` → `stage_update(llm)`→`(tts)`→`turn_result`(오프닝) 수신, `ai_text`가 질문은행 opening 문항 원문과 **정확히 일치**함을 확인(DEF-001). 텍스트 턴("MSA/Saga") 제출 → 후속 질문 수신, `question_id`가 `category=technical` 항목을 가리킴(DEF-007, opening 미섞임 확인). 짧은 입력("네") 제출 → 페르소나 낭독 없이 고정 폴백문("답변 감사합니다. 다음 질문으로 넘어가겠습니다.")으로 정상 처리(DEF-004 가드 동작 확인 — RAG 후보가 없어 질문은행 폴백 대신 최종 폴백 문구 사용). `GET /transcripts`로 5개 행(turn_index 0~4) 순서·중복 없음 확인. Redis에서 `job_watch:*` 키가 각 job 성공 직후 자동 삭제됨을 확인(DEF-008 감시 루프의 "정상 종료 시 정리" 동작 확인 — 실패 경로 자체는 150초 대기가 필요해 이번 스모크에서는 재현하지 않음, 06 인계).
- **DEF-009 한계의 실제 재현(의도치 않게)**: 스모크 테스트 종료 시 Celery 워커 프로세스를 `Stop-Process -Force`(강제종료, atexit 미실행)로 종료하자 llama-server 자식 프로세스가 실제로 고아로 남는 것을 확인했다(`llama-server.pid` 파일의 PID와 실제 `Get-CimInstance`로 조회한 고아 프로세스 PID가 일치) — 위 R3 DEF-009 설명에 적어둔 한계("정상 종료에서만 atexit 작동")가 실측으로도 재현됐다. PID 파일 덕분에 즉시 식별해 `Stop-Process -Id <PID> -Force`로 정리했고(DEC-028 준수, 이미지명 기준 종료 없음), VRAM이 기준선(약 514~576MiB)으로 복귀함을 `nvidia-smi`로 확인했다. **이중 기동(두 서버가 동시에 같은 포트를 점유하는 것) 자체는 이번 스모크에서 발생하지 않았다** — 왜냐하면 애초에 고아가 생긴 시점이 스모크 "종료" 단계였고 그 이후 새 워커를 다시 기동하지 않았기 때문이다. AC-R8은 06이 "고아가 이미 떠 있는 상태에서 새 워커를 기동"하는 시나리오로 별도 재현해야 한다.
- Redis 인증: `docker compose up -d redis`로 재기동(재작업된 `docker-compose.yml` 적용) → `redis-cli -a final_redis_pw PING` 성공, 비밀번호 없이 `PING` 시 `NOAUTH Authentication required.` 확인. `docker compose ps`에서 포트 매핑이 `127.0.0.1:6389->6379/tcp`로 표시됨(이전 `0.0.0.0:6389`에서 변경) 확인. 앱의 `settings.redis_url`(새 인증정보 포함)로 정상 PING 확인. Celery 워커 로그에 `transport: redis://:**@localhost:6389/0`로 연결 성공 로그 확인(비밀번호 마스킹 출력).
- **정리(Teardown)**: 스모크 테스트로 만든 candidate 계정 1개와 연쇄 데이터(interviews/transcripts/consents)를 DB에서 직접 DELETE로 정리. 생성된 WAV 3개(`var/media/tts/*.wav`)를 파일명으로 특정해 삭제(기존 10개 baseline은 보존). Redis의 `celery-task-meta-*` 3개를 직접 삭제(`job_watch:*`는 이미 자동 정리되어 있었음, 위 R6 참고). 프로세스는 전부 자신이 기동한 PID만 `Stop-Process -Id <PID> -Force`로 종료(uvicorn 2개, celery 2개, 고아 llama-server 1개) — 병렬 진행 중인 unit-20의 포트 8620 프로세스(37768/21288)는 조회만 하고 건드리지 않았다. `.harness-tmp/u7rework_*`(로그/PID 기록)와 scratchpad의 임시 스크립트는 전부 삭제. `backend/var/llm/llama-server.pid`도 삭제. 최종 `git status`에 이 재작업이 만든 변경 외의 잔여물이 없음을 확인(아래 R7 참고).

### R7. 게이트 1/2 재확인 및 최종 `git status`
- 게이트 1(정적 분석): `ruff check app alembic/env.py` — **All checks passed!** (`.harness-tmp/venv_05_unit7` 재사용, `ruff` 0.16.8). 프론트엔드 변경 없음(해당 없음, 최초 05와 동일 사유).
- 게이트 2(자체 코드 리뷰 체크리스트):
  - [x] 설계서/디자인서 명세와 실제 구현 일치 — R4에 신규 편차(오프닝 LLM 생략) 기록. 나머지는 DEC-035가 확정한 정책을 그대로 구현.
  - [x] 에러 처리 누락 경로 없음 — 신규 코드(turn_numbering의 IntegrityError 처리, job_watchdog의 Redis/CancelledError 처리, llm_engine의 이중 기동 감지)까지 예외를 삼키지 않고 로그/폴백으로 처리.
  - [x] 시스템 경계 검증 — LLM 출력은 여전히 `TurnLLMOutput` 스키마로 강제 검증(공백 거부 추가). 이번 재작업은 신규 사용자 입력 경계를 추가하지 않았다(기존 `TurnCreate` 그대로).
  - [x] 하드코딩된 시크릿/자격증명 — Redis 비밀번호는 R3 DEF-011에서 설명한 대로 기존 `POSTGRES_PASSWORD` 관례와 동일한 로컬 개발용 placeholder이며 실제 운영 시크릿이 아니다(같은 근거로 게이트2 통과 판단).
  - [x] 신규 외부 의존성 없음 — 이번 재작업은 `requirements.txt`에 신규 패키지를 추가하지 않았다(전부 표준 라이브러리 + 기존 의존성 재사용: `celery.result.AsyncResult`, `redis.asyncio`, `pydantic.field_validator`, `re`, `time`).
  - [x] 범위 외 변경 없음 — 포트 8620/8720 및 그 소유 파일(`frontend/app/interviews/**`, `frontend/components/WebcamPreview.tsx`, `frontend/lib/useMediaQuery.ts`, unit-19 목록 화면)은 조회조차 하지 않았다. `docs/harness/decisions.md`/`traceability.md`는 편집하지 않았다(오케스트레이터 전용, 반영 제안은 최종 보고로 전달). `git add`/`commit`도 하지 않았다.
- 최종 `git status --short`(재작업 완료 시점, 이 유닛이 만들지 않은 변경도 함께 보임 — 병렬 진행 중인 unit-19/20 작업, 구분은 최종 보고 참고):
```
 M backend/.env.example
 M backend/app/api/v1/interviews.py
 M backend/app/api/v1/ws.py
 M backend/app/core/config.py
 M backend/app/main.py
 M backend/app/services/celery_app.py
 M backend/app/services/interview_prompts.py
 M backend/app/services/job_queue.py
 M backend/app/services/llm_engine.py
 M backend/app/services/rag_engine.py
 M backend/app/worker/tasks.py
 M backend/docker-compose.yml
 M docs/harness/decisions.md
 M docs/harness/units/unit-19-test.md
 M frontend/next-env.d.ts
?? "99.현재상태/현재상태_02.png"
?? backend/alembic/versions/f2a9c4d81e36_v9_transcripts_unique_turn_index.py
?? backend/app/services/job_watchdog.py
?? backend/app/services/turn_numbering.py
?? docs/harness/verify-log_unit-19-test.md
?? frontend/e2e/unit-19/
?? frontend/e2e/unit-20/
```
`docs/harness/decisions.md`의 변경은 이번 세션 시작 시점부터 이미 있던 것(오케스트레이터 소관, 이 유닛이 만든 변경 아님). `docs/harness/units/unit-19-test.md`·`docs/harness/verify-log_unit-19-test.md`·`frontend/next-env.d.ts`·`frontend/e2e/unit-19/`·`frontend/e2e/unit-20/`은 병렬 진행 중인 다른 에이전트(unit-19/unit-20)의 산출물이며 이 유닛은 건드리지 않았다(내용 확인도 하지 않음, 그대로 보존). `99.현재상태/` PNG는 사용자 소유 미추적 파일로 이전부터 존재했고 이번에도 건드리지 않았다.
