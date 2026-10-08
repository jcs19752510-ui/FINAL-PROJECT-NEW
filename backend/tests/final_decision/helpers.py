"""최종 합격/불합격 테스트 공용 헬퍼 — 면접 행을 DB에 직접 만든다(면접 진행 자체는 이 기능의 범위가 아니다)."""

import uuid

import psycopg

from tests.support.accounts import _database_url


def insert_interview(candidate_id: str, status: str = "completed") -> str:
    interview_id = str(uuid.uuid4())
    with psycopg.connect(_database_url(), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into interviews (id, candidate_id, status, report_status) "
            "values (%s, %s, %s::interview_status, 'none')",
            (interview_id, candidate_id, status),
        )
    return interview_id


def final_row(interview_id: str) -> tuple:
    with psycopg.connect(_database_url(), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(
            "select final_decision::text, final_decision_note, final_decided_by::text, "
            "final_decided_at, final_notified_at "
            "from interviews where id = %s",
            (interview_id,),
        )
        return cur.fetchone()
