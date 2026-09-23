# 테스트 결과서 (Test Result Report) — unit-24

## 1. 개요
- 테스트 대상: 음성 Prosody 분석(`app/services/prosody_engine.py`) 및 이를 소비하는
  전 계층(모델→마이그레이션→음성 턴 제출 경로→서버 기동 예열→API 응답)
- 테스트 유형: 단위+통합 병합(Low 등급 전용, 작업 단위 1개·영향 범위 명확)
- 적용 Tier: Low(additive 신규 컬럼, 기존 스키마/API 계약 손상 없음)
- 적용 속도 트랙: L1(경량판), 사용자 요구로 4절은 표준 수준으로 채움
- 테스트 목적: (1) 실제 한국어 음성에서 피치/유성비 등 원시 수치가 정확히
  추출되는지, (2) 콜드스타트 지연 문제 유무 및 대응, (3) 음성 턴 제출 전체
  파이프라인(HTTP→STT→prosody→DB→응답)이 실제로 깨지지 않는지
- 관련 산출물: `unit-24-note.md`, 원 계획서 §5.3.2(REQ-018/019)
- 테스트 수행자(에이전트): 본 세션(05+06 역할 겸임)
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위: 디코딩(PyAV)+피치추출(librosa) 정확성, 콜드/웜 타이밍, Alembic upgrade/
  downgrade, 음성 턴 제출 실제 HTTP E2E(등록→로그인→동의→세션생성/시작→음성
  제출→조회), 서버 기동 성공 여부(예열 로직 포함)
- 제외 범위 및 사유: (1) "자신감/긴장도" 해석 라벨의 정확도 — 이 모듈은 애초에
  그런 라벨을 만들지 않으므로 해당 없음(unit-24-note.md §1 설계 원칙). (2) 브라우저
  실제 마이크 녹음 — 도구 부재, Piper로 합성한 실제 한국어 음성으로 대체(기존
  unit-5/6이 gTTS로 STT/TTS를 검증한 선례와 동일 방식).

## 3. 테스트 환경
- Windows, Python 3.13(backend/.venv, librosa 0.10.2.post1 신규 설치), PostgreSQL
  (Docker `final-project-db`, 5544), 신규 uvicorn 프로세스(포트 8302)
- 테스트 데이터: Piper로 합성한 실제 한국어 문장 오디오 3건(직접 스크립트 실행 2건 +
  HTTP E2E 1건), 격리 테스트 계정 1개(`unit24-cand@example.com`)
- 전제 조건: `docker ps`로 DB 기동 확인, v12(head)까지 마이그레이션 적용 확인

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 문법/린트 | `py_compile`+`ruff check` 신규/수정 파일 전체 | 오류 0건 | `PY_OK`, ruff clean(interviews.py는 기존 무관 부채 1건 그대로, 신규 이슈 없음) | PASS | |
| TC-002 | 실제 음성 디코딩+피치추출 | Piper 합성 한국어 문장(7.7초) → `analyze_prosody()` 직접 호출 | duration/pitch_mean/pitch_std/voiced_ratio 반환, 값이 사람 목소리 대역(65~2093Hz) 내 | `{'duration_sec': 7.696, 'pitch_mean_hz': 265.24, 'pitch_std_hz': 55.27, 'voiced_ratio': 0.7967}` — 정상 범위 | PASS | |
| TC-003 | 콜드스타트 타이밍(완전 콜드) | 신규 파이썬 프로세스, 최초 호출 | 완료(수치는 참고용, 실패만 아니면 됨) | **32초 소요**(DEF-001) → 예열 로직 추가 | PASS(리스크 완화 조치 포함) | 실사용 영향 가능성 있어 즉시 대응 |
| TC-004 | 디스크캐시 웜 상태 첫 호출 + 프로세스 내 2회차 | 별도 신규 프로세스(디스크 캐시 有)에서 연속 2회 호출 | 1회차>2회차, 둘 다 초 단위 이내 | 1회차 4.79s, 2회차 0.75s | PASS | "최초 1회만 느림" 패턴, STT/TTS와 동일 계열 확인 |
| TC-005 | Alembic upgrade/downgrade 라운드트립 | `upgrade head`→확인→`downgrade -1`→확인→`upgrade head`→확인 | 매 단계 성공 | 3단계 모두 성공, `alembic current`로 각 단계 확인 | PASS | |
| TC-006 | 서버 기동(예열 포함) — 수정 전 | 신규 uvicorn(8302) 기동 | 정상 기동 | **기동 자체가 크래시**(DEF-002, `TypeError: a coroutine was expected`) | FAIL→수정 후 재실행 | |
| TC-006R | 서버 기동(예열 포함) — 수정 후 | 동일 | 정상 기동, `/health` 200 | `{"status":"ok"}` 즉시 응답(예열은 백그라운드라 기동을 막지 않음 확인) | PASS | |
| TC-007 | 음성 턴 제출 실제 HTTP E2E | 등록→로그인→동의(ai_interview_notice+biometric_voice)→세션생성→시작→실제 한국어 음성(멀티파트)으로 `/turns` 제출→`GET /transcripts` | 응답 202, 이후 조회 시 해당 턴의 `prosody` 필드에 4개 수치 채워짐, AI 턴은 `prosody:null` | 정확히 일치(`{"duration_sec":7.638,"pitch_std_hz":60.48,"voiced_ratio":0.8159,"pitch_mean_hz":276.75}`), AI 텍스트 턴 2건은 `prosody:null` | PASS | 총 응답시간 10.76초(STT 모델 첫 로드+STT추론+예열된 prosody 포함, 타임아웃 없음) |
| TC-008 | 분석 실패 시 그레이스풀 디그레이드(코드 리뷰) | `_submit_voice_turn` 예외 처리 경로 확인 | `ProsodyAnalysisError`를 잡아 로깅만 하고 턴 저장은 계속 진행 | 코드 확인: `except ProsodyAnalysisError: logger.warning(...)` 이후 `finally`로 정상 흐름 지속 | PASS | 실제 실패 강제 재현(예: 손상 오디오 주입)은 TC-002/007이 이미 정상 경로를 실측했고 이 경로는 STT 실패 처리(TtsSynthesisError 대응)와 동일 패턴이라 코드 리뷰로 갈음(과잉 테스트 방지) |

