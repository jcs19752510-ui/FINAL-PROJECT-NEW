# unit-24 구현 노트 — 원안(REQ-018/019 축소판) 음성 Prosody 분석

- 작성 에이전트: 본 세션(05+06 역할 겸임), 작성일: 2026-09-22
- 배경: ③ 매트릭스 "가능(중)" 항목 순서(STT스트리밍→Prosody→...) 중 두 번째. 단,
  **순서를 1건 재조정**했다 — 아래 "순서 변경 사유" 참고.

## 0. 순서 변경 사유 (사용자 승인 순서에서 이탈, 사유 명시)

원래 순서는 "STT 실시간 스트리밍 전환"이 먼저였으나, 착수 직전 `app/api/v1/
interviews.py`의 `_submit_voice_turn` 상단에서 **2026-09-22(오늘) 날짜로 이미
기록된 실제 장애 대응 주석**을 발견했다: "음성 답변 제출이 실제 백엔드 행을
일으킨 근본 원인 중 하나로 확인되어 명시적으로 스레드풀에 위임한다." 즉 이
함수는 오늘 이미 한 차례 실제 인시던트가 발생해 막 수습된 코드다.

WS 기반 실시간 오디오 스트리밍으로의 재설계는 (1) 이 함수와 WS 게이트웨이(`app/
api/v1/ws.py`, 현재 서버→클라이언트 push 전용으로 명시적으로 설계된 채널)를
동시에 건드려야 하고, (2) WebM/Opus 청크 재조립이라는 만만치 않은 신규 문제가
있고, (3) 이 환경에 브라우저 자동화 도구가 없어 실제 MediaRecorder 청크 전송을
검증할 방법이 없다. 오늘 막 수습된 고위험 경로를 검증 불가능한 상태로 재설계하는
것은 20년차 엔지니어 판단으로 무리라고 보고, **더 안전하고 값을 낼 수 있는
"Prosody 분석"을 먼저 진행**했다. STT 스트리밍은 별도로 사용자 확인 후 재개 여부
결정 필요(진행 중인 대화에서 별도 보고).

## 1. 구현 범위

- `backend/app/services/prosody_engine.py`(신규): PyAV(`av`, faster-whisper의
  기존 의존성 재사용)로 임의 컨테이너/코덱을 모노 16kHz float32 PCM으로 디코딩 →
  `librosa.pyin`으로 피치(Hz) 평균/표준편차, 유성음 비율 추출. "자신감/긴장도"
  같은 해석 라벨은 만들지 않고 원시 수치만 반환(공정성/설명가능성 원칙, 모듈
  docstring 참고).
- `backend/requirements.txt`: `librosa>=0.10,<0.11` 추가, 실제 설치·검증 완료.
- `backend/app/models/transcript.py`: `prosody_json`(JSONB, nullable) 컬럼 추가.
- `backend/alembic/versions/b3f8d2a916c5_v12_transcript_prosody.py`(신규 마이그레이션).
- `backend/app/api/v1/interviews.py`: `_submit_voice_turn`에서 STT 뒤에 prosody
  분석을 추가 호출(threadpool 위임, 실패해도 턴 저장은 막지 않는 그레이스풀
  디그레이드). 모듈에 `logger` 신설.
- `backend/app/schemas/transcript.py`: `TranscriptOut.prosody` 필드 추가(`prosody_json`
  컬럼에서 별칭 매핑).
- `backend/app/main.py`: 서버 기동 시 백그라운드로 `prosody_engine.warmup()` 실행
  (아래 2절 DEF-002 대응).

## 2. 실측으로 발견한 결함

