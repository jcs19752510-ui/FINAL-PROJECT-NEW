"""Locust 스크립트 자체를 검증하기 위한 가짜 API 서버(실제 백엔드 불필요). 테스트 전용 — 운영에 쓰지 않는다.
실행: python loadtest/stub_server.py <포트> [fail]   ('fail'이면 로그인 이후 모든 조회가 500을 돌려준다)"""

import sys

import uvicorn
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()
FAIL = len(sys.argv) > 2 and sys.argv[2] == "fail"


@app.post("/api/v1/auth/login")
def login(payload: dict):
    if payload.get("password") != "pw":
        raise HTTPException(status_code=401, detail="bad credentials")
    return {"access_token": "tok-" + payload["email"], "token_type": "bearer", "user": {"id": "1"}}


def _check(authorization: str | None) -> None:
    if FAIL:
        raise HTTPException(status_code=500, detail="boom")
    if not authorization or not authorization.startswith("Bearer tok-"):
        raise HTTPException(status_code=401, detail="no token")


@app.get("/api/v1/auth/me")
def me(authorization: str | None = Header(default=None)):
    _check(authorization)
    return {"id": "1"}


@app.get("/api/v1/interviews")
def interviews(authorization: str | None = Header(default=None)):
    _check(authorization)
    return []


@app.get("/api/v1/recruiter/reports")
def reports(authorization: str | None = Header(default=None)):
    _check(authorization)
    return []


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
