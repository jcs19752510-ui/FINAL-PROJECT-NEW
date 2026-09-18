# 요구사항 추적 매트릭스 (Requirements Traceability Matrix)

> 2단계(`02-planning.md`)에서 생성. 이후 3단계(설계 매핑), 5·6단계(구현/단위테스트), 7·8단계(통합/전체테스트)를 거치며 갱신한다. 8단계 완료 조건은 모든 행의 "구현"~"전체테스트" 컬럼이 채워지는 것이다(제외 항목은 사유 명시로 커버리지 인정).

## 기능 요구사항 (In-Scope)

| REQ-ID | 요구사항/기능 (기획서 §, 우선순위) | 설계 매핑 (설계서 §) | 작업 단위 (unit-n) | 구현 상태 | 단위테스트 (unit-n-test) | 통합테스트 (feature-x) | 전체테스트(08) | 비고 |
|---|---|---|---|---|---|---|---|---|
| REQ-001 | [Must] 회원가입/로그인/역할 구분(지원자/채용담당자) (02-planning §4.2) | 03-system-design §1.2(Auth/User API), §3(USERS 테이블), §4.2(auth 엔드포인트), §6.1(JWT/RBAC) | unit-1 | 구현 완료(05단계, `backend/app/api/v1/auth.py` + `frontend/app/{register,login}/page.tsx`) | PASS(06단계, L1 경량판 — 정상경로 2케이스: 회원가입/로그인+본인조회 06단계가 직접 재현, `docs/harness/units/unit-1-test.md`) | | | Feature A. **Speed Track L1 확정**(DEC-003) — 06 경량판 완료. **L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요**(에러경로/이메일중복/role422/비밀번호422/로그인401/프론트 화면흐름은 06이 아직 독립 재현하지 않음, 5단계 자체기록만 존재). 상세는 `docs/harness/units/unit-1-note.md`, `unit-1-test.md` 참고 |
| REQ-002 | [Must] 면접 세션 생성·시작·종료·상태관리 (02-planning §4.2) | 03-system-design §1.2(Session API), §3(INTERVIEWS 상태머신 + `report_status` 필드, v2 재작업), §4.2(`/interviews` POST/**GET(신규, 내 목록 조회, DEC-024 갭1)**, `/start`(v2: `ai_interview_notice`만 검사 + `opening_question` job 자동 enqueue, DEC-023/갭8), `/end`, `/report/regenerate`(신규, 갭5)) | unit-2 | 구현 완료(05단계, `backend/app/api/v1/interviews.py` — 생성/시작/종료 3개 엔드포인트만. `backend/app/models/interview.py`, `backend/app/models/consent.py`(최소 스키마), `backend/app/services/job_queue.py`(큐/워커 경계 인터페이스, 정당한 순서상 스텁), Alembic `fdd74cee7615`) | PASS(06단계, L1 경량판 — 정상경로 2케이스: TC-001 세션생성+recruiter역할게이트(403), TC-002 동의게이트(403)→동의부여→start(202,live)→end(202,completed,report_status=queued), 06단계가 직접 새 서버 프로세스(포트 8021)로 재현, `docs/harness/units/unit-2-test.md`) | | | Feature B. **Speed Track L1 확정**(DEC-003) — 06 경량판 완료. **L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요**(중복시작/종료 409, 수평권한상승 403, 인증없음 401, 존재하지않는 id 404는 06이 아직 독립 재현하지 않음, 5단계 자체기록만 존재). **범위 편차(unit-2-note.md §2 참고)**: (1) `GET /interviews`(목록 조회)는 이번 지시 범위에서 제외되어 미구현 — [C-03] 지원자 홈이 의존하므로 후속 작업 단위 필요. (2) `POST /interviews/{id}/report/regenerate`, `/resume`은 각각 unit-10/unit-3 범위, 미구현. (3) `INTERVIEWS.rubric_template_id`는 FK 제약 없이 nullable 컬럼만 생성(unit-13이 `RUBRIC_TEMPLATES` 생성 시 FK 추가 필요). (4) `CONSENTS`는 `/start`의 DEC-023 게이트에 필요한 최소 스키마만 선행 생성, 동의관리 REST API 전체는 unit-14/15 책임. (5) `opening_question`/`report_generation` job enqueue는 실제 Celery/Redis 큐가 아직 없어 `job_id` 발급 스텁(unit-4/7/10이 내부 구현 예정) — API 응답 계약(202 {job_id})과 상태 전이는 실제로 구현·검증됨. 상세는 `docs/harness/units/unit-2-note.md`, `unit-2-test.md` 참고 |
| REQ-003 | [Must] 텍스트 기반 질문-응답(채팅형 UI) (02-planning §4.2) | 03-system-design §1.1(WebSocket Gateway), §4.3(`text_turn` 메시지) | unit-4 | Not Started | | | | Feature C |
| REQ-004 | [Must] 음성 기반 질문-응답(턴제, 실시간 스트리밍 아님) (02-planning §4.2) | 03-system-design §1.3(큐/워커 순차처리), §2.2(WebRTC 제거·HTTP업로드로 대체, DEC-015), §4.2(`/turns`), §4.3(`voice_turn_start/end`) | unit-5 | Not Started | | | | Feature C. REQ-F-002 축소판 |
| REQ-005 | [Must] 로컬 STT 파이프라인(Whisper 경량 모델, 턴제 배치) (02-planning §6.1) | 03-system-design §2.3(faster-whisper small/CPU/int8 선정, 실측 RTF 0.22), §5.1(지연 실측치) | unit-5 | Not Started | | | | Feature C |
| REQ-006 | [Must] 로컬 오픈소스 TTS(AI 면접관 음성 합성) (02-planning §6.1) | 03-system-design §2.5(Piper 선정, 실측 RTF 0.056, GPL-3.0 라이선스 리스크 및 격리 대응) | unit-6 | Not Started | | | | Feature C. 라이선스 주의 — GPL-3.0 신규 확인(DEC-017), 법무검토 필요 |
| REQ-007 | [Must] LLM 적응형 꼬리질문 생성 + RAG 질문은행 검색 (02-planning §4.2) | 03-system-design §2.4(Qwen2.5-Instruct GGUF 선정, DEC-016), §3(QUESTIONS.embedding/pgvector), §4.4(구조화 출력 JSON 계약) | unit-7 | Not Started | | | | Feature C |
| REQ-008 | [Must] 라이브 코딩 환경 — 에디터+제출/저장(실행 없음) (02-planning §4.2) | 03-system-design §2.1(Monaco Editor), §3(CODE_SUBMISSIONS 테이블), §4.2(`/code-submissions` POST/**GET(신규, 세션 재개 시 재조회, DEC-024 갭3)**), §6.3(제출값 새니타이즈, REQ-036과 동일기준) | unit-9 | Not Started | | | | Feature D. REQ-F-004 축소판 |
| REQ-009 | [Must] STAR 구조 기반 상세 피드백 리포트 자동 생성 (02-planning §4.2) | 03-system-design §3(EVALUATION_REPORTS.**star_json**(situation/task/action/result, v2 재작업 DEC-024 갭7) + `summary_text` 폴백), §4.2(`/report`, `/report/regenerate`), §4.4(리포트 생성 전용 구조화 출력 계약, 신규) | unit-10 | Not Started | | | | Feature E |
| REQ-010 | [Must] 루브릭 기반 채용 적합도 스코어링(1~5점) (02-planning §4.2) | 03-system-design §3(EVALUATION_REPORTS.technical/communication/cultural_fit_score), §4.2(`/report`) | unit-11 | Not Started | | | | Feature E |
| REQ-011 | [Should] 채용담당자용 리포트 열람 대시보드(최소 뷰어) (02-planning §4.2) | 03-system-design §1.2(Recruiter API), §4.2(`/recruiter/reports`), §6.1(RBAC — recruiter는 담당 지원자만 열람) | unit-12 | Not Started | | | | Feature F |
| REQ-012 | [Must] 평가 근거 노출(루브릭 적용 근거 최소 표시) (02-planning §4.2) | 03-system-design §3(EVALUATION_REPORTS.details_json), §4.2(`/report`), §6.3(details_json도 REQ-036 새니타이즈 대상, v2 재작업 명시) | unit-11 | Not Started | | | | Feature E. REQ-N-004(공정성/설명가능성) 최소 대응 |
| REQ-013 | [Must] 세션 중단/재접속 처리 규칙 (02-planning §4.2) | 03-system-design §3(INTERVIEWS.status=paused/expired), §4.2(`/resume`, **`/code-submissions` GET, `/whiteboard` GET — 신규, 재개 시 코드/화이트보드 복원, DEC-024 갭3·4**), §5.4(job idempotency), §5.3(가용성) | unit-3 | 구현 완료(05단계, `backend/app/api/v1/interviews.py` — `GET /interviews/{id}`(신규, 상세조회+`resumable` 파생필드), `POST /interviews/{id}/resume`. DEC-026로 SESSION_EXPIRED 임계값 24h 확정 및 `paused` 전이 트리거 메커니즘은 범위외로 보류) | PASS 대기(06단계, L1 경량판) | | | Feature B. **Speed Track L1(DEC-003)** — 06 경량 테스트 대기, 07은 L1 부채로 08 착수 전 정산 필요. 도메인 특이케이스(01단계 §6). **범위 편차(unit-3-note.md §2 참고)**: (1) `GET /interviews/{id}/code-submissions`, `GET /interviews/{id}/whiteboard`는 CODE_SUBMISSIONS/WHITEBOARD_SNAPSHOTS 모델이 아직 없어 각각 unit-9/unit-17 책임으로 남김(미구현). (2) turn_index 등 실제 대화 콘텐츠 복원은 TRANSCRIPTS 모델이 없는 unit-4 이후 범위. (3) `paused` 상태로의 자동 전이(하트비트/WS 접속끊김 감지)는 신설하지 않음(DEC-026) — 현재는 재접속해도 `live`로 남아있는 세션을 그대로 조회/재개하는 경로만 지원 |
| REQ-014 | [Should] 채용담당자 질문지/루브릭 최소 커스터마이징 (02-planning §4.2) | 03-system-design §3(RUBRIC_TEMPLATES), §4.2(`/recruiter/rubric-templates`) | unit-13 | Not Started | | | | Feature F |
| REQ-015 | [Should] 웹캠 영상 프리뷰(AI 분석 없음) (02-planning §4.2) | 03-system-design §1.2(클라이언트 전용, 서버 미전송), §6.2(수집최소화 원칙과 직결) | unit-16 | Not Started | | | | Feature H |
| REQ-016 | [Should] 운영자 기본 모니터링(세션 수, 에러 로그) (02-planning §4.2) | 03-system-design §4.2(`/ops/health`), §7.2(Prometheus/Grafana 지표) | unit-18 | Not Started | | | | Feature H |
| REQ-017 | [Could] 시스템 설계 화이트보드 캔버스(AI 자동분석 없음) (02-planning §4.2) | 03-system-design §3(WHITEBOARD_SNAPSHOTS), §4.2(`/whiteboard` PUT/**GET(신규, 세션 재개 시 재조회, DEC-024 갭4)**) | unit-17 | Not Started | | | | Feature H. REQ-F-005 축소판 |

## 규제 대응 요구사항 (규칙 I — 개인정보보호법 생체정보·자동화된 결정)

| REQ-ID | 요구사항/기능 | 설계 매핑 | 작업 단위 | 구현 상태 | 단위테스트 | 통합테스트 | 전체테스트(08) | 비고 |
|---|---|---|---|---|---|---|---|---|
| REQ-029 | [Must] 생체정보(음성) 수집 전 별도 명시적 동의 절차 + 미동의시 이용 제한 안내 | **[v2 재작업, DEC-023/024]** 03-system-design §3(CONSENTS 테이블), §4.2(`POST /consents`, `GET /users/me/consents`(신규, 갭1), **`POST /interviews/{id}/turns` 음성 제출 시 매 요청 실시간 재검사**), §6.2(동의 게이트를 `/start`에서 `/turns`(음성 제출 시점)로 이동 — 텍스트 전용 이용자는 더 이상 이 동의를 강제받지 않음, 미동의/철회 시 403 CONSENT_REQUIRED_VOICE, job 자체를 큐에 넣지 않고 오디오도 저장하지 않음) | unit-14 | Not Started | | | | 개인정보 보호법 시행령 제18조·제23조 대응(01단계 §5.1). **재작업 사유(DEC-022 갭6)**: v1은 텍스트 전용 이용자에게도 세션 시작 시 강제해 자유로운 동의 원칙과 긴장 관계였음 |
| REQ-030 | [Must] 동의 철회 및 수집 데이터 즉시 삭제 요청 기능 | 03-system-design §3(DELETION_REQUESTS 테이블), §4.2(`/consents/{id}/revoke`, `DELETE /users/me/biometric-data`, **`GET /users/me/deletion-requests`(신규, 처리상태 조회, DEC-024 갭2)**), §6.2(SLA 24h 배치 파기잡 + **철회 시 다음 음성 제출부터 서버가 실제로 차단하는 실시간 재검사 메커니즘 명시, DEC-023 — 단순 플래그 저장이 아님**) | unit-14 | Not Started | | | | 위와 동일 근거 |
| REQ-031 | [Must] "AI는 보조 도구, 최종 결정은 인간이 함" 원칙 명시 + 자동 최종판정 기능 미제공 | 03-system-design §3(EVALUATION_REPORTS.overall_recommendation을 recommend/neutral/not_recommend 3등급 enum으로 제한, "합격/불합격 확정" 필드 스키마 자체에 미생성 — §3.2 원계획서 대비 변경점), §6.2(모든 리포트 응답에 고정 문구) | unit-15 | Not Started | | | | 개인정보 보호법 제37조의2(자동화된 결정 거부권·설명요구권, 2024-03-15 시행) 대응. 9단계에서 미반영 시 Critical 결함 |
| REQ-032 | [Must] AI 면접 진행/평가 사실 사전 고지 화면 | 03-system-design §4.2(`GET /interviews/{id}/pre-notice`, `POST /interviews/{id}/start`(v2: `ai_interview_notice` 동의를 유일한 세션 시작 게이트로 검사, DEC-023)), §6.2(세션 시작 버튼은 고지 확인 체크박스 선행 — 04단계 UI 반영 필요 사항으로 명시 인수인계) | unit-15 | Not Started | | | | 채용절차법 개정 동향(고지의무 강화) 대응 |
| REQ-033 | [Must] 데이터 보관기간 정책 + 자동/요청 삭제 라이프사이클 | 03-system-design §6.2(음성원본=STT완료 즉시삭제, transcript/리포트=기본180일 임시값·법률자문 확인필요), §7.4(Celery beat 배치 파기잡) | unit-15 | Not Started | | | | 개인정보 보호법 일반 원칙 대응 |
| REQ-034 | [Must] 실제 외부 공개 전 법률/컴플라이언스 자문 권고 문구 고정 노출 | 03-system-design §4.2(`GET /legal/disclaimer`), §6.2(모든 리포트 화면 하단 노출), §8(전 트레이드오프 항목의 "확인 필요" 표기 방식 자체가 이 원칙의 실천) | unit-15 | Not Started | | | | 규칙 I-4 — 에이전트가 법적 판단을 대신하지 않음을 명시. 1차 구현은 unit-15(운영 관리자 화면), 11단계 인수인계 문서(`11-ops-handoff-runbook.md`)에도 동일 문구를 재수록해 이중 노출한다(제거 대상 아님) |

## AI/LLM 안전장치 요구사항 (규칙 J)

| REQ-ID | 요구사항/기능 | 설계 매핑 | 작업 단위 | 구현 상태 | 단위테스트 | 통합테스트 | 전체테스트(08) | 비고 |
|---|---|---|---|---|---|---|---|---|
| REQ-035 | [Must] 프롬프트 인젝션 방어(사용자 입력이 시스템 프롬프트를 덮어쓰거나 우회 못하게 하는 입력 경계 설계) | 03-system-design §6.3(role 분리 + 1차 패턴 필터링, 잔여리스크 명시), §4.4(구조화 출력 강제) | unit-8 | Not Started | | | | 09단계 인젝션 취약점 점검과 동일하게 Critical 취급 |
| REQ-036 | [Must] LLM 출력 새니타이즈(채팅/리포트 렌더링 시 HTML 이스케이프, XSS 방지) | 03-system-design §6.3(서버측 HTML escape+화이트리스트 마크다운, 클라이언트 DOMPurify 2중방어. **[v2 재작업, DEC-024 갭7] 대상 필드 목록에 `EVALUATION_REPORTS.star_json`/`summary_text`/`details_json` 명시적 포함** — v1은 `speak_text`/`key_observations`만 명시해 리포트 필드가 누락되어 있었음) | unit-8 | Not Started | | | | 코드 제출값(REQ-008)도 동일 기준 적용 |
| REQ-037 | [Must] LLM 도구/함수 호출 최소 권한(시스템 제어 신호는 화이트리스트 명령만 허용) | 03-system-design §6.3(function-calling 권한 미부여, RAG는 읽기전용 컨텍스트 주입), §4.3(`control` enum 화이트리스트) | unit-8 | Not Started | | | | 원안 5.1.2 "시스템 제어 신호" 확장 금지 |
| REQ-038 | [Must] 요청 빈도/리소스 사용량 레이트리밋(세션/사용자당 LLM 호출 제한 + GPU 4GB 제약 고려한 동시 추론 큐잉) | 03-system-design §1.3(큐 최대길이 50, 단일 GPU워커 직렬화), §6.3(세션당/일일 상한) | unit-8 | Not Started | | | | 02-planning §6.1, §7 리스크 2 연결 |
| REQ-039 | [Must] 시스템 프롬프트 유출 방지(유출 시도 탐지·거부) | 03-system-design §6.3(출력 후처리 n-gram 유사도 검사+AUDIT_LOGS 기록, 시스템프롬프트 자체 거절지침 포함) | unit-8 | Not Started | | | | |

## Out-of-Scope (사유 포함)

| REQ-ID | 기능 | 원 계획서 근거 | 제외 사유 |
|---|---|---|---|
| REQ-018 | 표정 기반 감정분석(DeepFace 7종 실시간 분석) | REQ-F-002 | GPU 4GB 제약, EU AI Act 감정인식 금지 관행 논의, 국내 생체인식정보 리스크, L1 트랙 부적합 (02-planning §4.3) |
| REQ-019 | 음성 운율(Prosody) 분석 | 원안 5.3.2 | REQ-018과 동일 사유 |
| REQ-020 | 실시간 자동 끼어들기(VAD 기반 turn-taking) | REQ-F-003 | 구현 난이도, 하드웨어 제약 — REQ-004(턴제)로 대체 |
| REQ-021 | 화이트보드 AI 비전 자동분석(GPT-4V 등) | REQ-F-005 | 오픈소스 대안의 로컬 구동 검증 안 됨, 예산 없음. 캔버스(REQ-017)는 유지 |
| REQ-022 | 코드 실제 실행/자동채점(샌드박스) | REQ-F-004 | 임의 코드 실행 보안위험, L1 일정상 샌드박스 구축 여력 없음 |
| REQ-023 | 동시접속 500명, K8s 오토스케일링 | REQ-N-002 | DEC-006으로 50명/단일 인스턴스 대체 확정 |
| REQ-024 | Oracle DB | 원안 6.1 | DEC-004로 PostgreSQL 대체 확정 |
| REQ-025 | Pinecone 벡터DB | 원안 4.1 | DEC-005로 pgvector/Chroma 대체 확정 |
| REQ-026 | 유료 API(OpenAI/Deepgram/Hume AI/ElevenLabs) | 원안 4.1, 5.1~5.2 | DEC-005로 오픈소스 대체 확정 |
| REQ-027 | 클라우드 배포(AWS/GCP/EKS) | 원안 4.1 | DEC-007로 로컬서버 확정 |
| REQ-028 | GDPR/CCPA 완전 대응 | REQ-N-003 | 국내(한국어/한국 채용시장) 대상 가정(A5) — 한국 개인정보보호법 대응(REQ-029~033)으로 대체 |

## 작성 규칙 (템플릿 원문)
- REQ-ID는 2단계에서 기획서의 기능 범위(In-Scope) 항목마다 하나씩 부여했다. 이후 단계에서 새 ID를 임의로 추가하지 않고, 새 요구사항이 필요하면 규칙 A에 따라 질문하거나 규칙 F(피드백 루프)로 상위 단계를 수정한다.
- Out-of-Scope 항목은 매트릭스에 포함하되 상태를 표기하지 않고(해당 없음) 사유만 명시해, "빠뜨린 것"과 "의도적으로 뺀 것"을 구분한다.
- 8단계에서 이 매트릭스를 검토해 커버리지 100%를 확인하지 못하면 PASS 판정할 수 없다.
- **L1 부채 관련**: 각 In-Scope REQ-ID가 속한 feature가 Speed Track L1로 진행되면(기본값, DEC-003), 07(통합테스트) 컬럼은 "L1 부채 — 08 착수 전 정산 필요"로 표기하고 5단계 착수 시점에 채운다(현재 02단계에서는 아직 트랙 확정 전이므로 비고에만 예고 표기).
