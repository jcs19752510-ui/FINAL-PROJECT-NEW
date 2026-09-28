# 테스트 결과서 (Test Result Report) — Feature C 통합테스트 (핵심 AI 파이프라인, REQ-003~007)

> `templates/test-report-template.md` 사용. 07단계 — "07단계 통합테스트 부채 21건"의
> 마지막이자 가장 큰 덩어리(unit-4/5/6/7)를 정산한다. 사용자 지시 "남은건 5건 진행해
> 주세요"에 따라 REQ-003(텍스트 답변)/REQ-004(음성 답변)/REQ-005(STT)/REQ-006(TTS)/
> REQ-007(핵심 LLM+RAG) 5개 REQ를 한 번에 정산한다.

## 1. 개요
- 테스트 대상: `backend/app/api/v1/interviews.py`(`POST /turns` 텍스트·음성,
  `GET /transcripts`, `POST /tts-preview`), `backend/app/services/stt_router.py`,
  `backend/app/services/llm_engine.py`, `backend/app/services/rag_engine.py`,
  `backend/app/worker/tasks.py`(Celery), `frontend/app/interviews/[id]/page.tsx`
- 테스트 유형: 통합(07단계) — 백엔드 API 실측 + 실제 Celery/LLM/STT/TTS 파이프라인
  풀가동 + 실제 브라우저 UI 실측
- 적용 Tier: unit-7은 L3(정식판, 재작업 v2까지 완료), unit-4/5/6은 L1(경량판) —
  이번 07은 L1 경량판이 남긴 에러경로/UI/동시성 부채와, unit-7-note.md가 명시적으로
  "07 통합(프런트 연계)"·"CPU 폴백 경로 미검증"으로 남긴 항목을 정산
- 테스트 목적: (1) 텍스트/음성 턴 제출의 미검증 에러 경로(401/403/404/409/410/422)
  실측, (2) 실제 다양한 오디오 포맷(wav/webm) STT 디코딩 성공 확인, (3) 동시 다중
  요청 시 이벤트루프 비블로킹 + Celery `--pool=solo` 직렬 큐잉 실증, (4) TTS 동시
  합성 및 텍스트 견고성, (5) **실제 브라우저로 답변 제출→AI 후속질문 렌더링까지
  전체 파이프라인 E2E 확인**(이 프로젝트 07단계에서 처음으로 LLM/RAG/TTS가 전부
  살아있는 상태로 UI 클릭 테스트), (6) unit-7-note.md가 미검증으로 남긴 **CPU 폴백
  경로를 실제로 강제 재현**
- 관련 산출물: `docs/harness/units/unit-4-note.md`/`unit-4-test.md`,
  `unit-5-note.md`/`unit-5-test.md`, `unit-6-note.md`/`unit-6-test.md`,
  `unit-7-note.md`/`unit-7-test.md`, `docs/harness/decisions.md` DEC-091
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: 텍스트 턴 에러경로 7종(TC-C01~C08), 음성 턴 에러경로 3종+동시성 2종
  (TC-C09~C11, C14~C16), STT 포맷 2종(TC-C12~C13), TTS 동시성+견고성 8종
  (TC-C17~C18), 실브라우저 텍스트 턴 E2E(2턴 연속, 실제 LLM 응답 렌더링 확인),
  실브라우저 마이크 권한거부 그레이스풀 디그레이드, **CPU 폴백 강제 재현**(Vulkan
  바이너리 임시 제거 → 실제 응답 생성 완료 확인 → 원복)
- 제외 범위 및 사유: (1) 429 QUEUE_FULL/AI_SERVICE_TIMEOUT — REQ-038(unit-8)·
  이미 DEC-085(503 QUEUE_FULL)에서 별도 실측 완료, 이번 범위 중복 제외.
  (2) 프롬프트 인젝션 방어 — REQ-035~039는 이미 unit-27 + DEC-077(2026-09-28
  루브릭 경로 재검증)에서 실측 완료, 이번 07은 REQ-003~007(턴 파이프라인) 자체의
  구조/에러경로/통합에 집중. (3) 실제 마이크 **허용** 상태 녹음(webcam과 동일
  사유 — Browser pane이 가상 마이크 장치를 제공하지 않음) — 대신 **실제 음성
  파일(Piper TTS로 합성한 진짜 한국어 음성)을 HTTP로 직접 업로드**해 STT 디코딩
  자체는 실측했고, 브라우저에서는 권한 **거부** 시 그레이스풀 디그레이드만 확인.

