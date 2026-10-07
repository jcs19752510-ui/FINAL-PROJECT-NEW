# 04. API 계약서 — AI 모의면접 플랫폼 (재구축용)

| 항목 | 내용 |
|---|---|
| 문서 ID | SPEC-04 |
| 버전 | v1.0 (2026-10-08 KST) |
| 담당 역할 | 백엔드 리드 |
| 기준 시스템 | 현재 `backend/app/api/v1/*`, `schemas/*` 실제 코드 |
| 선행 | 01 문서의 REQ·BR, 03 문서의 T(테이블) |

> **이 문서를 읽는 AI에게**: 이 문서는 **프런트와 백엔드가 공유하는 계약**이다. 경로·필드명·상태 코드를 임의로 바꾸지 않는다. 바꿔야 하면 PM(사용자)에게 알리고 이 문서와 `frontend/lib/api.ts` 타입을 **함께** 고친다. "선택(B)" 표시가 붙은 API는 사용자 승인 없이 만들지 않는다.

---

## 1. 공통 규칙

### 1.1 기본
| 항목 | 값 |
|---|---|
| Base URL | `http://127.0.0.1:8001/api/v1` (WebSocket·정적 파일은 `/api/v1` 없음) |
| 형식 | JSON(UTF-8). 파일 업로드는 `multipart/form-data` |
| 인증 | `Authorization: Bearer <access JWT>`. refresh는 httpOnly 쿠키 `refresh_token`(path `/api/v1/auth`) |
| ID | UUID 문자열 |
| 시각 | ISO 8601, 타임존 포함(UTC) |
| 페이지네이션 | **없음**(전체 목록 반환) |
| 문서 | 자동 생성 `/docs`(Swagger). 운영에서는 비활성 권장(SEC-R09) |

