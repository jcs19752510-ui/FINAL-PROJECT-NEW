"""최종 합격/불합격 처리 API 테스트 (실서버 HTTP, 메일 미설정 환경 — 자동 발송 경로는 test_final_decision_mail.py).

사전 조건: docs/harness/test-infra.md 와 같다(서버 + DATABASE_URL). 서버는 GMAIL_* 미설정 상태여야 한다.
"""

import threading
import uuid

import httpx
import pytest

from tests.final_decision.helpers import final_row, insert_interview
from tests.support.accounts import API_V1, AccountFactory

NOTE_OK = "최종 합격을 진심으로 축하드립니다. 함께하게 되어 기쁩니다."
NOTE_NO = "아쉽게도 이번 채용에서는 최종 합격에 이르지 못했습니다."


@pytest.fixture
def ctx(api: httpx.Client, account_factory: AccountFactory):
    recruiter = account_factory.create("recruiter")
    candidate = account_factory.create(
        "candidate",
    )
    return api, recruiter, candidate


def _decide(api, recruiter, iid, status="accepted", note=NOTE_OK):
    return api.patch(
        f"{API_V1}/recruiter/reports/{iid}/final-decision",
        headers=recruiter.auth_headers,
        json={"status": status, "decision_note": note},
    )


def test_accept_completed_interview(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    resp = _decide(api, recruiter, iid)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interview_id"] == iid
    assert body["final_decision"] == "accepted"
    assert body["final_decision_note"] == NOTE_OK
    assert body["final_decided_at"]
    assert body["final_notified_at"] is None  # 메일 미설정 → 보낸 척 하지 않는다
    decision, note, by, at, notified = final_row(iid)
    assert (decision, note, by, notified) == ("accepted", NOTE_OK, recruiter.user_id, None) and at is not None


def test_reject_completed_interview(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    resp = _decide(api, recruiter, iid, "rejected", NOTE_NO)
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_decision"] == "rejected"
    assert final_row(iid)[0] == "rejected"


def test_second_decision_is_rejected_and_keeps_first(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    assert _decide(api, recruiter, iid).status_code == 200
    for status, note in (("accepted", NOTE_OK), ("rejected", NOTE_NO)):
        again = _decide(api, recruiter, iid, status, note)
        assert again.status_code == 409
        assert "변경할 수 없습니다" in again.json()["detail"]
    assert final_row(iid)[:2] == ("accepted", NOTE_OK)


@pytest.mark.parametrize("status", ["scheduled", "live", "paused", "expired"])
def test_non_completed_interview_is_rejected(ctx, status):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id, status)
    resp = _decide(api, recruiter, iid)
    assert resp.status_code == 409
    assert final_row(iid)[0] is None


def test_unknown_interview_404(ctx):
    api, recruiter, _ = ctx
    assert _decide(api, recruiter, str(uuid.uuid4())).status_code == 404


def test_candidate_cannot_decide_403(ctx):
    api, _, candidate = ctx
    iid = insert_interview(candidate.user_id)
    resp = api.patch(
        f"{API_V1}/recruiter/reports/{iid}/final-decision",
        headers=candidate.auth_headers,
        json={"status": "accepted", "decision_note": NOTE_OK},
    )
    assert resp.status_code == 403
    assert final_row(iid)[0] is None


def test_unauthenticated_401(ctx):
    api, _, candidate = ctx
    iid = insert_interview(candidate.user_id)
    for method, path in (
        ("PATCH", "final-decision"),
        ("GET", "final-notification-draft"),
        ("POST", "final-mark-notified"),
    ):
        resp = api.request(
            method,
            f"{API_V1}/recruiter/reports/{iid}/{path}",
            json={"status": "accepted", "decision_note": "x"} if method == "PATCH" else None,
        )
        assert resp.status_code == 401, path


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "accepted", "decision_note": ""},
        {"status": "accepted", "decision_note": "   "},
        {"status": "accepted", "decision_note": "가" * 501},
        {"status": "accepted"},
        {"status": "pending", "decision_note": NOTE_OK},
        {"status": "hired", "decision_note": NOTE_OK},
        {"decision_note": NOTE_OK},
    ],
)
def test_invalid_payload_422(ctx, payload):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    resp = api.patch(f"{API_V1}/recruiter/reports/{iid}/final-decision", headers=recruiter.auth_headers, json=payload)
    assert resp.status_code == 422
    assert final_row(iid)[0] is None