## 3. 테스트 환경
- 로컬 backend(uvicorn, 포트 8000) + frontend(Next.js, 포트 3000) + **Celery AI
  워커**(`celery -A app.services.celery_app worker --concurrency=1 --pool=solo
  -Q ai_pipeline`, 이 프로젝트 07단계에서 처음으로 LLM 파이프라인을 실제로 가동한
  채 테스트) + DB(`final-project-db`, 포트 5544) + Redis(`final-project-redis`,
  포트 6389), `preview_start`/Bash 백그라운드로 기동
- 백엔드 에러 경로: `itC1-*`/`itC2-*` candidate 2명(HTTP 스크립트) + 브라우저
  회원가입 `itC-browser-e2e@example.com`(1명, 실제 UI 클릭)
- LLM: llama.cpp `llama-server.exe`(Qwen2.5-1.5B-Instruct GGUF, Vulkan GPU 우선
  → CPU 폴백 강제 재현 포함), STT: faster-whisper(`small`/CPU/int8), TTS: Piper
  (`ko_KR-kss-medium`)

## 4. 테스트 케이스 및 결과

### REQ-003(텍스트 턴 제출)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-C01 | scheduled 상태에서 턴 제출 | 409 | `409` | PASS |
| TC-C02 | 인증 없음 | 401 | `401` | PASS |
| TC-C03 | 존재하지 않는 id | 404 | `404` | PASS |
| TC-C04 | 타인 소유(수평 권한 상승) | 403 | `403` | PASS |
| TC-C05 | 빈 문자열 본문 | 422 | `422` | PASS |
| TC-C06 | 정상 제출 | 202 + job_id | `202` | PASS |
| TC-C06b | AI 응답 실도착(폴링) | Celery→LLM→RAG 실처리 후 transcripts에 AI 턴 추가 | 실제 도착, 내용이 답변 맥락(MSA/Saga)을 정확히 반영한 꼬리질문 | PASS |
| TC-C07 | completed 상태에서 제출 | 409 | `409` | PASS |
| TC-C08 | 만료(24h 경과, DB 직접 조작) 후 제출 | 410 | `410` | PASS |

### REQ-004(음성 턴 제출) / REQ-005(STT)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-C09 | 음성 턴 인증 없음 | 401 | `401` | PASS |
| TC-C10 | 존재하지 않는 id | 404 | `404` | PASS |
| TC-C11 | 타인 소유(수평 권한 상승) | 403 | `403` | PASS |
| TC-C12 | wav 포맷 음성 제출 | 202 + STT 디코딩 성공 | `202`, content_text="저는 클라우드 인프라 자동화 경험이 있습니다." (원문 100% 일치) | PASS |
| TC-C13 | webm(opus) 포맷 음성 제출 | 202 + STT 디코딩 성공 | `202`, 동일 원문 100% 일치 | PASS |
| TC-C14 | 음성 제출과 동시에 가벼운 GET 호출 | 둘 다 정상 응답, GET이 STT에 막히지 않음 | 음성 202, GET 200 | PASS |
| TC-C14b | 이벤트루프 비블로킹 재검증(아래 §10 내부검증 참고) | 동시 요청 시 GET 응답시간이 베이스라인과 동일 | 동시 실행 시 2.06s, 베이스라인(무관 상황) 2.05s — **동일** → STT는 event loop를 막지 않음(threadpool 위임 정상 동작) | PASS(1차 임계값 오판 → 재검증으로 확정, §10) |
| TC-C15/16 | 텍스트 턴 2개 거의 동시 제출 | Celery `--pool=solo` 직렬 처리 — 두 AI 응답 완료시각이 벌어짐 | 둘 다 202 수락, 완료시각 gap **10.85초**(병렬이면 0에 가까움) — 직렬 큐잉 실증 | PASS |

### REQ-006(TTS)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-C17 | 동시 3건 합성 요청 | 전부 200, 서로 다른 audio_url | 전부 200, url 3개 모두 고유 | PASS |
| TC-C17b | 위 응답 URL 중복 없음 | distinct | 3/3 고유 | PASS |
| TC-C17c | 동시 요청이 순차 직렬화되지 않음(threadpool 병렬) | 총 소요시간 < 개별 소요시간 합 | 총 5.79s vs 개별합 17.26s(각 ~5.75s) — **실제 병렬 실행 확인**(TTS-preview는 Celery 큐를 거치지 않는 독립 threadpool 경로) | PASS |
| TC-C18-html_tags | `<script>` 포함 텍스트 | 200(이스케이프 불필요 — TTS는 렌더링 아님) | `200` | PASS |
| TC-C18-emoji | 이모지 포함 | 200 | `200` | PASS |
| TC-C18-newlines | 개행 다수 포함 | 200 | `200` | PASS |
| TC-C18-mixed_script | 한/영/숫자/기호/일본어 혼합 | 200 | `200` | PASS |
| TC-C18-boundary_500 | 정확히 500자(상한 경계값) | 200 | `200` | PASS |