### 1.2 오류 응답 (RFC 7807, 모든 오류 공통)

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "이미 최종 결과가 처리되어 변경할 수 없습니다.",
  "code": "VALIDATION_ERROR"
}
```

### 1.3 오류 코드

| code | HTTP | 의미 |
|---|---|---|
| `AUTH_INVALID_TOKEN` | 401 | 토큰 없음·만료·위조·종류 불일치, 로그인 실패, 삭제된 계정 |
| `AUTH_FORBIDDEN` | 403 | 역할 불일치, 타인 리소스 |
| `NOT_FOUND` | 404 | 대상 없음 |
| `VALIDATION_ERROR` | 422 | 입력 검증 실패. **409(상태 충돌·중복)에도 같은 코드가 쓰인다**(`title`은 `Conflict`) |
| `CONSENT_REQUIRED_NOTICE` | 403 | 사전고지 동의 없이 면접 시작 |
| `CONSENT_REQUIRED_VOICE` | 403 | 음성 동의 없음/철회 |
| `CONSENT_REQUIRED_RESUME` | 403 | 이력서 수집 동의 없음 |
| `RESUME_ALREADY_SUBMITTED` | 409 | 이력서 재제출 |
| `TURN_LIMIT_REACHED` | 409 | 세션당 답변 5회 초과 |
| `REPORT_GENERATION_FAILED` | 409 | 리포트 생성 실패 상태 |
| `SESSION_EXPIRED` | 410 | 세션 만료 |
| `RATE_LIMIT_EXCEEDED` | 429 | 분당 한도 초과 |
| `QUEUE_FULL` | 429(턴) / 503(재채점) | AI 큐 가득 참 |
| `AI_SERVICE_TIMEOUT` | 504 | STT·TTS·비전 등 AI 처리 실패 |

> 422는 `detail`에 Pydantic 오류 목록 문자열이 들어간다. 상태 충돌·중복은 **409 + `VALIDATION_ERROR`** 이다(코드가 같아도 HTTP 상태로 구분).

### 1.4 역할 표기
`공개` 인증 없음 / `candidate` / `recruiter` / `admin` / `소유자` = 해당 면접의 지원자 본인.

### 1.5 동시성·멱등성 표기
- **1회**: 같은 대상에 한 번만 성공(행 잠금 또는 유니크 제약).
- **멱등**: 같은 요청을 여러 번 해도 결과가 같다.

---

## 2. 권한 매트릭스

| API | 공개 | candidate | recruiter | admin | 비고 |
|---|:-:|:-:|:-:|:-:|---|
| API-01 가입 | ✅ | ✅ | ✅ | ✅ | role 고정 candidate |
| API-02 로그인, API-03 갱신 | ✅ | | | | |
| API-04 내 정보 | | ✅ | ✅ | ✅ | |
| API-05 채용담당자 추가 | | ❌403 | ✅ | ❌403 | |
| API-10~14 면접 생성·목록·상세·시작·종료 | | ✅소유자 | ❌403(생성·목록) | | 상세·시작·종료도 소유자만 |
| API-15 재개, API-16 턴, API-17 대화 | | ✅소유자 | ❌ | | |
| API-18 리포트 조회 | | ✅소유자 | ✅전체 | | |
| API-19 리포트 재시도 | | ✅소유자 | ❌ | | |
| API-20~23 코드·화이트보드 | | ✅소유자 | ❌ | | |
| API-30~34 동의·삭제 | | ✅본인 | ✅본인 | ✅본인 | 본인 데이터만 |
| API-40~41 이력서 제출·상태 | | ✅(제출은 candidate만) | | | |
| API-50~54 리포트 목록·상세·최종판단 | | ❌ | ✅ | | |
| API-55~60 이력서 검토 | | ❌ | ✅ | | |
| API-61~64 루브릭 | | ❌ | ✅ | | 템플릿은 본인 것·기본만 |
| API-70 운영 모니터링 | | ❌ | ❌ | ✅ | |
| API-71 헬스 | ✅ | | | | |

---

## 3. REST 엔드포인트

### 3.1 인증

#### API-01 `POST /auth/register` — REQ-001
- 요청: `{ "email": "a@b.com", "password": "8~128자", "name": "1~100자", "role": "candidate" }` (`role` 생략 가능, **`candidate` 외 값은 422**)
- 응답 **201**: `{ "id", "email", "name", "role": "candidate", "created_at" }`
- 오류: 409 `VALIDATION_ERROR`(이미 가입된 이메일), 422
- 규칙: SEC-01, SEC-04, BR-01·02

#### API-02 `POST /auth/login`
- 요청: `{ "email", "password"(1~128자) }`
- 응답 **200**: `{ "access_token", "token_type": "bearer", "user": UserOut }` + `Set-Cookie: refresh_token`(HttpOnly, SameSite=Lax, Secure=운영, Path=/api/v1/auth, 7일)
- 오류: 401 `AUTH_INVALID_TOKEN`(**이메일 불일치와 비밀번호 불일치를 같은 메시지**로) — SEC-03

#### API-03 `POST /auth/refresh`
- 요청: 본문 없음(쿠키 사용). 응답 **200**: `{ "access_token", "token_type": "bearer" }`. refresh 토큰은 재발급하지 않는다.
- 오류: 401(쿠키 없음·만료·종류 불일치·삭제된 사용자)

#### API-04 `GET /auth/me` → 200 `UserOut`. 401.

#### API-05 `POST /recruiter/recruiters` — REQ-047
- 요청: `{ "email", "password"(8~128), "name"(1~100) }` (role 필드 **없음**, 항상 recruiter)
- 응답 **201** `UserOut`. 오류: 401, 403(recruiter 아님), 409, 422
- 규칙: SEC-04

### 3.2 면접 세션

공통 객체
```json
InterviewOut = { "id","candidate_id","recruiter_id","rubric_template_id","status","report_status","started_at","ended_at","overall_score","created_at" }
InterviewListItemOut = { "id","status","report_status","started_at","ended_at","overall_score","created_at","resumable" }
InterviewDetailOut = InterviewOut + { "resumable": true|false }   // live·paused일 때만 true
```

#### API-10 `POST /interviews` — REQ-002
- 요청 본문 없음. 응답 **201** `InterviewOut`(`status=scheduled`, `report_status=none`, `rubric_template_id`=시스템 기본)
- 오류: 401, 403(candidate 아님)

#### API-11 `GET /interviews` — 내 면접 목록
- 응답 200 `InterviewListItemOut[]`. 정렬: `coalesce(started_at, created_at)` 내림차순(동률 id 내림차순). 24시간 넘은 live·paused는 이 시점에 `expired`로 확정. 오류: 401, 403

#### API-12 `GET /interviews/{id}` → 200 `InterviewDetailOut`. 오류: 401, 403(타인), 404

#### API-13 `POST /interviews/{id}/start` — REQ-002, REQ-032
- 응답 **202**: `{ "job_id": "...", "message": "AI가 첫 질문을 준비 중입니다", "interview": InterviewOut }`
- 오류: 409(scheduled 아님), 403 `CONSENT_REQUIRED_NOTICE`(`ai_interview_notice` 동의 없음)
- 부수효과: `live` + `started_at`, 첫 질문 작업 큐 투입. **`biometric_voice`는 여기서 검사하지 않는다.**

#### API-14 `POST /interviews/{id}/end`
- 응답 **202**: `{ "job_id", "interview": InterviewOut }`. 오류: 409(live 아님)
- 부수효과: `completed`, `ended_at`, `report_status=queued`, 리포트 작업 투입

#### API-15 `POST /interviews/{id}/resume` — REQ-013
- ※ 현행 화면(S-05)은 이 API를 호출하지 않음(백엔드만 존재). 새 프로젝트에서 재개 UI를 만들 때 사용(OPEN-13).
- 응답 200 `InterviewDetailOut`(paused면 live로 전환, live면 그대로 — 멱등). 오류: 409(live·paused 아님), 410 `SESSION_EXPIRED`

#### API-16 `POST /interviews/{id}/turns` — REQ-003/004/005
`Content-Type`으로 분기한다.

**텍스트**: `application/json` `{ "text": "1~4000자" }`
**음성**: `multipart/form-data`, 파일 필드 이름 **`audio`**

- 응답 **202** `{ "job_id": "..." }`
- 처리 순서(고정, 현행 코드): 소유자 확인 → 세션 만료(410) → live 아님(409) → 지원자 답변 5회(409) → (음성) 동의 재조회(403) → 레이트리밋 → 큐 상한 → (음성) 파일 읽기·크기 확인·STT → (텍스트) 인젝션 의심 패턴 **로그만** → 저장 → 작업 투입
- 오류:

| HTTP / code | 조건 |
|---|---|
| 401 / 403 `AUTH_FORBIDDEN` / 404 | 인증, 타인 세션, 없음 |
| 409 `VALIDATION_ERROR` | live 아님 |
| 409 `TURN_LIMIT_REACHED` | 지원자 답변 5회 도달 |
| 410 `SESSION_EXPIRED` | 24시간 경과 |
| 403 `CONSENT_REQUIRED_VOICE` | 음성 동의 없음·철회(**오디오를 읽지 않음**) |
| 429 `RATE_LIMIT_EXCEEDED` | 사용자당 분당 10회 초과 |
| 429 `QUEUE_FULL` | 큐 50 이상 |
| 422 | 빈 텍스트·4000자 초과, `audio` 필드 없음·빈 파일·25MB 초과, multipart 형식 오류 |
| 504 `AI_SERVICE_TIMEOUT` | STT 실패(디코딩 불가 등), 아무것도 저장하지 않음 |

- 저장: `transcripts`(speaker=user, input_mode=text|voice, `audio_ref=null`), `turn_index`는 서버가 채번(유니크 제약 + 최대 5회 재시도)

#### API-17 `GET /interviews/{id}/transcripts` → 200 `TranscriptOut[]`(`turn_index` 오름차순)
```json
{ "id","interview_id","question_id","turn_index","speaker":"ai|user","input_mode":"text|voice","content_text","audio_ref","prosody","created_at" }
```

#### API-18 `GET /interviews/{id}/report` — REQ-009/010/012
- **200** `ReportOut`:
```json
{
  "interview_id": "...", "report_status": "ready", "overall_score": "4.0",
  "technical_score": 4, "communication_score": 4, "cultural_fit_score": 4,
  "overall_recommendation": "recommend|neutral|not_recommend|null",
  "pass_fail_recommendation": "pass|fail|borderline|null",
  "star": { "situation": "", "task": "", "action": "", "result": "" },
  "summary_text": null, "details": {},
  "rubric": {
    "template_id": "...", "name": "기본 루브릭",
    "criteria": [ { "name": "기술 이해도", "weight": 40, "description": "", "score": 4, "evidence": "", "answer_refs": [5] } ],
    "answers": [ { "no": 5, "excerpt": "120자 이내" } ]
  },
  "disclaimer": "이 결과는 참고용 AI 평가이며, 최종 채용 결정은 인간이 내립니다."
}
```
- **202** `{ "status": "processing" }`(queued)
- **409** `REPORT_GENERATION_FAILED`(failed), **409** `VALIDATION_ERROR`(면접 미종료, `report_status=none`)
- 접근: 소유자 지원자 또는 recruiter. 타인 지원자는 403.
- 규칙: `summary_text`에 시스템 프롬프트 유출 마커가 있으면 **고정 안내 문구로 대체**해서 응답(SEC-25). `answers`는 `answer_refs`로 참조된 답변만, 원문이 삭제됐으면 빠진다. `rubric=null`이면 구버전·폴백.

#### API-19 `POST /interviews/{id}/report/regenerate`
- **소유자만**. `failed`일 때만. 응답 **202** `{ "job_id" }`. 오류: 409

### 3.3 코드·화이트보드

#### API-20 `POST /interviews/{id}/code-submissions` — 201
- 요청: `{ "language": "python|javascript|typescript|java|c|cpp|csharp|go|rust|sql|plaintext", "content": "0~20000자" }`(language는 소문자 정규화, 목록 밖은 422)
- 응답 201 `{ "id","interview_id","language","content","submitted_at" }`. 매번 새 행(append-only). 소유자만.

#### API-21 `GET /interviews/{id}/code-submissions?language=python` → 200 배열(최신순). `language` 선택.

#### API-22 `PUT /interviews/{id}/whiteboard` — 200
- 요청: `{ "strokes": [ { "points": [ { "x": 0.0, "y": 0.0 } ], "color": "#000", "width": 0<w<=64 } ] }` — strokes ≤ 2000, 스트로크당 points 1~5000
- 응답 `{ "id","interview_id","strokes":[...],"created_at" }`. 매번 새 행.

#### API-23 `GET /interviews/{id}/whiteboard` → 200 최신 1건 또는 **200 `null`**(저장한 적 없음, 404 아님)

### 3.4 동의·개인정보

#### API-30 `POST /consents` — 201
- 요청: `{ "consent_type": "biometric_voice|ai_interview_notice|resume_submission" }`
- 응답: `{ "id","consent_type","granted_at","revoked_at":null,"lawful_basis":"consent" }`. 같은 종류를 또 등록해도 새 행이 생긴다(이력). 접속 IP는 암호화 저장.

#### API-31 `POST /consents/{id}/revoke` — 200
- 오류: 404, 403(타인 동의), 409(이미 철회). **철회 후 다음 음성 제출부터 즉시 403.**

#### API-32 `GET /users/me/consents` → 200 `ConsentOut[]`(동의일 내림차순)

#### API-33 `DELETE /users/me/biometric-data` — **202**
- 응답 `DeletionRequestOut`: `{ "id","target":"biometric_only","status":"pending","requested_at","completed_at":null }`. 처리는 매 시간 배치.

#### API-34 `GET /users/me/deletion-requests` → 200 `DeletionRequestOut[]`

### 3.5 이력서 (지원자)

#### API-40 `POST /resumes` — REQ-040, **201**
- `multipart/form-data`, 파일 필드 **`file`**
- 응답 `MyResumeStatusOut`: `{ "id","status":"pending","original_filename","decision_note":null,"interview_schedule_note":null,"submitted_at","reviewed_at":null }`
- 검사 순서: candidate만(403) → `resume_submission` 동의(403 `CONSENT_REQUIRED_RESUME`) → 이미 제출함(409 `RESUME_ALREADY_SUBMITTED`) → multipart 형식 → 파일 존재 → `Content-Type`이 `application/pdf` → 비어 있지 않음 → 10MB 이하(위반은 422)
- 저장: 서버가 만든 `{uuid}.pdf` 이름으로 `var/resumes/`, DB에는 경로만. (**현재 파일 내용(매직바이트)은 검사하지 않음** — SEC-R02)

#### API-41 `GET /users/me/resume-status` → 200 `MyResumeStatusOut` 또는 **200 `null`**(기록 없음). 감사 필드(`reviewed_by`, `notified_at`)는 노출하지 않는다.

### 3.6 채용담당자 — 리포트와 최종 합격/불합격

#### API-50 `GET /recruiter/reports` — REQ-011/046
- 응답 200 배열(최신 생성순):
```json
{ "interview_id","candidate_name","candidate_email","status","report_status","started_at","ended_at","overall_score" }
```
- 면접 상태 필터는 **화면에서만** 한다(쿼리 파라미터 없음). 오류: 401, 403(recruiter 아님)

#### API-51 `GET /recruiter/reports/{interview_id}` — 200
- API-50 항목 + `report_available`, `message`, `technical_score`, `communication_score`, `cultural_fit_score`, `overall_recommendation`, `pass_fail_recommendation`, `star`, `summary_text`, `details`, `rubric`, 그리고 **최종 판단 4필드**:
```json
{ "final_decision": "accepted|rejected|null", "final_decision_note": null, "final_decided_at": null, "final_notified_at": null }
```
- `report_available=false`이면 점수·STAR는 `null`이고 `message`로 상태를 안내("아직 리포트 생성이 요청되지 않았습니다." / "리포트를 생성하는 중입니다…" / "리포트 생성에 실패했습니다…" / "리포트가 준비되었습니다."). 오류: 404

#### API-52 `PATCH /recruiter/reports/{interview_id}/final-decision` — REQ-045
- 요청: `{ "status": "accepted|rejected", "decision_note": "1~500자(앞뒤 공백 제거 후 검사)" }`
- 응답 **200** `FinalDecisionOut`:
```json
{ "interview_id","final_decision":"accepted","final_decision_note":"...","final_decided_at":"...","final_notified_at":"... 또는 null" }
```
- 오류:

| HTTP | 조건 |
|---|---|
| 401 / 403 | 인증 / recruiter 아님 |
| 404 | 면접 없음 |
| 409 | 면접이 `completed`가 아님 |
| 409 | **이미 최종 결과가 처리됨**("이미 최종 결과가 처리되어 변경할 수 없습니다.") |
| 422 | 빈 문구·공백 문구·501자 이상, `status`가 accepted/rejected 아님 |

- 규칙: **1회**. 행 잠금으로 동시 2건이면 200 1건 + 409 1건, 메일은 1회. 저장·커밋 후 메일 발송, 성공 시에만 `final_notified_at` 기록. 메일 미설정·실패여도 응답은 200.

#### API-53 `GET /recruiter/reports/{interview_id}/final-notification-draft` — 200
- 응답 `{ "to_email","subject","body" }`. 처리 전이면 409. recruiter만.

#### API-54 `POST /recruiter/reports/{interview_id}/final-mark-notified` — 200 `FinalDecisionOut`
- 처리 전 409. 이미 시각이 있으면 **덮어쓰지 않음(멱등)**.

### 3.7 채용담당자 — 이력서 검토

공통
```json
RecruiterResumeListItemOut = { "id","candidate_id","candidate_name","candidate_email","status","original_filename","submitted_at","reviewed_at","notified_at" }
RecruiterResumeDetailOut = ListItem + { "content_type","file_size_bytes","decision_note","interview_schedule_note" }
```

#### API-55 `GET /recruiter/resumes` → 200 목록(제출 최신순)
#### API-56 `GET /recruiter/resumes/{id}` → 200 상세. 404
#### API-57 `GET /recruiter/resumes/{id}/file` → 200 PDF(`FileResponse`, 원본 파일명). recruiter만.

#### API-58 `PATCH /recruiter/resumes/{id}/decision` — REQ-042/043/044
- 요청: `{ "status": "accepted|rejected", "decision_note": "선택", "interview_schedule_note": "선택(합격 시)" }`
- `status`가 `pending`이면 **422**. 응답 200 `RecruiterResumeDetailOut`(`notified_at` 포함).
- 재판단 허용(상태를 바꾸면 메일을 다시 보낸다). 판단 저장 → 커밋 → 메일 → 성공 시 `notified_at`.
- 화면 규칙: `interview_schedule_note`는 `"YYYY-MM-DD(요일) HH:MM 보충문구"` 형식으로 조합해 보낸다.
- 주의: 서버는 `decision_note` 길이를 제한하지 않는다(재구축 시 500자 제한 권장, SEC-R08).

#### API-59 `GET /recruiter/resumes/{id}/notification-draft` → 200 `{ to_email, subject, body }`. 판단 전 409.
#### API-60 `POST /recruiter/resumes/{id}/mark-notified` → 200 상세. 판단 전 409. (이 API는 호출할 때마다 시각을 **갱신**한다)

### 3.8 루브릭 (OPEN-04: 유지할 때만)

```json
RubricTemplateOut = { "id","recruiter_id":null|uuid,"name","criteria":[{"name":"1~100자","weight":0~100,"description":"≤500자"}],"is_system_default":true|false,"created_at" }
```
#### API-61 `GET /recruiter/rubric-templates` → 내 템플릿 + 시스템 기본(최신순)
#### API-62 `POST /recruiter/rubric-templates` — 201. 요청 `{ "name": "1~100자", "criteria": [1~20개] }`. **가중치 합이 100이 아니면 422**
#### API-63 `PATCH /recruiter/rubric-templates/{id}` — 본인 소유만(기본 템플릿·타인 템플릿은 403). 합 100 검사
#### API-64 `PUT /recruiter/interviews/{id}/rubric-template` — 요청 `{ "rubric_template_id" }` 응답 `{ "interview_id","rubric_template_id","job_id" }`
- 같은 템플릿 200(변경 없음), 채점 중 409, `ready`·`failed`면 교체 + 재채점 작업 투입(큐 50 이상이면 **503**). **현재 이 API를 쓰는 화면은 없다.**

### 3.9 운영

#### API-70 `GET /ops/health` — admin만
```json
{ "queue_length": 0, "gpu_memory_used_bytes": 0, "error_rate": 0.0, "active_sessions": 3, "checked_at": "...", "notes": { "queue_length": "…" } }
```
`active_sessions`(= live 세션 수)만 실측이고 나머지는 0이며 `notes`에 이유를 적는다(L-25).

#### API-71 `GET /health` → `{ "status": "ok" }` (공개)

---

## 4. 선택(B) 엔드포인트 — 사용자 승인 시에만

| API | 요청 | 응답·규칙 |
|---|---|---|
| API-80 `POST /interviews/{id}/turns/preview` | multipart `audio`(짧은 조각) | 200 `{ "text": "" }`. 저장·작업 투입 없음, live + 음성 동의 필요, 분당 20회, 빈 인식은 빈 문자열 |
| API-81 `POST /interviews/{id}/tts-preview` | `{ "text": 1~500자 }` | 200 `{ "audio_url" }`. 진단용. 504 |
| API-82 `POST /interviews/{id}/code-submissions/execute` | `{ language(python/javascript), content(1~20000) }` | 200 `{ stdout, stderr, exit_code, timed_out }`. 소유자만, 분당 5회, 언어 밖 422. **9중 격리 필수(SEC-27)** |
| API-83 `POST /interviews/{id}/whiteboard/analyze` | 없음 | 200 `{ "analysis", "disclaimer", "model" }`. 저장된 캔버스 없으면 404, 실패 504 |
| API-84 `POST /interviews/{id}/webcam-emotion` | multipart `image`(8MB 이하) | 200 `{ dominant_emotion, scores, face_confidence, disclaimer }`. **채용 평가 연결 금지, 저장 금지** |
| API-85 `GET /users/me/data-export` | — | 200 `{ exported_at, user_id, email, name, account_created_at, consents[], deletion_requests[], interviews[] }`(대화 원문 제외) |

---

## 5. WebSocket·정적 파일

### WS-01 `/ws/interviews/{interview_id}?token=<access JWT>`
- 연결 거부: 토큰 무효·타인 세션·삭제된 사용자는 서버가 **accept 전에 close(1008)** 호출(클라이언트에는 핸드셰이크 실패/1008로 보임).
- **서버 → 클라이언트** (`job_id`로 어떤 제출에 대한 이벤트인지 구분):

```json
{"type":"stage_update","job_id":"...","stage":"llm|tts"}
{"type":"turn_result","job_id":"...","transcript":"내 발화 텍스트 또는 null","ai_text":"...","audio_url":"/media/tts/xxxx.wav 또는 null","control":{"action":"next_question|end_interview|switch_to_coding|none"},"user_transcript_id":"uuid 또는 null","ai_transcript_id":"uuid"}
{"type":"report_ready","job_id":"...","interview_id":"..."}
{"type":"error","job_id":"...","code":"AI_SERVICE_TIMEOUT|REPORT_GENERATION_FAILED","message":"..."}
```
(`stage`는 현재 `llm`, `tts`만 발행한다. 첫 질문은 `user_transcript_id=null`. `queue_status`는 허용 목록에는 있으나 **발행 코드가 없다**.)
- **클라이언트 → 서버**: `{"type":"cancel_queue_wait","job_id":"..."}` 하나만 허용, **받아도 아무 동작도 하지 않는다**. 그 외 메시지·JSON이 아닌 프레임은 **무시**(연결 유지).
- 중계 이벤트는 `type`이 화이트리스트(`queue_status`,`stage_update`,`turn_result`,`report_ready`,`error`)에 있는 JSON 객체만 전달한다.
- 클라이언트는 WS가 끊겨도 `GET /interviews/{id}/transcripts`·`GET /interviews/{id}`·`GET /interviews/{id}/report` 폴링으로 복구한다(첫 질문은 3초 간격 최대 15회).

### WS-02 `/ws/interviews/{id}/signaling` — 선택(B)
SDP/ICE 중계만(`offer|answer|ice-candidate|bye`), 방당 2피어.

### MEDIA-01 `GET /media/tts/{uuid}.wav` — 인증 없는 정적 파일(추측 불가 UUID 이름). SEC-33.

---

## 6. LLM 구조화 출력 계약

### 6.1 턴 출력(`TurnLLMOutput`)
```json
{
  "speak_text": "공백만 아닌 1자 이상(앞뒤 공백 제거)",
  "control": "next_question|end_interview|switch_to_coding|none",
  "technical_accuracy": 1,
  "communication_clarity": 1,
  "key_observations": [],
  "rubric_match": {}
}
```
필수: `speak_text`. `control` 밖 값은 검증 실패(재시도 1회 → 폴백).

### 6.2 리포트 출력(`ReportLLMOutput`)
```json
{
  "star": { "situation": "", "task": "", "action": "", "result": "" },
  "technical_accuracy": 1, "communication_clarity": 1, "cultural_fit": 1,
  "overall_recommendation": "recommend|neutral|not_recommend",
  "pass_fail_recommendation": "pass|fail|borderline",
  "details": {},
  "criteria_scores": [ { "criterion": "", "score": 1, "evidence": "", "answer_refs": [1] } ]
}
```
- `star`가 문자열로 오면 `situation`에 담아 보정, `details`가 객체가 아니면 `{"note": ...}`로 감싼다.
- `criteria_scores`가 배열이 아니면 빈 배열. 서버 검증 규칙은 03 문서 6.3.
- 이 출력에는 **"합격/불합격 확정" 필드를 만들지 않는다**(`pass_fail_recommendation`은 참고 의견).

---

## 7. 안내 메일 계약

> 발송은 `smtplib`(Gmail SMTP, STARTTLS 587, 타임아웃 10초), `text/plain; charset=utf-8`. **수신자는 항상 DB의 지원자 이메일**이다. 아래 줄바꿈은 그대로 유지한다.

### 7.1 서류 합격
- 제목: `[채용 안내] 서류 전형 합격 및 모의면접 안내`
```text
{이름}님, 안녕하세요.

