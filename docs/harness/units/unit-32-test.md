# 테스트 결과서 (Test Result Report) — unit-32

## 1. 개요
- 테스트 대상: 벤더 어댑터 3종(ElevenLabs TTS, Deepgram STT, Pinecone VectorDB)
- 테스트 유형: 단위(문법/정적 검토만 — 기능 테스트 불가, 아래 사유)
- 적용 Tier: Low(운영 코드에 연결되지 않은 격리 파일)
- 테스트 목적: 문법 오류 없음 확인. **기능 검증은 API 키 부재로 수행 불가**.
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위: `py_compile`+`ruff check` 3개 파일
- 제외 범위 및 사유: 실제 벤더 API 호출 — API 키가 없어 원천적으로 불가능
  (사용자와 사전 합의된 범위, unit-32-note.md §2).

## 3. 테스트 환경
- Windows, Python 3.13(backend/.venv)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | 문법/린트(3개 파일) | `py_compile`+`ruff check` | 오류 0건 | clean | PASS |

## 5. 커버리지
- 해당 없음(사유: 기능 코드 경로를 실행할 방법이 없어 커버리지 측정 자체가
  무의미 — API 키 확보 전까지는 정적 검토가 유일하게 가능한 검증 수단).

## 6. 결함(Defect) 목록
- 결함 없음(단, "결함 없음"의 의미가 제한적임 — 4절 참고. 문법 오류가 없다는
  뜻이지 기능이 올바르다는 뜻이 아니다).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트 없음(파일 작성 외 프로세스/DB/네트워크 자원 생성 없음)
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- **이 3개 파일은 단 한 번도 실행되지 않았다.** 실제 벤더 서버와의 스키마
  불일치, 인증 방식 오류, 응답 포맷 가정 오류 등이 있어도 이 테스트로는
  전혀 발견되지 않는다. 실제 연결 전 unit-32-note.md §4 체크리스트를 반드시
  따를 것.

## 9. 결론 및 판정
- [ ] PASS
- [x] CONDITIONAL PASS — 조건: **정적 검토(문법)만 통과**, 기능적으로는
  "PASS도 FAIL도 아닌 미검증" 상태. API 키 확보 후 정식 06단계 테스트 필수 —
  이 보고서만으로 "완료"로 간주하지 말 것.

## 10. 내부 검증
- N/A — 문법 검토 1개 케이스뿐이라 반복 검증의 실익 없음.

---

## 후속 실측 — Deepgram (2026-09-23, DEC-057)

사용자가 Deepgram API 키를 발급·제공(`backend/.env`에 직접 저장, 키 값은 대화에 한 번만 노출된 뒤 파일로만 취급). ElevenLabs/OpenAI는 아직 미제공 — 이 절은 **Deepgram 하나만** 다룬다.

### 테스트 케이스
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-002 | 실제 Deepgram API 호출(한국어 STT) | Piper로 "안녕하세요 저는 실시간 음성 인식 테스트를 진행하고 있습니다." 합성 → `transcribe_audio_deepgram(wav_bytes, api_key)` 실제 호출(`.harness-tmp/verify_deepgram.py`) | 원문과 일치하는 한국어 텍스트 반환 | `"안녕하세요 저는 실시간 음성 인식 테스트를 진행하고 있습니다."` — 정확히 일치 | Pass |
| TC-003 | 응답 스키마 실측 확인 | 위 호출 응답에서 `results.channels[0].alternatives[0].transcript` 경로 실제 파싱 성공 여부 | 어댑터 docstring의 "실측 미확인" 가정이 맞는지 확인 | 정확히 그 경로로 파싱 성공 — 가정이 맞았음, `KeyError` 없음 | Pass |

### 결함
- 없음. 다만 어댑터의 `Content-Type: "audio/wav"` 고정값(코드 주석에 "실제 연결 시 업로드 파일의 실제 MIME 타입으로 교체 필요"로 표시됨)은 이번 테스트가 실제로 WAV를 보냈기 때문에 우연히 맞았다 — `interviews.py`가 받는 브라우저 업로드(webm 등)를 그대로 넘기면 이 고정값이 깨질 수 있다. **실제 엔드포인트 연결 시 반드시 고쳐야 함**(unit-32-note.md §4 체크리스트에 이미 있던 항목, 이번 실측으로 근거 보강).

### 정리(규칙 K)
- 생성 파일: `.harness-tmp/verify_deepgram.py`(스크립트 자체), 임시 WAV는 메모리에서만 생성되어 디스크에 남지 않음(Piper 어댑터가 아니라 `PiperTTSEngine.synthesize()`를 직접 호출해 bytes만 받음). 정리 대상 없음.