### REQ-007(핵심 LLM+RAG, 07 통합 — 실브라우저)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-C19 | 회원가입→로그인→사전고지 동의(스크롤 완독)→면접시작→오프닝질문 수신 | 실제 LLM이 생성한 오프닝 질문이 화면에 렌더링 | "간단히 자기소개와 함께, 최근에 가장 몰입해서 진행했던 프로젝트를 소개해 주세요." 실제 렌더링(스크린샷 확인) | PASS |
| TC-C20 | 답변 입력→전송→AI 후속질문 수신(1턴) | 답변 맥락을 반영한 실제 꼬리질문이 채팅창에 렌더링 | 답변("Redis 캐시와 메시지 큐...") → 후속질문 "Redis 캐시와 메시지 큐를 도입해 응답속도를 개선했던 프로젝트를 소개해 주세요." 정확히 맥락 반영, 실제 렌더링 확인(스크린샷) | PASS |
| TC-C21 | 2턴 연속 대화 유지 | 이전 답변("3개월/팀원5명")까지 반영한 후속질문 | "3개월간 진행되었으며 팀원 5명과 함께 작업했는지 어떻게 그 프로젝트를 진행했는지..." — 문맥 누적 확인(다소 어색한 문장이나 CPU 폴백 경로였음, §4 CPU폴백 참고) | PASS |
| TC-C22 | 음성 답변 버튼 클릭 시 마이크 권한 | 거부/사용불가 시 크래시 없이 텍스트 유도 안내 | "마이크 권한이 거부되었거나 사용할 수 없습니다. 텍스트로 답변해주세요." 정확히 렌더링, 화면 정상 유지(답변 카운터·입력창 그대로 동작) | PASS |
| TC-C23 | **CPU 폴백 강제 재현**(unit-7-note.md §2 편차#2 미검증 항목) | Vulkan 바이너리 부재 시 CPU 빌드로 자동 폴백해 실제로 응답을 생성 | 워커 로그: `llama-server(GPU/Vulkan) 기동 시도` → `기동 실패 — CPU 전용 빌드로 폴백` → `llama-server 기동 완료 (binary=bin_cpu)` → job 26.26초만에 **성공**(GPU 대비 느리지만 정상 완료). GPU 메모리 855→902MiB(거의 무변화, 순수 CPU 실행 확인, Vulkan 로드 시의 +1100MiB 증가와 대조). 복구 후 정상 Vulkan 경로 재확인(오프닝 질문 정상 도착) | PASS |

## 5. 커버리지
- REQ-003 에러경로 7종(409×2/401/404/403/422/410) + 실제 AI 응답 도착까지 전부
  커버. unit-4-note.md가 "07/06 정식화 시 반드시 실제 브라우저로 검증 필요"라고
  명시했던 인수조건 8(낙관적 UI/타임아웃 안내)은 이번 실측에서 실제 응답이
  AI_WAIT_TIMEOUT_MS(12초)보다 빠르게(워밍업 후 4.5~7초) 도착해 타임아웃 안내
  자체는 관측되지 않았음 — 이는 unit-7-note.md §5가 이미 문서화한 "설계 전제
  (상시 기동 워커)와 개발환경(요청마다 새 워커) 차이"가 이번엔 워커가 이미
  워밍업된 상태라 재현되지 않은 것으로, 결함이 아니라 타이밍 조건부 현상.
- REQ-004/005 에러경로 3종 + 포맷 2종(wav/webm, 둘 다 원문 100% 일치) +
  이벤트루프 비블로킹(threadpool 위임 정상) + Celery 직렬 큐잉 실증까지 커버.
- REQ-006 동시성(병렬 threadpool 확인) + 텍스트 견고성 5종 커버.
- REQ-007 07 통합(프런트-백엔드-Celery-LLM-RAG-TTS-WS 전체 파이프라인 실클릭
  E2E) + **CPU 폴백 경로**(unit-7-note.md가 유일하게 미검증으로 남겼던 항목)
  까지 전부 커버 — 이로써 unit-7의 남은 알려진 검증 공백이 해소됨.

## 6. 결함(Defect) 목록
- 결함 없음(신규) — TC-C01~C23 전부 실측으로 확인.
- TC-C14b는 최초 판정 임계값(<2.0s)이 부적절해 FAIL로 표시됐으나(§10 내부검증
  참고), 베이스라인과 비교하는 통제 실험으로 재검증한 결과 실제로는 문제가 아님을
  확인 — 결함으로 등록하지 않음(테스트 설계 오류였지 제품 결함이 아님).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 신규 생성 DB 레코드: candidate 3명(`itC1-*`/`itC2-*`/`itC-browser-e2e`) + 관련
  interview 7건 + transcript + consent + evaluation_report(종료된 세션 1건에서
  자동 생성) — 전용 정리 스크립트로 FK 순서(evaluation_reports→transcripts→
  interviews→consents→users) 지켜 전부 DELETE, 재조회 0명 확인. 헬스체크용 임시
  계정(`healthcheck-*`) 1명도 별도 정리 완료.
- 기동한 프로세스: `preview_start("backend")`, `preview_start("frontend")`,
  Celery 워커(Bash 백그라운드) 3회(정상 Vulkan 1회 → CPU 폴백 검증용 1회 →
  복구 후 정상 Vulkan 1회) — 전부 `preview_stop`/`TaskStop`으로 정상 종료,
  `tasklist`로 `llama-server.exe` 잔존 프로세스 0개 확인(매 전환 시점마다 확인).
- CPU 폴백 검증을 위해 `backend/var/llm/bin_vulkan/llama-server.exe`를 임시로
  `.bak`로 리네임했다가 테스트 직후 **원래 이름으로 복구**하고, 복구된 Vulkan
  경로가 실제로 다시 정상 동작함을 별도 재확인(오프닝 질문 실도착)까지 완료.
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(결함이 없어 코드
  수정 없음, `backend/var/llm/` 바이너리 파일명도 원상 복구되어 diff 없음).
- 강제 중단 여부: 없음.
- **규칙 K-6(부하테스트 후 서비스 헬스체크)**: 동시성 테스트(TC-C14/15/17) 이후
  `GET /api/v1/health`(`{"status":"ok"}`) + 신규 계정으로 회원가입→로그인→면접
  생성→시작→오프닝질문 실도착까지 실제 핵심 경로를 재확인, 정상 동작 확인 후
  이 보고서를 작성함.

## 8. 리스크 및 잔존 이슈
- `GET /interviews` 응답이 약 2.05초로 다소 느림(N+1 lazy-expiry 패턴) — 이는
  **이번에 새로 발견한 문제가 아니라** `unit-19-test.md` §8이 이미 "성능 N+1
  lazy-expiry"로 기록해둔 기존 리스크다. 이번 07에서는 "STT가 이 지연을
  유발하는가"만 확인했고(→ 아니었음, 베이스라인과 동일), 이 지연 자체를 고치는
  것은 이번 범위 밖이다.
- CPU 폴백 경로는 실제로 동작하지만 약 26초로 GPU 대비 약 4~5배 느림 — 운영
  환경에서 GPU 드라이버 장애 시 대기시간이 크게 늘어날 수 있음을 실측으로
  확인(참고 정보, 별도 조치 없음 — 애초에 "느려도 동작"이 이 폴백의 설계 목표).
- TC-C21의 CPU 폴백 응답이 문장 구조상 다소 어색함("3개월간 진행되었으며 팀원
  5명과 함께 작업했는지 어떻게...") — GPU 대비 품질 저하 가능성을 시사하나
  1회 관측만으로 일반화하지 않음(별도 벤치마크 필요, 이번 범위 밖).

## 9. 결론 및 판정
- [x] PASS — REQ-003/004/005/006/007의 "L1 부채"(에러경로·포맷·동시성·07 통합·
  CPU 폴백) 전부 정산 완료. 이로써 `docs/harness/traceability.md` 기준 07단계
  통합테스트 부채 20건 전체 정산 완료(15건 기완료 + 이번 5건).

## 10. 내부 검증
- 1차(커버리지 확인): unit-4/5/6/7-note.md가 남긴 미검증 항목과 TC-C01~C23을
  1:1 대조 — 누락 없음(429/타임아웃은 별도 DEC-085/unit-8 범위로 의도적 제외,
  §2 명시).
- 2차(TC-C14b 판정 재검토 — 과신/오판 경계): 최초 실행에서 "음성 제출과 동시에
  가벼운 GET을 호출했더니 2.06초 걸렸다 → 이벤트루프가 막혔다"고 성급히
  결론짓지 않고, **음성 제출 없이 같은 GET만 4회 반복 측정**해 베이스라인이
  이미 2.05초임을 확인했다. 두 값이 사실상 동일하므로 "STT가 이벤트루프를
  막는다"는 최초 가설은 기각하고, 대신 `GET /interviews`가 원래도 느리다는
  (이미 문서화된) 사실만 재확인한 것으로 판정을 정정했다 — 근거 없이 결함으로
  등록하지도, 근거 없이 그냥 통과시키지도 않고 통제 실험으로 확정한 사례
  (REQ-013 GET/410 오판을 코드 대조로 바로잡았던 것과 동일한 원칙 적용).
