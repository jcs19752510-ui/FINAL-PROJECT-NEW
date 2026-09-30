"use client";

/**
 * [Feature J] 이력서 상세 + 합격/불합격 판단 + 통보 — 이력서제출_합격통보_
 * 신규기능_요청프롬프트.md §4-2. 2026-09-30(사용자 지시)부터 판단 저장 직후
 * 백엔드가 Gmail SMTP로 안내 메일을 즉시 자동 발송한다(§2 결정#3의 반자동
 * 방식을 대체 — recruiter_resumes.py의 `decide_resume` 참고). 이 화면의
 * "안내 내용 미리보기"는 실제 발송된(혹은 발송될) 내용을 다시 확인하는
 * 용도이며, "발송 완료로 표시" 버튼은 자동 발송이 실패했을 때(메일 미설정,
 * SMTP 오류 등)의 수동 대체 경로로만 남아있다 — `detail.notified_at`이 이미
 * 채워져 있으면(자동 발송 성공) 이 버튼 대신 완료 시각만 보여준다.
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

// 2026-09-30(사용자 지시): 합격/불합격 안내 문구를 자유 텍스트 대신 드롭다운
// 템플릿 선택으로 변경. 문구 내용 자체는 초안이며, 원하는 표현으로 언제든
// 교체 가능(이 배열만 수정하면 됨).
const ACCEPT_TEMPLATES = [
  "축하드립니다. 안내해드린 일정에 맞춰 모의면접을 진행해주시기 바랍니다.",
  "우수한 서류 평가를 받으셨습니다. 다음 단계인 모의면접에서 뵙겠습니다.",
  "귀하의 경험과 역량이 저희가 찾는 인재상에 부합하여 합격하셨습니다.",
] as const;

const REJECT_TEMPLATES = [
  "이번 채용에는 아쉽게 인연이 닿지 않았으나, 좋은 결과로 다시 뵙기를 바랍니다.",
  "서류 심사 결과 이번 채용 요건에는 부합하지 않아 아쉽게 되었습니다.",
  "많은 지원자 중 제한된 인원만 선발하는 과정에서 아쉬운 결과를 안내드립니다.",
] as const;

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));
const MINUTE_OPTIONS = ["00", "30"];

// select에 없는 값(과거 자유 텍스트에서 되돌린 값 등)이 현재 선택돼 있으면 목록
// 맨 앞에 임시로 추가해 원본을 그대로 보여준다 — 값을 잃어버리지 않기 위함.
function withCurrentAsOption(options: readonly string[], current: string): string[] {
  if (!current || options.includes(current)) return [...options];
  return [current, ...options];
}

function formatLocalDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// 2026-09-30(사용자 지시): "면접일자는 기본으로 오늘 날짜 +7일로 지정 (토요일/
// 일요일 제외, +7일이 주말이면 그 다음 월요일로)".
function defaultInterviewDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  const day = d.getDay(); // 0=일, 6=토
  if (day === 6) d.setDate(d.getDate() + 2);
  else if (day === 0) d.setDate(d.getDate() + 1);
  return formatLocalDate(d);
}

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

  const [acceptNote, setAcceptNote] = useState("");
  const [rejectNote, setRejectNote] = useState("");
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
        setAcceptNote(d.status === "accepted" ? d.decision_note ?? "" : "");
        setRejectNote(d.status === "rejected" ? d.decision_note ?? "" : "");
        const parsed = parseScheduleNote(d.interview_schedule_note);
        // 2026-09-30(사용자 지시): 일정이 "한 번도 설정된 적 없을 때만" 오늘+7일(주말 제외)·
        // 14:00을 기본값으로 채운다. 과거 자유 텍스트(파싱 안 되는 값)가 이미 있으면 그건
        // 실제 결정 없이 남겨둔 메모일 수 있으므로, 없는 날짜를 지어내 붙이지 않는다 —
        // 실측 중 이 구분을 안 두면 옛 메모에 임의의 날짜가 섞여 붙는 결함을 발견해 수정.
        if (!d.interview_schedule_note) {
          setScheduleDate(defaultInterviewDate());
          setScheduleTime("14:00");
        } else {
          setScheduleDate(parsed.date);
          setScheduleTime(parsed.time);
        }
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

  // 면접 일정은 합격 시에만 의미가 있어 "합격 처리" 버튼만 막는다(불합격은 무관).
  const scheduleIncomplete = (!!scheduleDate) !== (!!scheduleTime);
  const acceptBlocked = saving || scheduleIncomplete || !acceptNote;
  const rejectBlocked = saving || !rejectNote;

  async function handleDecision(nextStatus: "accepted" | "rejected") {
    if (!accessToken || !params.id) return;
    if (nextStatus === "accepted" && acceptBlocked) return;
    if (nextStatus === "rejected" && rejectBlocked) return;
    setSaving(true);
    setActionError(null);
    try {
      const updated = await decideResume(accessToken, params.id, {
        status: nextStatus,
        decision_note: nextStatus === "accepted" ? acceptNote : rejectNote,
        interview_schedule_note: nextStatus === "accepted" ? composeScheduleNote(scheduleDate, scheduleTime, scheduleExtra) : undefined,
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
          <label htmlFor="accept-note">합격 안내 문구 (합격 처리 시 필수)</label>
          <select
            id="accept-note"
            value={acceptNote}
            onChange={(e) => setAcceptNote(e.target.value)}
            style={{ width: "100%" }}
          >
            <option value="">합격 안내 문구를 선택해주세요</option>
            {withCurrentAsOption(ACCEPT_TEMPLATES, acceptNote).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="reject-note">불합격 안내 문구 (불합격 처리 시 필수)</label>
          <select
            id="reject-note"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            style={{ width: "100%" }}
          >
            <option value="">불합격 안내 문구를 선택해주세요</option>
            {withCurrentAsOption(REJECT_TEMPLATES, rejectNote).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="schedule-date">면접 일정 안내 (합격 시에만 사용, 참고용이에요)</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              id="schedule-date"
              type="date"
              aria-label="면접 날짜"
              value={scheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
              style={{ flex: 1 }}
            />
            <select
              aria-label="면접 시(24시간 기준)"
              value={scheduleTime.split(":")[0] ?? ""}
              onChange={(e) => setScheduleTime(`${e.target.value}:${scheduleTime.split(":")[1] ?? "00"}`)}
              style={{ flex: 1 }}
            >
              {withCurrentAsOption(HOUR_OPTIONS, scheduleTime.split(":")[0] ?? "").map((h) => (
                <option key={h} value={h}>
                  {h}시
                </option>
              ))}
            </select>
            <select
              aria-label="면접 분"
              value={scheduleTime.split(":")[1] ?? ""}
              onChange={(e) => setScheduleTime(`${scheduleTime.split(":")[0] ?? "00"}:${e.target.value}`)}
              style={{ flex: 1 }}
            >
              {withCurrentAsOption(MINUTE_OPTIONS, scheduleTime.split(":")[1] ?? "").map((m) => (
                <option key={m} value={m}>
                  {m}분
                </option>
              ))}
            </select>
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
          <button type="button" className="submit-button" disabled={acceptBlocked} onClick={() => handleDecision("accepted")}>
            {saving ? "저장 중..." : "합격 처리"}
          </button>
          <button
            type="button"
            className="submit-button"
            style={{ background: "var(--color-text-secondary)" }}
            disabled={rejectBlocked}
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
            {detail.notified_at
              ? "판단 저장 시 시스템이 지원자에게 안내 메일을 자동으로 발송했습니다. 아래에서 발송된 내용을 다시 확인할 수 있어요."
              : "자동 발송이 아직 되지 않았습니다(메일 설정 누락 또는 발송 실패). 아래 내용을 복사해서 직접 보내신 뒤 '발송 완료로 표시'를 눌러주세요."}
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
