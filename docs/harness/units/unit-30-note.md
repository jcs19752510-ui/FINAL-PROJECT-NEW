# unit-30 구현 노트 — K8s/클라우드 배포 매니페스트 (참고용, 미적용)

- 작성 에이전트: 본 세션, 작성일: 2026-09-22
- 원 계획서 §2.1/§7.1(K8s 기반 배포/오토스케일링)

## 1. 정직한 스코프 선언

이 세션에는 실제 클라우드 계정도, K8s 클러스터도 없다. 아래 매니페스트는
**`yaml.safe_load()`로 문법만 검증**했을 뿐, 실제 클러스터에 `kubectl apply`한
적이 없다 — "배포가 실제로 동작한다"는 뜻이 아니라 "문법적으로 유효한 참고
설정"이라는 뜻이다.

## 2. 구현 범위

- `backend/deploy/k8s/00-namespace-and-config.yaml`: 네임스페이스 + ConfigMap
- `backend/deploy/k8s/01-secrets.yaml.example`: 시크릿 예시(실값 없음, .gitignore
  대상 실제 파일로 별도 관리 필요)
- `backend/deploy/k8s/02-api-deployment.yaml`: API 서버 Deployment(replicas=2,
  stateless라 수평확장 가능) + Service + HPA(CPU 70% 기준 2~10)
- `backend/deploy/k8s/03-worker-deployment.yaml`: Celery AI 워커 Deployment
  (**replicas=1 고정**) + PVC 2개(media, llm-models)

## 3. 이 매니페스트가 원안의 "500명 동시접속" 목표를 달성하지 못하는 이유
   (재확인, ③ 매트릭스 판정 불변)

API 계층(`02-api-deployment.yaml`)은 stateless라 HPA로 실제 수평 확장이
가능하다 — 이 부분은 진짜 개선이다. 하지만 실제 무거운 작업(STT/LLM/TTS)을
수행하는 Celery 워커는 `llm_engine.py`의 `--pool=solo` 단일 GPU 프로세스
전제(unit-7 실측) 때문에 **replicas를 1보다 늘리면 GPU 메모리 경합이 발생**
한다. 진짜로 늘리려면 GPU 노드 자체를 늘려야 하는데, 그건 이 매니페스트가
아니라 실제 하드웨어/클라우드 예산의 문제다 — ③ 매트릭스가 "500명 동시접속"을
여전히 "개발 불가"로 유지하는 이유가 바로 이것이며, 이 유닛으로 그 판정이
바뀌지 않는다(03-worker-deployment.yaml 주석에 동일 내용 기록).

## 4. 범위 밖

- Ingress/TLS(cert-manager) 매니페스트 — `backend/deploy/nginx.conf.sample`
  (unit-25)과 개념이 중복돼 이번엔 별도로 만들지 않음. 실제 클라우드
  프로바이더(AWS ALB/GCP GCLB 등)마다 Ingress 어노테이션이 달라 일반화하기
  어려움도 있음.
- CI/CD 파이프라인(원안 §2.2 "GitHub Actions") — 별도 유닛 필요.
- 실제 클러스터 적용/부하테스트 — 클러스터 자체가 없어 불가능.
