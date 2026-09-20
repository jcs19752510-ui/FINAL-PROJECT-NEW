"""공용 픽스처. 사용법과 규약은 docs/harness/test-infra.md 참고.

서버는 자동 기동하지 않는다: 실행자가 자기 PID 규칙으로 띄우고 `API_BASE_URL`로 알려준다.
"""
import os
from collections.abc import Iterator

import httpx
import pytest

from tests.support.accounts import API_V1, AccountFactory
from tests.support.cleanup import CleanupError, cleanup_test_data

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=API_BASE_URL, timeout=30.0) as client:
        try:
            client.get(f"{API_V1}/health")
        except httpx.TransportError as exc:
            pytest.fail(
                f"API 서버({API_BASE_URL})에 연결할 수 없습니다: {exc}. "
                "서버를 직접 띄우고 API_BASE_URL을 지정하세요 (docs/harness/test-infra.md).",
                pytrace=False,
            )
        yield client


@pytest.fixture(scope="session")
def account_factory(api: httpx.Client) -> Iterator[AccountFactory]:
    factory = AccountFactory(api)
    yield factory
    created = set(factory.created_emails)
    if not created:
        return
    counts = cleanup_test_data(created)
    if counts["users"] < len(created):
        raise CleanupError(
            f"생성한 계정 {len(created)}개 중 {counts['users']}개만 DB에서 찾았습니다. "
            "API 서버와 DATABASE_URL이 같은 DB를 가리키는지 확인하세요 (테스트 계정이 남았을 수 있음)."
        )