| ID | 설명 | 재현 | 심각도 | 상태 |
|---|---|---|---|---|
| DEF-001 | `librosa.pyin`의 numba JIT 완전 콜드 컴파일이 최대 약 32초 소요(디스크 캐시 있으면 ~5초, 이후 <1초) — 실사용자의 첫 음성 답변이 이 비용을 그대로 떠안으면 타임아웃 위험 | 신규 프로세스에서 Piper로 합성한 실제 한국어 음성을 `analyze_prosody()`에 직접 전달, 최초 호출 시간 실측 | Medium(기능은 정상 동작하나 콜드 지연이 큼) | Fixed — 서버 기동 시 백그라운드 예열(`warmup()`) 추가 |
| DEF-002 | `loop.run_in_executor(...)`는 코루틴이 아닌 `Future`를 반환 — `asyncio.create_task()`에 직접 넘기면 `TypeError: a coroutine was expected`로 **서버 기동 자체가 실패**함 | uvicorn 서버 프로세스로 직접 재현(신규 포트 8302, startup 단계에서 크래시 확인) | High(서버가 아예 안 뜸) | Fixed — 코루틴 래퍼(`_run_prosody_warmup`)로 감싸 수정, 재기동 성공 확인 |

## 3. 범위 밖 — 심각한 별개 발견 (사용자에게 별도 보고 필요)

이 유닛 검증 도중, **`content_text`(AI 질문·지원자 답변 전체 대화 텍스트)가
DB에 손상된 채로 저장**되는 것을 실제 HTTP E2E 테스트로 확인했다. DB에서 직접
`content_text`를 조회하면 유니코드 치환 문자(U+FFFD)가 섞여 있어 **표시 문제가
아니라 실제 데이터 손실**이다(복구 불가능한 손상).

- 이 유닛(prosody)이 원인이 아님을 확인: 내가 건드린 파일은 `content_text` 처리
  경로를 전혀 건드리지 않음(모델에 컬럼 추가, STT 이후 별도 analyze_prosody
  호출만 추가).
- `tts_engine.py`는 정확히 이 계열 문제(Windows 콘솔/서브프로세스 코드페이지가
  한글을 손상시키는 현상)를 이미 겪고 명시적으로 우회한 이력이 있음("unit-4/
  5-note.md가 이미 겪은 것과 동일 현상" — 코드 주석 원문). `llm_engine.py`의
  HTTP JSON 송수신은 UTF-8 명시 처리로 확인됨(1차 조사에서는 정상).
- 근본 원인 미확정 — 이 세션이 uvicorn을 수동으로 새 포트에 띄운 테스트 환경
  특유의 문제(예: `PYTHONIOENCODING` 미설정)일 가능성과, 실제 상시 운영 경로에서도
  재현되는 진짜 결함일 가능성을 모두 배제하지 못함. AI 생성 턴과 STT 인식 턴
  **양쪽 모두**에서 손상이 관찰돼 STT 한 곳만의 문제는 아닌 것으로 보임.
- **이 유닛의 범위가 아니라 별도 조사가 필요** — 사용자에게 대화로 별도 보고.

## 4. 인수인계

- STT 실시간 스트리밍 전환: 보류 상태(0절 사유), 재개 여부 사용자 결정 필요.
- `content_text` 손상 건: 심각도가 이 6개 항목 전체보다 높을 수 있음 — 우선순위
  재조정 필요할 수 있음(사용자 결정 필요).

## 5. [2026-09-23 정정, DEC-051] §3의 "content_text 손상"은 오탐이었음

STT 스트리밍 재개 직전 재조사한 결과, §3에서 보고한 `content_text` 손상은
**실제 데이터 손상이 아니라 콘솔 표시 오류(오탐)**로 판정됐다. raw psycopg
왕복 + 실제 ORM(`Transcript` 모델) 경로 양쪽 다 바이트 단위 완전 일치 확인,
근거·검증 방법은 `docs/harness/decisions.md` DEC-051 참고. §3 원문은 당시
실제로 그렇게 판단했던 기록이므로 삭제하지 않고 그대로 둔다 — 이후 unit-25가
이 오탐을 근거로 암호화 범위를 좁힌 결정(DEC-040)도 전제가 틀렸을 뿐 그
자체가 잘못된 절차는 아니었다(원인 미확정 상태에서 보수적으로 범위를 좁힌
판단은 그 시점 기준으로는 합리적이었음).
