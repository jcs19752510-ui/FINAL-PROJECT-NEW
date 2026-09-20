"""고유 테스트 계정 팩토리 (docs/harness/test-infra.md).

모든 테스트 계정 이메일은 `harness_test_<uuid4>@harness-test.example` 형식이다. 이 형식이
DB 정리 헬퍼(`cleanup.py`)가 지울 수 있는 유일한 대상이므로, 테스트는 반드시 이 모듈로만
계정을 만든다.
"""
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Literal

import httpx

API_V1 = "/api/v1"

# 앱의 `EmailStr`(email-validator)가 RFC 6761 예약 TLD `.invalid`를 거부하므로(가입 422 실측)
# 같은 RFC 2606 예약 TLD 중 허용되는 `.example`을 쓴다. 실메일이 절대 존재할 수 없는 도메인이라
# 실사용자 계정과 충돌하지 않는다는 성질은 동일하다. 변경은 이 상수 한 곳에서만 한다.
MARKER_DOMAIN = "harness-test.example"
_UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
MARKER_EMAIL_RE = re.compile(rf"^harness_test_{_UUID_RE}@{re.escape(MARKER_DOMAIN)}$")
# SQL LIKE 패턴. `_`는 LIKE 와일드카드이므로 이스케이프(ESCAPE '\')한다.
MARKER_EMAIL_LIKE = rf"harness\_test\_%@{MARKER_DOMAIN}"

Role = Literal["candidate", "recruiter"]


class HarnessApiError(RuntimeError):
    """테스트 준비 단계에서 API가 예상 밖 응답을 준 경우 (테스트 실패가 아니라 인프라 오류)."""


@dataclass(frozen=True)
class HarnessAccount:
    email: str
    password: str
    role: Role
    name: str
    user_id: str
    access_token: str | None = None

    @property
    def auth_headers(self) -> dict[str, str]:
        if self.access_token is None:
            raise HarnessApiError("로그인하지 않은 계정입니다 (login_account 또는 create_account(login=True) 사용).")
        return {"Authorization": f"Bearer {self.access_token}"}


def new_marker_email() -> str:
    return f"harness_test_{uuid.uuid4()}@{MARKER_DOMAIN}"


def is_marker_email(email: str) -> bool:
    return MARKER_EMAIL_RE.fullmatch(email) is not None


def register_account(api: httpx.Client, role: Role = "candidate") -> HarnessAccount:
    email = new_marker_email()
    password = secrets.token_urlsafe(16)
    name = f"harness-{role}"
    resp = api.post(
        f"{API_V1}/auth/register",
        json={"email": email, "password": password, "name": name, "role": role},
    )
    if resp.status_code != 201:
        raise HarnessApiError(f"회원가입 실패: {resp.status_code} {resp.text}")
    return HarnessAccount(email=email, password=password, role=role, name=name, user_id=resp.json()["id"])


def login_account(api: httpx.Client, account: HarnessAccount) -> HarnessAccount:
    resp = api.post(f"{API_V1}/auth/login", json={"email": account.email, "password": account.password})
    # 세션 공유 클라이언트의 쿠키 저장소에 refresh 쿠키가 쌓이면 계정 간 상태가 섞이므로 비운다.
    # 테스트는 Bearer 토큰만 사용한다.
    api.cookies.clear()
    if resp.status_code != 200:
        raise HarnessApiError(f"로그인 실패: {resp.status_code} {resp.text}")
    return HarnessAccount(
        email=account.email,
        password=account.password,
        role=account.role,
        name=account.name,
        user_id=account.user_id,
        access_token=resp.json()["access_token"],
    )


class AccountFactory:
    """세션 동안 만든 계정 이메일을 추적해 종료 시 정리 대상으로 넘긴다."""

    def __init__(self, api: httpx.Client) -> None:
        self._api = api
        self.created_emails: list[str] = []

    def create(self, role: Role = "candidate", *, login: bool = True) -> HarnessAccount:
        account = register_account(self._api, role)
        self.created_emails.append(account.email)
        return login_account(self._api, account) if login else account
