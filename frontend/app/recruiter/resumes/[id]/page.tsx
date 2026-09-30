"use client";

/**
 * [Feature J] 이력서 상세 + 합격/불합격 판단 + 통보 초안 — 이력서제출_합격통보_
 * 신규기능_요청프롬프트.md §4-2. 판단 저장 후에는 화면에서 바로 통보 초안
 * (제목/본문)을 불러와 관리자가 복사해 MCP 메일 도구로 직접 보낼 수 있게
 * 하고, 발송을 마치면 "통보 완료로 표시" 버튼으로 `notified_at`을 남긴다
 * (§2 결정#3 — 백엔드는 이메일을 자동 발송하지 않는다).
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  type NotificationDraftOut,
  type RecruiterResumeDetailOut,
  type UserOut,
  clearAccessToken,
  decideResume,
  downloadResumeFile,
  getMe,
  getNotificationDraft,
  getRecruiterResumeDetail,
  markResumeNotified,
  readAccessToken,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import styles from "../../recruiter.module.css";

const STATUS_LABEL: Record<RecruiterResumeDetailOut["status"], string> = {
  pending: "심사 대기",
  accepted: "합격",
  rejected: "불합격",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

const WEEKDAY_LABEL = ["일", "월", "화", "수", "목", "금", "토"];

// "YYYY-MM-DD(요일) HH:MM 나머지 문구" 형식으로 저장된 기존 값을 날짜/시간/보충 문구로
// 되돌린다. 이 형식이 아닌 옛 자유 텍스트는 통째로 보충 문구 칸에 넣고 날짜/시간은
// 비워둔다 — 잘못 쪼개서 보여주는 것보다 안전하다(2026-09-30, 사용자 지시로 날짜/시간
// 선택 UI 추가).
function parseScheduleNote(note: string | null): { date: string; time: string; extra: string } {
  if (!note) return { date: "", time: "", extra: "" };
  const match = note.match(/^(\d{4}-\d{2}-\d{2})\((?:일|월|화|수|목|금|토)\)\s+(\d{2}:\d{2})(?:\s+([\s\S]*))?$/);
  if (!match) return { date: "", time: "", extra: note };
  return { date: match[1], time: match[2], extra: match[3] ?? "" };
}

function composeScheduleNote(date: string, time: string, extra: string): string | undefined {
  const trimmedExtra = extra.trim();
  if (!date && !time) return trimmedExtra || undefined;
  const weekday = WEEKDAY_LABEL[new Date(`${date}T${time}`).getDay()];
  const formatted = `${date}(${weekday}) ${time}`;
  return trimmedExtra ? `${formatted} ${trimmedExtra}` : formatted;
}

export default function RecruiterResumeDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [detail, setDetail] = useState<RecruiterResumeDetailOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [decisionNote, setDecisionNote] = useState("");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [scheduleExtra, setScheduleExtra] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [draft, setDraft] = useState<NotificationDraftOut | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [markingNotified, setMarkingNotified] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
      return;
    }
    getMe(accessToken)
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAccessToken();
          router.push("/login");
          return;
        }
        setUser(null);
      })
      .finally(() => setAuthLoading(false));
  }, [accessToken, router]);

  function reload() {
    if (!accessToken || !params.id) return;
    getRecruiterResumeDetail(accessToken, params.id)
      .then((d) => {
        setDetail(d);
        setDecisionNote(d.decision_note ?? "");
        const parsed = parseScheduleNote(d.interview_schedule_note);
        setScheduleDate(parsed.date);
        setScheduleTime(parsed.time);
        setScheduleExtra(parsed.extra);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "네트워크 오류로 상세 정보를 가져오지 못했어요.");
      });
  }

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter") return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, user, params.id]);

  // 2026-09-30(사용자 지시): "이력서 미리보기" 버튼을 눌러야만 PDF가 뜨던 것을
  // 상세 화면에 들어오는 즉시 자동으로 불러오도록 변경 — 버튼은 수동 새로고침용으로 남긴다.
  // autoLoadedIdRef로 같은 id에 대해 두 번 fetch하지 않도록 막는다(React strict mode
  // 개발 모드 이펙트 이중 호출 대비 — 실측 중 실제로 파일 요청이 2번 나가는 것을 확인해 추가).
  const autoLoadedIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!accessToken || !detail) return;
    if (autoLoadedIdRef.current === detail.id) return;
    autoLoadedIdRef.current = detail.id;
    handleDownload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, detail?.id]);

  const scheduleIncomplete = (!!scheduleDate) !== (!!scheduleTime);

  async function handleDecision(nextStatus: "accepted" | "rejected") {
    if (!accessToken || !params.id || saving || scheduleIncomplete) return;
    setSaving(true);
    setActionError(null);
    try {
      const updated = await decideResume(accessToken, params.id, {
        status: nextStatus,
        decision_note: decisionNote.trim() || undefined,
        interview_schedule_note: composeScheduleNote(scheduleDate, scheduleTime, scheduleExtra),
      });
      setDetail(updated);
      setDraft(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleLoadDraft() {
    if (!accessToken || !params.id) return;
    setDraftError(null);
    try {
      setDraft(await getNotificationDraft(accessToken, params.id));
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.message : "안내 초안을 가져오지 못했어요.");
    }
  }

  async function handleDownload() {
    if (!accessToken || !params.id || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await downloadResumeFile(accessToken, params.id);
      // 2026-09-29(실제 결함 발견·수정, 사용자 재확인 계기): `window.open()`을
      // `await fetch(...)` 뒤에 호출하면 Chrome이 "사용자 동작의 직접 결과가
      // 아니다"라고 판단해 팝업을 조용히 차단한다(에러도 없이 그냥 아무 일도
      // 안 일어남 — `window.open()`이 `null`을 반환하는 것으로 실측 확인).
      // 새 탭을 열려는 시도 자체를 없애고, 같은 화면에 `<iframe>`으로 바로
      // 미리보기를 내장하는 방식으로 바꿔 이 문제를 근본적으로 피한다 —
      // 사용자가 원래 요청한 "바로 확인"에도 새 탭보다 더 잘 맞는 방식이다.
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(URL.createObjectURL(blob));
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "파일을 가져오지 못했어요.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleMarkNotified() {
    if (!accessToken || !params.id || markingNotified) return;
    setMarkingNotified(true);
    try {
      const updated = await markResumeNotified(accessToken, params.id);
      setDetail(updated);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "안내 완료 처리 중 오류가 발생했어요.");
    } finally {
      setMarkingNotified(false);
    }
  }

  if (authLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>불러오는 중...</div>
      </div>
    );
  }

  if (!user || user.role !== "recruiter") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>{!user ? "로그인이 필요합니다" : "권한이 없습니다"}</h1>
          <Link href={!user ? "/login" : "/"} className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            {!user ? "로그인하러 가기" : "홈으로"}
          </Link>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className={styles.page}>
        <HomeLink />
        <div className="banner-error" role="alert">
          {loadError}
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton} aria-busy="true">
          불러오는 중입니다...
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <HomeLink />
      <div className={styles.detailHeader}>
        <h1 style={{ margin: 0 }}>{detail.candidate_name}님의 이력서</h1>
        <span className={styles.statusTag}>{STATUS_LABEL[detail.status]}</span>
      </div>
      <p className={styles.subtitle}>
        {detail.candidate_email} · 제출일시 {formatDateTime(detail.submitted_at)}
      </p>

      {downloadError && (
        <div className="banner-error" role="alert" style={{ marginTop: 12 }}>
          {downloadError}
        </div>
      )}
      <p>
        <button type="button" className="submit-button" disabled={downloading} onClick={handleDownload}>
          {downloading ? "불러오는 중..." : previewUrl ? "이력서 미리보기 새로고침" : `이력서 미리보기 (${detail.original_filename})`}
        </button>
        {previewUrl && (
          <a
            href={previewUrl}
            download={detail.original_filename}
            className="submit-button"
            style={{
              display: "inline-block",
              marginLeft: 8,
              textDecoration: "none",
              background: "var(--color-text-secondary)",
              width: "auto",
              padding: "12px 16px",
            }}
          >
            내 컴퓨터에 저장
          </a>
        )}
      </p>
      {previewUrl && (
        <iframe
          src={previewUrl}
          title={`${detail.original_filename} 미리보기`}
          style={{ width: "100%", height: 480, border: "1px solid var(--color-border)", borderRadius: 8, marginBottom: 16 }}
        />
      )}

      {actionError && (
        <div className="banner-error" role="alert" style={{ marginTop: 12 }}>
          {actionError}
        </div>
      )}

      <section style={{ marginTop: 24 }}>
        <h2>합격/불합격 결정</h2>
        <div className="field">
          <label htmlFor="decision-note">합격 안내 문구 또는 불합격 사유</label>
          <textarea
            id="decision-note"
            value={decisionNote}
            onChange={(e) => setDecisionNote(e.target.value)}
            rows={3}
            style={{ width: "100%" }}
          />
        </div>
        <div className="field">
          <label htmlFor="schedule-date">면접 일정 안내 (선택 입력, 참고용이에요)</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              id="schedule-date"
              type="date"
              aria-label="면접 날짜"
              value={scheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
              style={{ flex: 1 }}
            />
            <input
              id="schedule-time"
              type="time"
              aria-label="면접 시간"
              value={scheduleTime}
              onChange={(e) => setScheduleTime(e.target.value)}
              style={{ flex: 1 }}
            />
          </div>
          {scheduleIncomplete && (
            <div className="field-error">면접 날짜와 시간을 모두 입력해주세요.</div>
          )}
          <input
            id="schedule-extra"
            type="text"
            aria-label="면접 일정 보충 설명"
            value={scheduleExtra}
            onChange={(e) => setScheduleExtra(e.target.value)}
            placeholder="예: 이후 편한 시간에 모의면접을 진행해주세요."
            style={{ width: "100%", marginTop: 8 }}
          />
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <button type="button" className="submit-button" disabled={saving || scheduleIncomplete} onClick={() => handleDecision("accepted")}>
            {saving ? "저장 중..." : "합격 처리"}
          </button>
          <button
            type="button"
            className="submit-button"
            style={{ background: "var(--color-text-secondary)" }}
            disabled={saving || scheduleIncomplete}
            onClick={() => handleDecision("rejected")}
          >
            {saving ? "저장 중..." : "불합격 처리"}
          </button>
        </div>
      </section>

      {detail.status !== "pending" && (
        <section style={{ marginTop: 32 }}>
          <h2>합격/불합격 안내</h2>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            아래 내용을 그대로 복사해서 이메일로 직접 보내주세요. 이 화면에서 자동으로 발송되지는 않아요.
          </p>
          {draftError && <div className="banner-error">{draftError}</div>}
          {!draft ? (
            <button type="button" className="submit-button" onClick={handleLoadDraft}>
              안내 내용 미리보기
            </button>
          ) : (
            <div
              style={{
                background: "var(--color-surface-secondary, #f3f4f6)",
                borderRadius: 8,
                padding: 14,
                marginTop: 12,
              }}
            >
              <div>
                <strong>받는 사람:</strong> {draft.to_email}
              </div>
              <div>
                <strong>제목:</strong> {draft.subject}
              </div>
              <pre style={{ whiteSpace: "pre-wrap", marginTop: 8, fontFamily: "inherit" }}>{draft.body}</pre>
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            {detail.notified_at ? (
              <span style={{ color: "var(--color-text-secondary)" }}>안내 완료: {formatDateTime(detail.notified_at)}</span>
            ) : (
              <button type="button" className="submit-button" disabled={markingNotified} onClick={handleMarkNotified}>
                {markingNotified ? "처리 중..." : "발송 완료로 표시"}
              </button>
            )}
          </div>
        </section>
      )}

      <div style={{ marginTop: 32 }}>
        <Link href="/recruiter/resumes">이력서 목록으로 돌아가기</Link>
      </div>
    </div>
  );
}
