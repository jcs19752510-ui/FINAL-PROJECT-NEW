-- Delete ALL candidate (role='candidate') accounts and their interview data.
-- Keeps: recruiter/admin accounts, questions, coding_problems, rubric_templates (system defaults and recruiter-owned).
-- Usage (psql variable): -v mode=dry   -> print counts, change nothing (ROLLBACK)
--                        -v mode=apply -> delete for real (COMMIT)
\set ON_ERROR_STOP on
\pset format aligned
BEGIN;

CREATE TEMP TABLE _c ON COMMIT DROP AS SELECT id FROM users WHERE role = 'candidate';
CREATE TEMP TABLE _i ON COMMIT DROP AS SELECT id FROM interviews WHERE candidate_id IN (SELECT id FROM _c);

SELECT 'BEFORE' AS phase,
  (SELECT count(*) FROM _c) AS candidates,
  (SELECT count(*) FROM _i) AS interviews,
  (SELECT count(*) FROM transcripts WHERE interview_id IN (SELECT id FROM _i)) AS transcripts,
  (SELECT count(*) FROM evaluation_reports WHERE interview_id IN (SELECT id FROM _i)) AS reports,
  (SELECT count(*) FROM code_submissions WHERE interview_id IN (SELECT id FROM _i)) AS code_subs,
  (SELECT count(*) FROM whiteboard_snapshots WHERE interview_id IN (SELECT id FROM _i)) AS whiteboards,
  (SELECT count(*) FROM resume_applications WHERE candidate_id IN (SELECT id FROM _c)) AS resumes,
  (SELECT count(*) FROM consents WHERE user_id IN (SELECT id FROM _c)) AS consents,
  (SELECT count(*) FROM deletion_requests WHERE user_id IN (SELECT id FROM _c)) AS deletion_reqs;

-- FK-safe order (children first)
DELETE FROM evaluation_reports   WHERE interview_id IN (SELECT id FROM _i);
DELETE FROM transcripts          WHERE interview_id IN (SELECT id FROM _i);
DELETE FROM code_submissions     WHERE interview_id IN (SELECT id FROM _i);
DELETE FROM whiteboard_snapshots WHERE interview_id IN (SELECT id FROM _i);
DELETE FROM interviews           WHERE id IN (SELECT id FROM _i);
DELETE FROM deletion_requests    WHERE user_id IN (SELECT id FROM _c);
DELETE FROM consents             WHERE user_id IN (SELECT id FROM _c);
DELETE FROM resume_applications  WHERE candidate_id IN (SELECT id FROM _c);
-- references from other rows to candidates (should be none; cleared defensively)
UPDATE interviews          SET recruiter_id = NULL     WHERE recruiter_id IN (SELECT id FROM _c);
UPDATE interviews          SET final_decided_by = NULL WHERE final_decided_by IN (SELECT id FROM _c);
UPDATE resume_applications SET reviewed_by = NULL      WHERE reviewed_by IN (SELECT id FROM _c);
UPDATE rubric_templates    SET recruiter_id = NULL     WHERE recruiter_id IN (SELECT id FROM _c);
DELETE FROM users                WHERE id IN (SELECT id FROM _c);

SELECT 'AFTER (inside transaction)' AS phase,
  (SELECT count(*) FROM users WHERE role = 'candidate') AS candidates_left,
  (SELECT count(*) FROM users WHERE role = 'recruiter') AS recruiters_kept,
  (SELECT count(*) FROM users WHERE role = 'admin') AS admins_kept,
  (SELECT count(*) FROM interviews) AS interviews_left,
  (SELECT count(*) FROM questions) AS questions_kept,
  (SELECT count(*) FROM coding_problems) AS coding_problems_kept;

SELECT (:'mode' = 'apply') AS do_commit \gset
\if :do_commit
COMMIT;
\echo '>>> COMMITTED (apply mode)'
\else
ROLLBACK;
\echo '>>> ROLLED BACK (dry-run: nothing was deleted)'
\endif
