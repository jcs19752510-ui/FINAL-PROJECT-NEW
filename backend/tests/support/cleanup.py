"""테스트 계정과 연쇄 데이터 정리 헬퍼 (docs/harness/test-infra.md).

안전 원칙:
- 대상은 `accounts.MARKER_EMAIL_RE`에 정확히 일치하는 이메일의 계정뿐이다. 이메일 인자가 하나라도
  형식에 맞지 않으면 DB를 건드리기 전에 거부한다.
- 삭제 전에 대상 건수를 출력하고, 삭제 건수가 조회 건수와 다르면 트랜잭션 전체를 롤백한다.
- 마커 계정을 참조하는 실사용자 데이터가 있으면 아무것도 지우지 않고 중단한다.
- 접속 정보는 하드코딩하지 않는다: env `DATABASE_URL`, 없으면 앱과 같은 관례로 `backend/.env`.
- DB에 연결할 수 없으면 `CONNECT_TIMEOUT_SECONDS` 안에 `CleanupError`로 끝난다 (teardown 무기한 대기 방지).
- `--all` 조회 결과에 형식 불일치("stray") 마커형 행이 섞여 있을 때: 실삭제는 아무것도 지우지 않고 중단하고,
  `--dry-run`은 정상 마커 건수를 집계하면서 stray를 별도 보고한다 (stray는 어떤 경우에도 삭제 대상이 아니다).

CLI (backend/ 에서 실행):
    python -m tests.support.cleanup --email <marker email> [--email ...] [--dry-run]
    python -m tests.support.cleanup --all [--dry-run]   # 마커 계정 전체 (병렬 실행 중인 다른 테스트 계정도 포함)

종료코드: 0 = 정상(stray 없음), 1 = 실패/중단(연결 불가, 비마커 거부, 실삭제 중 stray 발견 등),
          3 = 정상 집계했으나 stray 존재(--all --dry-run 전용; argparse 사용법 오류 2와 구분).
"""
import argparse
import os
import sys
import uuid
from collections.abc import Iterable
from pathlib import Path

import psycopg

from tests.support.accounts import MARKER_EMAIL_LIKE, is_marker_email

_BACKEND_DIR = Path(__file__).resolve().parents[2]
CONNECT_TIMEOUT_SECONDS = 5
EXIT_STRAY_FOUND = 3


class CleanupError(RuntimeError):
    pass


class UnsafeCleanupTarget(CleanupError):
    pass


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        env_file = _BACKEND_DIR / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "DATABASE_URL":
                    url = value.strip().strip("\"'")
    if not url:
        raise CleanupError("DATABASE_URL이 없습니다: env로 지정하거나 backend/.env에 정의하세요.")
    # 앱은 SQLAlchemy 드라이버 접미사(postgresql+psycopg://)를 쓰지만 psycopg는 순정 스킴만 받는다.
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _connect() -> psycopg.Connection:
    url = _database_url()
    try:
        return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    except psycopg.OperationalError as exc:
        raise CleanupError(f"DB에 연결할 수 없습니다 (제한 {CONNECT_TIMEOUT_SECONDS}초): {exc}") from exc
    except psycopg.Error as exc:
        # DSN 파싱 오류 메시지는 접속 문자열 일부를 되풀이할 수 있어 원문을 싣지 않는다.
        detail = f"DB 접속 설정이 올바르지 않습니다 ({type(exc).__name__}). DATABASE_URL을 확인하세요."
        raise CleanupError(detail) from exc


