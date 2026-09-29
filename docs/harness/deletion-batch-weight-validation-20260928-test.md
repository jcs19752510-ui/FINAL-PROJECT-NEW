# 테스트 결과서 — 자동 파기 배치(unit-21) + 루브릭 weight 합계 검증(REQ-014 잔여 부채)

> 사용자 지시 "A. 코드로 실제 해결 가능한 미구현 항목 → 작업 진행해줘"에 따라
> 2026-09-20(DEC-029)부터 미착수 상태로 방치돼 있던 unit-21(자동 파기 배치)과
> unit-13-note.md가 "잔여 부채"로 남긴 weight 합계 검증을 정산한다.

## 0. 작업 중 발생한 환경 사고(투명 공개)

테스트 착수 직후 `backend/.venv`가 통째로 작동을 멈췄다 — 원인 확인 결과
**사용자가 Anaconda를 의도적으로 삭제**했기 때문(`.venv`가 Anaconda의 Python을
기반으로 만들어져 있었음). 사용자 확인("Anaconda 재설치 금지, venv로 버전별
개발 진행 중")에 따라 **독립 실행형 Python 3.12.10**(`C:\Users\mega\AppData\
Local\Programs\Python\Python312`)으로 `backend/.venv`를 새로 만들고
`requirements.txt` 전체를 재설치했다(torch/tensorflow/deepface 포함 약 150개
패키지, 원래 3.13.9였으나 독립 설치본 중 3.13이 없어 가장 가까운 3.12 사용).
재설치 후 `celery`/`sqlalchemy`/`faster-whisper`/`sentence-transformers`/
`torch`/`tensorflow`/`deepface`/`librosa` 전부 import 확인 + 실제 backend
서버·Celery 워커 기동까지 확인해 이 환경 사고가 완전히 복구됐음을 실측으로
확인한 뒤 본 작업을 진행했다. (`llama.cpp` 바이너리·Piper 음성 파일은 pip
패키지가 아니라 `backend/var/`에 독립적으로 존재해 이번 사고와 무관.)

## 1. 개요
- 테스트 대상: `backend/app/worker/deletion_tasks.py`(신규),
  `backend/app/services/celery_app.py`(beat_schedule 추가),
  `backend/app/api/v1/recruiter.py`(`_validate_criteria_weight_sum` 신규)
- 테스트 유형: 06단계(신규 구현 직후 단위 검증) — 실제 DB로 직접 태스크 함수 호출
  + 실HTTP(weight 검증)
- 관련 산출물: `docs/harness/decisions.md` DEC-029(unit-21 최초 배정)/DEC-092(이번),
  `docs/harness/units/unit-13-note.md`(weight 부채 원 출처)
- 테스트 수행자: 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: `delete_requested_data`(biometric_only/full_account 두 target 모두),
  `purge_expired_data`(180일 경과 transcript/report), 루브릭 weight 합계 검증
  (생성/수정 양쪽 엔드포인트), **[2026-09-28 21시, 2차 라운드] Celery beat
  스케줄러의 실제 자동 발화**.
- 제외 범위(1차 라운드 당시): Celery beat가 실제로 "매 시간" 스스로 발화하는 것
  자체는 처음엔 실측하지 않았다 — 그러려면 정시까지 대기해야 하는데 1차 작업
  시점에는 그럴 시간이 없었다. **2차 라운드(같은 날 20:50경 재착수)는 마침 다음
  정시(21:00)까지 10분 남은 시점이라 실제로 대기해 검증했다** — 상세 §4 하단
  "beat 실발화" 항목, §8에 최종 결론. `purge_expired_data`(매일 1회, 새벽 3시)는
  다음 발화까지 수 시간이 걸려 이번에도 직접 관찰하지 못했으나, **동일한 Celery
  beat crontab 스케줄러 엔진이 정확히 예정된 정시에 실제로 발화하는 것을 이미
  실증**했으므로(delete_requested_data로 검증) 매커니즘 자체의 신뢰도는 간접
  확보됐다고 판단한다(스케줄 값만 다를 뿐 동일 엔진).

## 3. 테스트 환경
- DB(`final-project-db`, 5544) + Redis(`final-project-redis`, 6389) 기존 컨테이너
  재사용. backend(`preview_start`, 포트 8000) — weight 검증 실HTTP용으로만 기동,
  삭제/파기 배치는 태스크 함수를 직접 호출(Celery 워커 프로세스 불필요, 단
  워커가 실제로 이 태스크들을 인식하는지는 별도로 기동해 `[tasks]` 목록에
  포함됨을 확인).

## 4. 테스트 케이스 및 결과

### `delete_requested_data`(REQ-030)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-DEL01 | 배치 실행 | dict 반환, 예외 없음 | `{'processed': 1, 'failed': 0}` | PASS |
| TC-DEL02 | biometric_only 요청 completed 전이 | status=completed, completed_at 채워짐 | 확인 | PASS |
| TC-DEL03 | 음성 턴의 prosody_json 실제 삭제 | null로 정리됨 | `prosody_json=None` | PASS |
| TC-DEL04 | full_account 배치 실행(DB 직접 시드 — 이 target을 만드는 API 없음, §2 아님·모듈 docstring 명시) | dict 반환 | `{'processed': 1, 'failed': 0}` | PASS |
| TC-DEL05 | full_account 요청 completed 전이 | status=completed | 확인 | PASS |
| TC-DEL06 | 계정 소프트 삭제 | `users.deleted_at` 채워짐 | 확인(로그인 차단 기존 로직과 연동) | PASS |
| TC-DEL07 | 면접 실제 하드 삭제 | 재조회 시 None | `None` | PASS |
| TC-DEL08 | 동의 실제 하드 삭제 | 재조회 시 None | `None` | PASS |
| TC-DEL10 | 멱등성(이미 completed인 요청 재처리 안 함) | completed_at 불변, processed=0 | 정확히 그대로 | PASS |

### `purge_expired_data`(REQ-033)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-PURGE01 | 배치 실행 | dict 반환 | `{'transcripts_deleted': 1, 'reports_deleted': 1}` | PASS |
| TC-PURGE02 | 181일 전 transcript 실제 삭제 | None | 확인 | PASS |
| TC-PURGE03 | 어제(180일 미만) transcript 보존 | 그대로 유지 | 원문 그대로 확인 | PASS |
| TC-PURGE04 | 181일 전 evaluation_report 실제 삭제 | None | 확인 | PASS |
| TC-PURGE05 | 반환 카운트 실제 삭제 건수와 일치 | 일치 | 일치 | PASS |

### 루브릭 weight 합계 검증(REQ-014)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-W01 | 생성 시 합계 120 | 422 | `422`, "현재 합계: 120" | PASS |
| TC-W02 | 생성 시 합계 70 | 422 | `422`, "현재 합계: 70" | PASS |
| TC-W03 | 생성 시 합계 정확히 100 | 201 | `201` | PASS |
| TC-W04 | 수정 시 합계 50으로 깨뜨림 | 422 | `422` | PASS |
| TC-W05 | 거부된 수정 이후 기존 템플릿 불변 확인 | 원래 값(40/30/30) 그대로 | 그대로 확인(부분 실패 시 데이터 오염 없음) | PASS |
| TC-W06 | 수정 시 합계 정확히 100(50/50) | 200 | `200` | PASS |

### Celery 워커 등록 확인(간접)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-REG01 | 워커 기동 시 `[tasks]` 목록에 신규 태스크 2개 노출 | 포함됨 | `app.worker.deletion_tasks.delete_requested_data`/`purge_expired_data` 둘 다 목록에 출력 확인 | PASS |

### beat 스케줄러 실발화(2026-09-28 21시, 2차 라운드 — DEC-094)
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-BEAT01 | `pending` 요청 1건을 20:49에 시드 → `celery worker`+`celery beat` 두 프로세스를 실제로 띄우고 다음 정시(21:00)까지 실시간 대기 | 이 세션이 태스크를 직접 호출하지 않아도, beat가 21:00:00 근처에 자동으로 `delete_requested_data`를 발행 | 워커 로그: `21:00:06.136 Task ... delete_requested_data[...] received` → `21:00:06.150 biometric_only 정리 1건` → `21:00:06.162 succeeded`. **`.delay()`/함수 직접 호출 없이 스케줄러 자체가 발화시킨 것을 실시간으로 확인** | PASS |
| TC-BEAT02 | 위 처리 결과가 실제로 DB에 반영됐는지 재조회 | status=completed, completed_at 채워짐 | `completed_at=2026-09-28 12:00:06.150706+00:00`(=KST 21:00:06) | PASS |

## 5. 커버리지
- REQ-030: `biometric_only`/`full_account` 두 target 전부, 멱등성까지 커버.
- REQ-033: 경계값(181일 전 vs 어제) 대조로 정확히 180일 기준으로 나뉨을 실증.
- REQ-014: 생성/수정 양쪽, 그리고 "거부된 수정이 기존 데이터를 오염시키지 않는지"
  까지 커버(단순 "422가 뜨는지"보다 한 단계 더 엄격한 검증).
- **[2026-09-28 21시 추가]** beat 스케줄의 실제 "시간 경과에 따른 자동 발화"도
  이제 커버됨(TC-BEAT01/02).
- **커버하지 못한 것(정직하게 명시, 그대로 유지)**: `purge_expired_data`의 실제
  발화 자체(다음 새벽 3시까지 대기 불가, 단 동일 엔진으로 간접 신뢰도 확보),
  `full_account`가 실제 운영 트래픽에서 발생하는 경로(애초에 그런 API가 없음 —
  사용자가 "지금은 만들지 않는다"로 확정, DEC-094).

## 6. 결함(Defect) 목록
- 결함 없음 — 신규 구현 코드가 설계 의도대로 전부 동작.
- (참고, 결함 아님) 테스트 스크립트 자체에서 SQLAlchemy 세션 분리 실수로 인한
  `DetachedInstanceError`/`ObjectDeletedError`가 2차례 발생했으나, 이는 검증용
  스크립트의 세션 관리 실수였고 원인 파악 후 즉시 수정 — 제품 코드(`deletion_
  tasks.py`)의 결함이 아님을 재현으로 확인.

## 7. 테스트 환경 정리(Teardown) — 규칙 K
- 신규 생성 데이터: `delbatch1-*`/`delbatch2-*`/`purgetest-*`(User 3명 + 연관
  Interview/Transcript/EvaluationReport/Consent/DeletionRequest), `weighttest-*`
  (User 1명 + RubricTemplate), **`beatcheck-*`/`u20-responsive-check-*`(2차 라운드,
  User 2명 + 연관 Interview/Transcript/Consent/DeletionRequest)** — 전부 스크립트
  cleanup 단계에서 삭제, 재조회 0건 확인.
- 최초 cleanup 코드에 FK 순서 실수(DeletionRequest를 안 지우고 User부터 삭제
  시도)가 있어 1차 실행이 중간에 실패 — 그 잔여 데이터(6개 계정)를 별도 스윕
  스크립트로 전부 제거하고 재조회 0건 확인한 뒤 재실행. 2차 라운드에서도 동일한
  FK 순서 실수(Consent 누락)가 한 번 더 있어 즉시 수정 후 재실행.
- 기동 프로세스: `preview_start("backend")`(weight 검증용 1차 + 반응형 재검증용
  2차, `preview_stop`으로 종료), Celery 워커(1차 등록 확인용 + 2차 beat 실발화용,
  `TaskStop`으로 종료), **Celery beat(2차, `TaskStop`으로 종료)** — `tasklist`로
  `llama-server.exe`/`python.exe` 잔여 프로세스 0개 확인. `backend/celerybeat-
  schedule*`(beat가 자동 생성하는 로컬 상태파일) 삭제 + `.gitignore`에 패턴 추가.
- **환경 복구 관련**: 구 `.venv`(Anaconda 기반, 작동 불능)는 `backend/.venv`
  위치에 `--clear` 옵션으로 그 자리에서 재생성했다(별도 백업 폴더를 만들지
  않음 — 원본이 어차피 작동 불능이라 되돌릴 이유가 없음, Docker 컨테이너는
  전혀 건드리지 않음).
- 정리 후 `git status`: 코드 변경분(`deletion_tasks.py` 신규, `celery_app.py`/
  `recruiter.py` 수정) + `docs/harness/*` 외 변경 없음. `backend/.venv/`는
  `.gitignore` 대상이라 git status에 나타나지 않음.

## 8. 리스크 및 잔존 이슈
- **[2026-09-28 21시, 2차 라운드에서 해소] beat 스케줄 실발화** — TC-BEAT01/02로
  `delete_requested_data`(매시)의 실제 자동 발화를 실시간으로 확인 완료.
  `purge_expired_data`(매일 새벽 3시)는 다음 발화까지 수 시간이 걸려 이번에도
  직접 관찰하진 못했으나, 동일한 beat crontab 엔진이 정확한 정시에 실제로 동작함을
  이미 실증했으므로 잔존 리스크는 낮다고 판단한다. **다만 `celery beat` 프로세스를
  실제 운영에 상시 기동해두는 것 자체는 여전히 11단계(운영 인수인계) 배포 절차
  항목**이다 — 이번 검증은 "코드/스케줄이 맞게 동작한다"까지이지 "운영에 배포
  완료했다"가 아니다.
- `full_account` 처리 로직은 그 target을 생성하는 API가 아직 없어 실제 운영에서
  호출될 일이 없다 — 향후 "계정 탈퇴" 기능이 추가되면 그때 이 배치가 정말 맞는
  동작인지(특히 email/name 스크럽 여부) 재검토 필요(모듈 docstring에 명시).
- Anaconda 제거로 인한 venv 재구축이 이번 세션에서 발생했다 — 재현 가능한
  독립 Python 환경 구축 절차(정확한 버전·설치 스크립트)가 아직 문서화되지
  않았으므로, 다른 컴퓨터/다른 세션에서 이 프로젝트를 재현하려면 동일한 문제를
  겪을 수 있다(인수인계 문서화 필요, 11단계 후보).

## 9. 결론 및 판정
- [x] PASS — REQ-030/033의 자동 파기 배치, REQ-014의 weight 합계 검증 모두
  실제 DB/HTTP로 구현·검증 완료. unit-21(2026-09-20 배정)이 이번에 최종 정산됨.

## 10. 내부 검증
- 1차(커버리지 확인): 03-system-design.md §6.2 원문("매 시간"/"매일 1회"/
  "biometric_only|full_account")과 구현/테스트를 1:1 대조 — 누락 없음.
- 2차(과신 경계): "태스크 함수가 정상 동작하니 배치 전체가 완료됐다"고 단정하지
  않고, beat 스케줄러의 실제 시간 기반 발화는 검증 범위 밖임을 §2/§8에 명시적으로
  기록했다. 또한 `full_account`가 실제로는 도달 불가능한 코드 경로라는 사실을
  숨기지 않고 모듈 docstring과 이 보고서 양쪽에 명시했다(정직성 원칙).