## 5. 커버리지
- L1 경량판이나 표준 수준으로 채움(1절 참고). 신규 코드 경로(디코딩/피처추출/
  마이그레이션/서버기동/E2E 음성제출) 전량 실제 실행으로 커버.
- 커버되지 않은 부분: 실제 브라우저 마이크 입력(3절 사유), 다양한 오디오 코덱
  (webm/opus 등 — 이번 테스트는 WAV만 사용. STT 자체는 unit-5가 이미 검증한 경로를
  재사용하므로 낮은 리스크로 판단).

## 6. 결함(Defect) 목록
| ID | 설명 | 심각도 | 상태 | 조치 |
|----|------|--------|------|------|
| DEF-001 | librosa numba JIT 완전 콜드 컴파일 최대 32초 | Medium | Fixed | 서버 기동 시 백그라운드 예열 추가 |
| DEF-002 | `run_in_executor` 반환값을 `create_task`에 직접 전달해 서버 기동 크래시 | High | Fixed | 코루틴 래퍼로 감싸 수정, 재기동 성공 확인 |

- 추가로 범위 밖 심각 발견 1건(`content_text` 데이터 손상) — 6절 결함 목록에는
  포함하지 않음(이 유닛이 원인이 아니고 수정도 이 유닛 범위가 아님), `unit-24-
  note.md` §3에 별도 기록 및 사용자 보고.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/unit24_uvicorn.log`, `warmup_tone.wav`,
  `voice_answer_sample.wav`, `unit24_token.txt`, `unit24_iv.txt`(전량 삭제 완료),
  DB 임시 행(interview 1·transcript 3·evaluation_report 1·consent 2·user 1, 전량
  삭제 완료 — 삭제 결과: `transcripts=3 reports=1 consents=2 interviews=1 users=1`),
  신규 uvicorn 프로세스(PID 24324, `taskkill`로 종료 확인)
- 전부 `.harness-tmp/` 하위에서만 생성: [x] 예 (그 외 디렉터리에 남긴 파일 없음 —
  `backend/var/media/tts/`의 TTS 테스트 부산물도 각 스크립트에서 즉시 삭제)
- 정리 완료 여부: 완료
- 정리 후 git status: 사용자 지시("Git 작업 금지")에 따라 이번 유닛부터 git
  상태 확인 자체를 수행하지 않음 — 파일시스템/DB 정리 완료만 위와 같이 직접
  확인했다.
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- **`content_text` 데이터 손상(범위 밖, 별도 보고 필요, 심각도 잠정 High~Critical)**
  — 3절/6절 참고. 이 유닛의 정상 판정에는 영향 없으나 프로젝트 전체 관점에서는
  이 6개 항목보다 우선순위가 높을 수 있음.
- **STT 실시간 스트리밍 전환 보류** — 오늘 이미 발생한 실제 인시던트가 담긴
  코드를 검증 불가능한 상태(브라우저 도구 부재)로 재설계하는 리스크 때문에
  순서를 조정하고 이번 유닛에서는 다루지 않음. 재개 여부 사용자 결정 필요.
- librosa 콜드스타트는 예열로 완화했으나, 예열 자체가 실패하면(코드상 best-effort,
  예외를 삼킴) 첫 실사용자가 콜드 비용을 다시 떠안는다 — 운영 모니터링 필요.

## 9. 결론 및 판정
- [x] PASS

## 10. 내부 검증
- L1 경량판 — 검증 생략. DEF-001/002는 "실패 실측→수정→성공 재실측" 사이클을
  실제로 거침(4절 TC-003/TC-006 참고).