서류 전형에 합격하셨습니다. 축하드립니다.

면접 일정 안내: {interview_schedule_note}     ← 있을 때만, 앞뒤 빈 줄
{decision_note}                                 ← 있을 때만, 앞뒤 빈 줄

모의면접 사이트에 이 계정(이메일/비밀번호)으로 로그인해주세요.
로그인 후 합격 여부를 다시 확인하실 수 있으며, 이어서 모의면접을 진행해주세요.
```

### 7.2 서류 불합격
- 제목: `[채용 안내] 서류 전형 결과 안내`
```text
{이름}님, 안녕하세요.

아쉽게도 이번 서류 전형에서는 합격하지 못하셨습니다.

{decision_note}                                 ← 있을 때만

지원해주셔서 감사합니다.
```

### 7.3 최종 합격
- 제목: `[채용 안내] 최종 합격 안내`
```text
{이름}님, 안녕하세요.

모든 전형을 마치고 최종 합격하셨습니다. 진심으로 축하드립니다.

{final_decision_note}

모의면접 사이트에 이 계정(이메일/비밀번호)으로 로그인해 결과를 다시 확인하실 수 있습니다.
```

### 7.4 최종 불합격
- 제목: `[채용 안내] 최종 결과 안내`
```text
{이름}님, 안녕하세요.