def _count(cur: psycopg.Cursor, sql: str, ids: list[uuid.UUID]) -> int:
    cur.execute(sql, (ids,))
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def cleanup_test_data(emails: Iterable[str] | None = None, *, dry_run: bool = False) -> dict[str, int]:
    """마커 계정(`emails` 지정 시 그 계정만, None이면 마커 계정 전체)과 연쇄 데이터를 삭제한다.

    반환값은 테이블별 (삭제된 또는 dry_run이면 삭제 예정) 건수 + `stray_users`(형식 불일치로 제외한 행 수).
    stray는 `emails=None`(--all) 조회에서만 생길 수 있고, `dry_run=False`이면 삭제 없이 중단한다.
    """
    email_list: list[str] | None = None
    if emails is not None:
        email_list = list(emails)
        bad = [e for e in email_list if not is_marker_email(e)]
        if bad:
            raise UnsafeCleanupTarget(f"마커 형식이 아닌 이메일은 정리할 수 없습니다: {bad}")

    with _connect() as conn, conn.cursor() as cur:
        if email_list is None:
            cur.execute("SELECT id, email FROM users WHERE email LIKE %s ESCAPE '\\'", (MARKER_EMAIL_LIKE,))
        else:
            cur.execute("SELECT id, email FROM users WHERE email = ANY(%s)", (email_list,))
        rows = cur.fetchall()

        # LIKE 결과를 정규식으로 한 번 더 걸러 SQL 패턴 실수가 오삭제로 이어지지 않게 한다.
        stray = [email for _, email in rows if not is_marker_email(email)]
        if stray and not dry_run:
            raise UnsafeCleanupTarget(f"조회된 계정 중 마커 형식이 아닌 것이 있어 중단합니다: {stray}")
        user_ids = [row[0] for row in rows if is_marker_email(row[1])]

        counts = dict.fromkeys(
            [
                "transcripts",
                "code_submissions",
                "whiteboard_snapshots",
                "evaluation_reports",
                "interviews",
                "consents",
                "deletion_requests",
                "rubric_templates",
                "users",
            ],
            0,
        )
        counts["stray_users"] = len(stray)
        if stray:
            print(
                f"[harness cleanup] 형식 불일치(stray) 마커형 계정 {len(stray)}건 — 삭제 대상 아님, 수동 확인 필요: "
                + ", ".join(sorted(stray))
            )
        if not user_ids:
            print("[harness cleanup] 대상 없음 (users=0)")
            return counts

        cur.execute("SELECT id FROM interviews WHERE candidate_id = ANY(%s::uuid[])", (user_ids,))
        interview_ids = [row[0] for row in cur.fetchall()]

        # 실사용자 면접이 테스트 채용담당자/템플릿을 참조하면 지우지도, 참조를 끊지도 않고 중단한다.
        foreign = _count_foreign(cur, user_ids)
        if foreign:
            raise UnsafeCleanupTarget(
                f"마커 계정을 참조하는 비-마커 면접 {foreign}건이 있어 중단합니다. 수동 확인이 필요합니다."
            )

        by_interview = {
            "transcripts": "SELECT count(*) FROM transcripts WHERE interview_id = ANY(%s::uuid[])",
            "code_submissions": "SELECT count(*) FROM code_submissions WHERE interview_id = ANY(%s::uuid[])",
            "whiteboard_snapshots": "SELECT count(*) FROM whiteboard_snapshots WHERE interview_id = ANY(%s::uuid[])",
            "evaluation_reports": "SELECT count(*) FROM evaluation_reports WHERE interview_id = ANY(%s::uuid[])",
            "interviews": "SELECT count(*) FROM interviews WHERE id = ANY(%s::uuid[])",
        }
        by_user = {
            "consents": "SELECT count(*) FROM consents WHERE user_id = ANY(%s::uuid[])",
            "deletion_requests": "SELECT count(*) FROM deletion_requests WHERE user_id = ANY(%s::uuid[])",
            "rubric_templates": "SELECT count(*) FROM rubric_templates WHERE recruiter_id = ANY(%s::uuid[])",
            "users": "SELECT count(*) FROM users WHERE id = ANY(%s::uuid[])",
        }
        for table, sql in by_interview.items():
            counts[table] = _count(cur, sql, interview_ids)
        for table, sql in by_user.items():
            counts[table] = _count(cur, sql, user_ids)

        mode = "DRY-RUN(삭제 안 함)" if dry_run else "삭제 예정"
        print(
            f"[harness cleanup] {mode}: "
            + ", ".join(f"{t}={n}" for t, n in counts.items() if t != "stray_users")
        )
        if dry_run:
            return counts

        # FK 의존 순서(자식 -> 부모). 새 테이블이 users/interviews를 참조하게 되면 여기에 추가해야 한다
        # (누락 시 FK 위반으로 트랜잭션이 롤백되어 아무것도 지워지지 않는다).
        deletes = [
            ("transcripts", "DELETE FROM transcripts WHERE interview_id = ANY(%s::uuid[])", interview_ids),
            ("code_submissions", "DELETE FROM code_submissions WHERE interview_id = ANY(%s::uuid[])", interview_ids),
            (
                "whiteboard_snapshots",
                "DELETE FROM whiteboard_snapshots WHERE interview_id = ANY(%s::uuid[])",
                interview_ids,
            ),
            (
                "evaluation_reports",
                "DELETE FROM evaluation_reports WHERE interview_id = ANY(%s::uuid[])",
                interview_ids,
            ),
            ("interviews", "DELETE FROM interviews WHERE id = ANY(%s::uuid[])", interview_ids),
            ("consents", "DELETE FROM consents WHERE user_id = ANY(%s::uuid[])", user_ids),
            ("deletion_requests", "DELETE FROM deletion_requests WHERE user_id = ANY(%s::uuid[])", user_ids),
            ("rubric_templates", "DELETE FROM rubric_templates WHERE recruiter_id = ANY(%s::uuid[])", user_ids),
            ("users", "DELETE FROM users WHERE id = ANY(%s::uuid[])", user_ids),
        ]
        for table, sql, ids in deletes:
            cur.execute(sql, (ids,))
            if cur.rowcount != counts[table]:
                raise CleanupError(
                    f"{table}: 삭제 건수({cur.rowcount})가 조회 건수({counts[table]})와 달라 롤백합니다."
                )
        return counts


def _count_foreign(cur: psycopg.Cursor, user_ids: list[uuid.UUID]) -> int:
    cur.execute(
        "SELECT count(*) FROM interviews WHERE NOT (candidate_id = ANY(%s::uuid[])) AND ("
        " recruiter_id = ANY(%s::uuid[]) OR rubric_template_id IN"
        " (SELECT id FROM rubric_templates WHERE recruiter_id = ANY(%s::uuid[])))",
        (user_ids, user_ids, user_ids),
    )
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="하네스 테스트 계정/데이터 정리 (마커 이메일 전용)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--email", action="append", help="정리할 마커 이메일 (여러 번 지정 가능)")
    target.add_argument("--all", action="store_true", help="마커 계정 전체 (병렬 실행 중인 테스트 계정 포함 주의)")
    parser.add_argument("--dry-run", action="store_true", help="건수만 출력하고 삭제하지 않음")
    args = parser.parse_args(argv)
    try:
        counts = cleanup_test_data(None if args.all else args.email, dry_run=args.dry_run)
    except CleanupError as exc:
        print(f"[harness cleanup] 실패: {exc}", file=sys.stderr)
        return 1
    return EXIT_STRAY_FOUND if counts["stray_users"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
