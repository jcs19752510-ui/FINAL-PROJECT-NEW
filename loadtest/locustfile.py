"""Locust 부하 테스트 스크립트 (원본 계획서 6.1, 2026-10-12).

**읽기 전용 시나리오**(로그인 → 내 정보 → 내 면접 목록 / 채용담당자는 리포트 목록)만 포함한다. 면접 진행(LLM·STT)
부하는 GPU 용량과 직결되고 데이터를 생성하므로 이 스크립트에 넣지 않았다 —
의미 있는 용량 측정은 별도 시나리오가 필요하다.

사용법:
    pip install locust
    # 계정 파일(email,password 한 줄씩) 또는 단일 계정 중 하나
    set LOCUST_ACCOUNTS_CSV=accounts.csv        (또는 LOCUST_EMAIL / LOCUST_PASSWORD)
    set LOCUST_ROLE=candidate                    (candidate | recruiter, 기본 candidate)
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8001 --headless -u 50 -r 5 -t 2m

주의: 운영 데이터가 있는 서버에 걸지 않는다. 테스트용 계정으로만 실행한다.
"""

import csv
import itertools
import os
import threading

from locust import HttpUser, between, task

_lock = threading.Lock()
_accounts: list[tuple[str, str]] | None = None
_counter = itertools.count()


def _load_accounts() -> list[tuple[str, str]]:
    global _accounts
    with _lock:
        if _accounts is None:
            path = os.environ.get("LOCUST_ACCOUNTS_CSV")
            if path:
                with open(path, encoding="utf-8", newline="") as fh:
                    _accounts = [
                        (row[0].strip(), row[1].strip()) for row in csv.reader(fh) if len(row) >= 2 and row[0].strip()
                    ]
            else:
                email, password = os.environ.get("LOCUST_EMAIL"), os.environ.get("LOCUST_PASSWORD")
                _accounts = [(email, password)] if email and password else []
        return _accounts


class _AuthedUser(HttpUser):
    abstract = True
    wait_time = between(1, 3)
    token: str | None = None

    def on_start(self) -> None:
        accounts = _load_accounts()
        if not accounts:
            raise RuntimeError("LOCUST_ACCOUNTS_CSV 또는 LOCUST_EMAIL/LOCUST_PASSWORD 환경변수가 필요합니다.")
        email, password = accounts[next(_counter) % len(accounts)]  # 계정을 돌려가며 사용
        with self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="POST /auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200 or "access_token" not in (resp.json() if resp.content else {}):
                resp.failure(f"로그인 실패: HTTP {resp.status_code}")
                return
            self.token = resp.json()["access_token"]

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


class CandidateUser(_AuthedUser):
    """지원자: 내 정보 조회, 내 면접 목록."""

    weight = 1 if os.environ.get("LOCUST_ROLE", "candidate") == "candidate" else 0

    @task(3)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", headers=self._auth, name="GET /auth/me")

    @task(2)
    def my_interviews(self) -> None:
        self.client.get("/api/v1/interviews", headers=self._auth, name="GET /interviews")


class RecruiterUser(_AuthedUser):
    """채용담당자: 내 정보 조회, 지원자 리포트 목록."""

    weight = 1 if os.environ.get("LOCUST_ROLE", "candidate") == "recruiter" else 0

    @task(2)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", headers=self._auth, name="GET /auth/me")

    @task(3)
    def reports(self) -> None:
        self.client.get("/api/v1/recruiter/reports", headers=self._auth, name="GET /recruiter/reports")