### 판정 갱신
- Deepgram: **CONDITIONAL PASS → 기능 검증 PASS로 승격**(단, 여전히 어떤 API 엔드포인트에도 배선되지 않은 상태 — 운영 경로는 DEC-005 그대로 로컬 faster-whisper). ElevenLabs/Pinecone은 키 미제공으로 그대로 CONDITIONAL PASS(9절 원문 유지).
- 내부 검증: Tier Low이고 1차(위 TC-002/003) 결함 0건이므로 2차 생략 가능(규칙 B Low 예외) — 생략함.

---

## 후속 배선 — 실제 음성 제출 경로 연결 (2026-09-23, DEC-063)

사용자가 "부분착수/코드준비 항목을 완료로 올릴 방법이 있는지" 질의 → 이 항목(Deepgram)은
키 검증까지 끝난 상태라 **돈 없이 순수 개발로 완료 가능**하다고 판단해 사용자가 승인,
실제 배선 작업을 진행했다.

### 구현
- `stt_adapter_deepgram.transcribe_audio_deepgram()`: `Content-Type` 하드코딩(`"audio/wav"`)을
  제거하고 호출부가 실제 업로드 MIME 타입을 전달하는 `content_type` 인자로 교체 —
  TC-003 결함 메모("webm 등 실제 업로드 시 깨질 수 있음")가 지적한 문제를 해소.
- 신규 `app/services/stt_router.py::transcribe_audio_smart(audio_bytes, content_type)`:
  `settings.deepgram_api_key`가 설정돼 있으면 Deepgram을 먼저 시도하고, 미설정이거나
  호출 실패(네트워크 오류·크레딧 소진 등) 시 조용히 `stt_engine.transcribe_audio()`
  (faster-whisper)로 폴백한다 — 운영 기본값은 여전히 무료 로컬 경로(DEC-005 유지),
  키가 있을 때만 Deepgram이 우선 사용된다.
- `app/api/v1/interviews.py`의 실제 음성 제출 경로 2곳(`_submit_voice_turn`의 최종 제출,
  `unit-36` 미리보기 엔드포인트)에서 `transcribe_audio` 직접 호출을 `transcribe_audio_smart`로
  교체하고 업로드 파일의 `audio.content_type`을 그대로 전달.

### 테스트 케이스
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-004 | 직접 함수 호출 — 라우터가 Deepgram을 실제로 타는지 | Piper로 합성한 실제 한국어 WAV를 `transcribe_audio_smart(wav_bytes, "audio/wav")`에 전달 | Deepgram이 인식한 텍스트 반환(faster-whisper 모델은 로드되지 않아야 함) | `"안녕하세요 반갑습니다. 오늘 면접에 참여해 주셔서 감사합니다."` 반환. 로그에 "faster-whisper 모델 로딩 시작" 부재 확인 — Deepgram 경로가 실제로 사용됨 | Pass |
| TC-005 | 실 HTTP E2E — 인증 포함 전 구간 | Docker(`final-project-db`/`final-project-redis`) 기동 상태에서 uvicorn(8010) 실행, httpx로 회원가입→로그인→`biometric_voice`+`ai_interview_notice` 동의→면접생성→`start`(live 전환)→`POST /interviews/{id}/turns`(multipart, `audio/wav`) | 202 Accepted, 저장된 transcript의 `content_text`가 Deepgram 인식 결과와 일치 | `202 {"job_id":"..."}`, `GET .../transcripts` 응답의 `content_text`가 TC-004와 정확히 동일한 문장. 서버 로그에 Deepgram 폴백 경고 없음(정상 경로로 성공했음을 재확인) | Pass |

### 결함
- 없음.

### 정리(규칙 K)
- 테스트로 생성한 계정 1건·동의 2건·면접 1건·transcript 1건은 검증 직후 스크립트로 즉시 삭제 완료.
- 테스트용 uvicorn(포트 8010) 프로세스 종료 완료. `final-project-db`/`final-project-redis`는 프로젝트 표준 개발 인프라이므로 유지.
- `.harness-tmp/`에 남긴 산출물 없음(스크립트는 세션 스크래치패드에서 실행).

### 판정 갱신(최종)
- Deepgram STT: **부분착수 → 완료**(③ 매트릭스 갱신 대상). 실제 서비스 경로(`POST /interviews/{id}/turns`, `.../turns/preview`)에 배선 완료, 인증 포함 실 HTTP 검증까지 마쳤다. 운영 기본값은 여전히 무료 faster-whisper이며, `DEEPGRAM_API_KEY`가 설정된 환경에서만 Deepgram이 우선 사용되는 그레이스풀 폴백 구조.
- ElevenLabs/Pinecone은 키 미제공으로 여전히 CONDITIONAL PASS — 유료 키 구매 없이는 완료 불가(별도 DEC-063 본문 참고).