아쉽게도 이번 채용에서는 최종 합격하지 못하셨습니다.

{final_decision_note}

지원해주셔서 진심으로 감사드립니다.
```

### 7.5 발송 규칙
1. 판단을 **먼저 커밋**한 뒤 발송한다.
2. 발송이 성공했을 때만 `notified_at` / `final_notified_at`을 기록한다.
3. `GMAIL_ADDRESS`·`GMAIL_APP_PASSWORD`가 없거나 SMTP가 실패하면 판단은 유지하고 시각은 비운다 → 화면의 "발송 완료로 표시"(API-60/54)가 수동 폴백.
4. 미리보기 API(API-59/53)는 **발송 본문과 같은 함수**로 만든다(문구가 어긋나지 않게).

---

## 8. 화면 ↔ API 매핑

| 화면 | 호출하는 API |
|---|---|
| S-01 로그인 | API-02, 04 |
| S-02 홈 | API-04, 11, 41 |
| S-03 면접 생성 | API-10 |
| S-04 사전고지 | API-12, 30, 13 |
| S-05 면접장 | API-12, 16, 17, 14, 20, 21, 22, 23, 30, WS-01 |
| S-06 리포트 | API-18, 19, WS-01(report_ready) |
| S-07 마이페이지 | API-04, 31, 32, 33, 34 |
| S-09 리포트 목록 | API-04, 50 |
| S-10 리포트 상세 | API-04, 51, 52, 53, 54 |
| S-11 이력서 목록 | API-04, 55 |
| S-12 이력서 상세 | API-04, 56, 57, 58, 59, 60 |
| S-14 채용담당자 추가 | API-04, 05 |
| S-15 루브릭 | API-61, 62, 63 |
| S-16 운영 | API-70 |
| S-22 가입(3002) | API-01 |
| S-23 로그인(3002) | API-02 |
| S-24 이력서(3002) | API-04, 41, 30(동의), 40 |

---

## 9. 계약 변경 규칙
1. 필드 이름·타입·상태 코드를 바꾸면 이 문서, 백엔드 스키마, `lib/api.ts` 타입, 테스트를 **한 작업 안에서 함께** 고친다.
2. 필드 **추가**는 선택(옵션) 필드로만 하고 기존 클라이언트를 깨지 않는다.
3. 새 LLM 출력 필드를 추가하면 05 문서 SEC-23(새니타이즈 목록)에 먼저 올린다.
4. 새 API에는 권한 등급(2절)과 SEC 규칙을 먼저 정한다.

---

## 10. 변경 이력

| 일시 | 버전 | 내용 |
|---|---|---|
| 2026-10-08 | v1.0 | 현재 코드의 라우터·스키마를 직접 대조해 재구축용으로 최초 작성(최종 합격/불합격 API 포함) |
