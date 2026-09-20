"""테스트 인프라 스모크: 서버 헬스, 계정 팩토리, 정리 헬퍼가 실제로 동작하는지만 확인한다."""
import httpx
import pytest

from tests.support.accounts import (
    API_V1,
    AccountFactory,
    Role,
    is_marker_email,
    login_account,
    new_marker_email,
    register_account,
)
from tests.support.cleanup import UnsafeCleanupTarget, cleanup_test_data


def test_health(api: httpx.Client) -> None:
    resp = api.get(f"{API_V1}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("role", ["candidate", "recruiter"])
def test_register_login_me_roundtrip(api: httpx.Client, account_factory: AccountFactory, role: Role) -> None:
    account = account_factory.create(role)
    assert is_marker_email(account.email)

    me = api.get(f"{API_V1}/auth/me", headers=account.auth_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == account.email
    assert body["role"] == role
    assert body["id"] == account.user_id

    assert api.get(f"{API_V1}/auth/me").status_code == 401


def test_marker_email_format() -> None:
    email = new_marker_email()
    assert is_marker_email(email)
    assert email != new_marker_email()
    assert not is_marker_email("real.user@example.com")
    assert not is_marker_email("harness_test_x@harness-test.example")
    assert not is_marker_email(f"x{email}")


def test_cleanup_refuses_non_marker_email() -> None:
    with pytest.raises(UnsafeCleanupTarget):
        cleanup_test_data(["real.user@example.com"])
    with pytest.raises(UnsafeCleanupTarget):
        cleanup_test_data([new_marker_email(), "admin@example.com"])


def test_cleanup_deletes_only_scoped_marker_account(
    api: httpx.Client, account_factory: AccountFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    keep = account_factory.create("candidate")
    target = register_account(api, "candidate")
    try:
        target = login_account(api, target)

        dry = cleanup_test_data([target.email], dry_run=True)
        assert dry["users"] == 1
        assert login_account(api, target).access_token  # dry-run은 지우지 않는다

        done = cleanup_test_data([target.email])
        assert done["users"] == 1
        assert "삭제 예정: " in capsys.readouterr().out  # 삭제 전 대상 건수 출력

        relogin = api.post(f"{API_V1}/auth/login", json={"email": target.email, "password": target.password})
        assert relogin.status_code == 401
        assert cleanup_test_data([target.email])["users"] == 0  # 멱등
    finally:
        cleanup_test_data([target.email])

    assert api.get(f"{API_V1}/auth/me", headers=keep.auth_headers).status_code == 200
