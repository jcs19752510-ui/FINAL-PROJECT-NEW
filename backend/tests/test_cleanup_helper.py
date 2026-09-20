"""정리 헬퍼의 실패/stray 경로 단위 테스트. DB·서버 없이 가짜 연결로 실행된다 (실계정을 만들지 않는다)."""
import uuid

import psycopg
import pytest

from tests.support import cleanup
from tests.support.accounts import new_marker_email

STRAY_EMAIL = "harness_test_0123456789ab@harness-test.example"  # 마커형이지만 UUID 형식이 아님


class _FakeCursor:
    def __init__(self, user_rows: list[tuple[uuid.UUID, str]], log: list[tuple[str, object]]) -> None:
        self._user_rows = user_rows
        self._log = log
        self._last = ""
        self.rowcount = 0

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self._log.append((sql, params))
        self._last = sql

    def fetchall(self) -> list[tuple[uuid.UUID, str]]:
        return self._user_rows if "FROM users WHERE email" in self._last else []

    def fetchone(self) -> tuple[int]:
        return (0,)


class _FakeConn:
    def __init__(self, user_rows: list[tuple[uuid.UUID, str]], log: list[tuple[str, object]]) -> None:
        self._user_rows = user_rows
        self._log = log

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._user_rows, self._log)


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secretpw@127.0.0.1:1/x")
    state: dict[str, object] = {"rows": [], "log": [], "kwargs": {}}

    def connect(url: str, **kwargs: object) -> _FakeConn:
        state["kwargs"] = kwargs
        return _FakeConn(state["rows"], state["log"])  # type: ignore[arg-type]

    monkeypatch.setattr(cleanup.psycopg, "connect", connect)
    return state


def _deletes(state: dict[str, object]) -> list[str]:
    return [sql for sql, _ in state["log"] if sql.lstrip().upper().startswith("DELETE")]  # type: ignore[union-attr]


def test_connect_uses_timeout_and_wraps_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secretpw@127.0.0.1:1/x")
    seen: dict[str, object] = {}

    def connect(url: str, **kwargs: object) -> None:
        seen.update(kwargs)
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(cleanup.psycopg, "connect", connect)
    with pytest.raises(cleanup.CleanupError, match="연결할 수 없습니다"):
        cleanup.cleanup_test_data([new_marker_email()], dry_run=True)
    assert seen["connect_timeout"] == cleanup.CONNECT_TIMEOUT_SECONDS


def test_connect_config_error_does_not_leak_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secretpw@127.0.0.1:1/x")

    def connect(url: str, **kwargs: object) -> None:
        raise psycopg.ProgrammingError("invalid connection string near secretpw")

    monkeypatch.setattr(cleanup.psycopg, "connect", connect)
    with pytest.raises(cleanup.CleanupError) as info:
        cleanup.cleanup_test_data([new_marker_email()], dry_run=True)
    assert "secretpw" not in str(info.value)


def test_cli_exits_1_when_db_unreachable(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secretpw@127.0.0.1:1/x")

    def connect(url: str, **kwargs: object) -> None:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(cleanup.psycopg, "connect", connect)
    assert cleanup.main(["--all", "--dry-run"]) == 1
    assert "연결할 수 없습니다" in capsys.readouterr().err


def test_sweep_dry_run_reports_stray_and_excludes_it_from_targets(
    fake_db: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    valid_id, stray_id = uuid.uuid4(), uuid.uuid4()
    fake_db["rows"] = [(valid_id, new_marker_email()), (stray_id, STRAY_EMAIL)]

    counts = cleanup.cleanup_test_data(None, dry_run=True)

    assert counts["stray_users"] == 1
    id_lists = [params[0] for sql, params in fake_db["log"] if params and "::uuid[]" in sql]  # type: ignore[union-attr]
    assert id_lists
    assert all(stray_id not in ids and valid_id in ids for ids in id_lists if ids)
    out = capsys.readouterr().out
    assert "stray" in out
    assert STRAY_EMAIL in out
    assert _deletes(fake_db) == []


def test_sweep_real_run_with_stray_aborts_without_deleting(fake_db: dict[str, object]) -> None:
    fake_db["rows"] = [(uuid.uuid4(), new_marker_email()), (uuid.uuid4(), STRAY_EMAIL)]

    with pytest.raises(cleanup.UnsafeCleanupTarget):
        cleanup.cleanup_test_data(None, dry_run=False)

    assert _deletes(fake_db) == []


def test_cli_exit_codes_for_stray_and_clean(fake_db: dict[str, object]) -> None:
    fake_db["rows"] = [(uuid.uuid4(), new_marker_email())]
    assert cleanup.main(["--all", "--dry-run"]) == 0

    fake_db["rows"] = [(uuid.uuid4(), new_marker_email()), (uuid.uuid4(), STRAY_EMAIL)]
    assert cleanup.main(["--all", "--dry-run"]) == cleanup.EXIT_STRAY_FOUND == 3
    assert cleanup.main(["--all"]) == 1  # 실삭제 경로는 stray가 있으면 중단(삭제 없음)
    assert _deletes(fake_db) == []


def test_stray_only_sweep_dry_run_still_reports(
    fake_db: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_db["rows"] = [(uuid.uuid4(), STRAY_EMAIL)]

    assert cleanup.cleanup_test_data(None, dry_run=True)["stray_users"] == 1
    assert "대상 없음" in capsys.readouterr().out