def test_note_boundary_500_chars_ok_and_trimmed(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    resp = _decide(api, recruiter, iid, "accepted", "  " + "가" * 500 + "  ")
    assert resp.status_code == 200
    assert resp.json()["final_decision_note"] == "가" * 500


def test_draft_requires_decision_then_matches_decision(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    url = f"{API_V1}/recruiter/reports/{iid}/final-notification-draft"
    assert api.get(url, headers=recruiter.auth_headers).status_code == 409
    _decide(api, recruiter, iid)
    draft = api.get(url, headers=recruiter.auth_headers)
    assert draft.status_code == 200
    body = draft.json()
    assert body["to_email"] == candidate.email
    assert body["subject"] == "[채용 안내] 최종 합격 안내"
    assert candidate.name in body["body"] and NOTE_OK in body["body"] and "최종 합격하셨습니다" in body["body"]
    assert "서류 전형" not in body["body"]  # 이력서 합격 문구를 재사용하지 않는다


def test_rejected_draft_content(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    _decide(api, recruiter, iid, "rejected", NOTE_NO)
    body = api.get(f"{API_V1}/recruiter/reports/{iid}/final-notification-draft", headers=recruiter.auth_headers).json()
    assert body["subject"] == "[채용 안내] 최종 결과 안내"
    assert NOTE_NO in body["body"] and "합격하지 못하셨습니다" in body["body"]


def test_draft_candidate_forbidden(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    _decide(api, recruiter, iid)
    assert (
        api.get(
            f"{API_V1}/recruiter/reports/{iid}/final-notification-draft", headers=candidate.auth_headers
        ).status_code
        == 403
    )


def test_mark_notified_flow_and_idempotent(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    url = f"{API_V1}/recruiter/reports/{iid}/final-mark-notified"
    assert api.post(url, headers=recruiter.auth_headers).status_code == 409  # 처리 전
    _decide(api, recruiter, iid)
    first = api.post(url, headers=recruiter.auth_headers)
    assert first.status_code == 200 and first.json()["final_notified_at"]
    second = api.post(url, headers=recruiter.auth_headers)
    assert second.json()["final_notified_at"] == first.json()["final_notified_at"]  # 덮어쓰지 않는다
    assert api.post(url, headers=candidate.auth_headers).status_code == 403


def test_report_detail_exposes_final_fields(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    url = f"{API_V1}/recruiter/reports/{iid}"
    before = api.get(url, headers=recruiter.auth_headers).json()
    assert before["final_decision"] is None and before["final_decision_note"] is None
    _decide(api, recruiter, iid)
    after = api.get(url, headers=recruiter.auth_headers).json()
    assert after["final_decision"] == "accepted" and after["final_decision_note"] == NOTE_OK
    assert after["final_decided_at"] and after["final_notified_at"] is None


def test_concurrent_decisions_only_one_wins(ctx):
    api, recruiter, candidate = ctx
    iid = insert_interview(candidate.user_id)
    results: list[int] = []

    def worker(status: str, note: str) -> None:
        with httpx.Client(base_url=str(api.base_url), timeout=30.0) as c:
            results.append(_decide(c, recruiter, iid, status, note).status_code)

    threads = [
        threading.Thread(target=worker, args=("accepted", NOTE_OK)),
        threading.Thread(target=worker, args=("rejected", NOTE_NO)),
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409]
    assert final_row(iid)[0] in ("accepted", "rejected")
