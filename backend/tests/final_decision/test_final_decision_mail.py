"""최종 합격/불합격 자동 메일 발송 경로 테스트 — 앱을 프로세스 안에서 띄우고 SMTP 발송 함수만 가짜로 바꾼다
(실제 Gmail 로 보내지 않는다). 사전 조건: DATABASE_URL, JWT_SECRET_KEY 환경변수와 마이그레이션 적용된 DB."""

import sys
import threading

import pytest

try:  # 무거운 AI 의존성이 없는 경량 테스트 venv 에서는 스텁으로 대체한다(docs/harness/test-infra.md §2.2).
    import faster_whisper  # noqa: F401
except ImportError:  # pragma: no cover
    import importlib.abc
    import importlib.machinery
    import types
    from unittest.mock import MagicMock

    class _Stub(types.ModuleType):
        def __getattr__(self, n):
            if n.startswith("__"):
                raise AttributeError(n)
            return MagicMock()

    class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        _NAMES = (
            "faster_whisper",
            "sentence_transformers",
            "librosa",
            "piper",
            "langchain_core",
            "langchain_openai",
            "av",
            "torch",
            "openai",
        )

        def find_spec(self, name, path, target=None):
            if name.split(".")[0] in self._NAMES:
                return importlib.machinery.ModuleSpec(name, self, is_package=True)

        def create_module(self, spec):
            m = _Stub(spec.name)
            m.__path__ = []
            return m

        def exec_module(self, module):
            pass

    sys.meta_path.insert(0, _Finder())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.email_service import EmailSendError  # noqa: E402
from tests.final_decision.helpers import final_row, insert_interview  # noqa: E402
from tests.support.accounts import API_V1, AccountFactory  # noqa: E402
from tests.support.cleanup import cleanup_test_data  # noqa: E402

NOTE = "최종 합격을 진심으로 축하드립니다. 함께하게 되어 기쁩니다."
MOD = "app.api.v1.recruiter_final_decision"


@pytest.fixture
def env():
    client = TestClient(app)  # lifespan 미사용(Redis/Celery 불필요)
    factory = AccountFactory(client)
    recruiter = factory.create("recruiter")
    candidate = factory.create("candidate")
    yield client, recruiter, candidate
    cleanup_test_data(set(factory.created_emails))


def _decide(client, recruiter, iid, status="accepted"):
    return client.patch(
        f"{API_V1}/recruiter/reports/{iid}/final-decision",
        headers=recruiter.auth_headers,
        json={"status": status, "decision_note": NOTE},
    )


def test_auto_send_success_sets_notified_at(env, monkeypatch):
    client, recruiter, candidate = env
    sent = []
    monkeypatch.setattr(f"{MOD}.email_configured", lambda: True)
    monkeypatch.setattr(f"{MOD}.send_notification_email", lambda to, subject, body: sent.append((to, subject, body)))
    iid = insert_interview(candidate.user_id)
    resp = _decide(client, recruiter, iid)
    assert resp.status_code == 200
    assert resp.json()["final_notified_at"]
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == candidate.email and subject == "[채용 안내] 최종 합격 안내" and NOTE in body and candidate.name in body
    assert final_row(iid)[4] is not None


def test_auto_send_rejected_mail_content(env, monkeypatch):
    client, recruiter, candidate = env
    sent = []
    monkeypatch.setattr(f"{MOD}.email_configured", lambda: True)
    monkeypatch.setattr(f"{MOD}.send_notification_email", lambda to, subject, body: sent.append((to, subject, body)))
    iid = insert_interview(candidate.user_id)
    assert _decide(client, recruiter, iid, "rejected").status_code == 200
    assert sent[0][1] == "[채용 안내] 최종 결과 안내" and "합격하지 못하셨습니다" in sent[0][2]


def test_send_failure_keeps_decision_without_notified_at(env, monkeypatch):
    client, recruiter, candidate = env

    def boom(*_a):
        raise EmailSendError("smtp down")

    monkeypatch.setattr(f"{MOD}.email_configured", lambda: True)
    monkeypatch.setattr(f"{MOD}.send_notification_email", boom)
    iid = insert_interview(candidate.user_id)
    resp = _decide(client, recruiter, iid)
    assert resp.status_code == 200 and resp.json()["final_decision"] == "accepted"
    assert resp.json()["final_notified_at"] is None  # 보낸 척 하지 않는다
    assert final_row(iid)[0] == "accepted" and final_row(iid)[4] is None
    # 수동 폴백 경로
    mark = client.post(f"{API_V1}/recruiter/reports/{iid}/final-mark-notified", headers=recruiter.auth_headers)
    assert mark.status_code == 200 and mark.json()["final_notified_at"]


def test_not_configured_sends_nothing(env, monkeypatch):
    client, recruiter, candidate = env
    sent = []
    monkeypatch.setattr(f"{MOD}.email_configured", lambda: False)
    monkeypatch.setattr(f"{MOD}.send_notification_email", lambda *a: sent.append(a))
    iid = insert_interview(candidate.user_id)
    assert _decide(client, recruiter, iid).json()["final_notified_at"] is None
    assert sent == []


def test_second_decision_never_resends_mail(env, monkeypatch):
    client, recruiter, candidate = env
    sent = []
    monkeypatch.setattr(f"{MOD}.email_configured", lambda: True)
    monkeypatch.setattr(f"{MOD}.send_notification_email", lambda *a: sent.append(a))
    iid = insert_interview(candidate.user_id)
    assert _decide(client, recruiter, iid).status_code == 200
    assert _decide(client, recruiter, iid, "rejected").status_code == 409
    assert _decide(client, recruiter, iid).status_code == 409
    assert len(sent) == 1


def test_concurrent_requests_send_exactly_one_mail(env, monkeypatch):
    client, recruiter, candidate = env
    sent = []
    monkeypatch.setattr(f"{MOD}.email_configured", lambda: True)
    monkeypatch.setattr(f"{MOD}.send_notification_email", lambda *a: sent.append(a))
    iid = insert_interview(candidate.user_id)
    codes: list[int] = []

    def worker():
        codes.append(_decide(TestClient(app), recruiter, iid).status_code)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200, 409, 409, 409]
    assert len(sent) == 1
