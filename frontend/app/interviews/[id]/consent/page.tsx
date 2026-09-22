"use client";

/**
 * [C-04] 사전고지·동의 화면 (unit-15, Feature G 규제 컴플라이언스, REQ-031/032/033/034).
 *
 * 04-ux-design.md v2 §2 [C-04] 명세 그대로: 고지문을 끝까지 스크롤해야 필수
 * 체크박스(`ai_interview_notice`)가 활성화되고, 선택 체크박스(`biometric_voice`)는
 * 언제든 체크 가능하다. "동의하고 시작"은 필수 체크박스만 체크하면 활성화된다
 * (DEC-023 — 텍스트 전용 지원자는 생체정보 동의 없이 시작 가능).
 *
 * 이 화면은 `POST /consents`(unit-14, `backend/app/api/v1/consents.py`)와
 * `POST /interviews/{id}/start`(unit-2, `interviews.py`)를 그대로 소비만 한다 —
 * 두 백엔드 파일 모두 이번 유닛에서 수정하지 않았다.
 *
 * **범위 편차(unit-15-note.md §2 참고)**: 03-system-design.md가 정의한
 * `GET /interviews/{id}/pre-notice` 엔드포인트는 어떤 유닛도 구현하지 않았고, 이번
 * 유닛은 `interviews.py`를 수정할 수 없어 이 화면의 고지문은 정적 텍스트
 * (`lib/complianceContent.ts`)로 대체했다.
 */
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  type InterviewDetailOut,
  createConsent,
  getInterview,
  readAccessToken,
  startInterview,
} from "@/lib/api";
import { PRE_NOTICE_TEXT } from "@/lib/complianceContent";
import HomeLink from "@/components/HomeLink";
import styles from "./consent.module.css";

const SCROLL_END_THRESHOLD_PX = 24;

export default function ConsentNoticePage() {
  const params = useParams<{ id: string }>();
  const interviewId = params.id;
  const router = useRouter();

  const [accessToken] = useState<string | null>(() => readAccessToken());
  const [interview, setInterview] = useState<InterviewDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [scrolledToEnd, setScrolledToEnd] = useState(false);
  const [noticeChecked, setNoticeChecked] = useState(false);
  const [voiceChecked, setVoiceChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const noticeBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
    }
  }, [accessToken, router]);

  useEffect(() => {
    if (!accessToken || !interviewId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const detail = await getInterview(accessToken!, interviewId);
        if (cancelled) return;
        if (detail.status === "live" || detail.status === "paused") {
          // 이미 시작된 세션 — 이 화면을 다시 거칠 필요 없이 면접장으로 보낸다.
          router.replace(`/interviews/${interviewId}`);
          return;
        }
        if (detail.status !== "scheduled") {
          setLoadError("이 세션은 이미 종료되었거나 만료되어 사전고지 동의를 진행할 수 없습니다.");
          setLoading(false);
          return;
        }
        setInterview(detail);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            router.push("/login");
            return;
          }
          setLoadError(err.message);
        } else {
          setLoadError("네트워크 오류로 사전고지 정보를 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [accessToken, interviewId, router]);

  function handleNoticeScroll() {
    const el = noticeBoxRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom <= SCROLL_END_THRESHOLD_PX) {
      setScrolledToEnd(true);
    }
  }

  async function handleSubmit() {
    if (!accessToken || !interview || !noticeChecked || submitting) return;
    setSubmitting(true);
    setSubmitError(null);

    try {
      await createConsent(accessToken, "ai_interview_notice");

      if (voiceChecked) {
        // 선택 동의이므로 이 호출이 실패해도 시작 자체를 막지 않는다(§6.2, DEC-023 —
        // 실제 강제 검사는 /turns 음성 제출 시점에 별도로 이루어진다).
        try {
          await createConsent(accessToken, "biometric_voice");
        } catch {
          // 조용히 삼키지 않고 사용자에게 알리되, 필수 흐름은 계속 진행한다.
          setSubmitError(
            "생체정보(음성) 동의 등록에 실패했습니다. 필요하면 마이페이지에서 다시 등록할 수 있습니다 — 계속 진행합니다.",
          );
        }
      }

      await startInterview(accessToken, interview.id);
      router.push(`/interviews/${interview.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.code === "CONSENT_REQUIRED_NOTICE") {
          setNoticeChecked(false);
          setSubmitError("동의 처리가 반영되지 않았습니다. 필수 항목에 다시 동의한 뒤 시도해주세요.");
        } else if (err.status === 409) {
          setSubmitError(err.message);
        } else {
          setSubmitError(err.message);
        }
      } else {
        setSubmitError("네트워크 오류가 발생했습니다. 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>사전고지 내용을 불러오는 중입니다...</div>
      </div>
    );
  }

  if (loadError || !interview) {
    return (
      <div className={styles.page}>
        <div className="banner-error">{loadError ?? "면접 세션을 찾을 수 없습니다."}</div>
        <Link href="/">홈으로 돌아가기</Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <HomeLink />
      <h1>AI 면접 진행 사전고지 및 동의</h1>
      <p className={styles.subtitle}>
        면접을 시작하기 전, 아래 내용을 끝까지 확인해주세요. AI는 보조 도구이며 최종 채용 결정은
        사람이 내립니다.
      </p>

      <div
        className={styles.noticeBox}
        ref={noticeBoxRef}
        onScroll={handleNoticeScroll}
        role="region"
        aria-label="AI 면접 사전고지 전문"
        tabIndex={0}
      >
        {PRE_NOTICE_TEXT}
      </div>
      <p className={`${styles.scrollHint} ${scrolledToEnd ? styles["scrollHint--done"] : ""}`} aria-live="polite">
        {scrolledToEnd ? "고지문을 끝까지 확인했습니다." : "고지문을 끝까지 스크롤하면 아래 필수 동의를 체크할 수 있습니다."}
      </p>

      <div className={styles.checkboxRow}>
        <input
          type="checkbox"
          id="consent-notice"
          checked={noticeChecked}
          disabled={!scrolledToEnd}
          onChange={(e) => setNoticeChecked(e.target.checked)}
        />
        <label htmlFor="consent-notice">
          <span className={styles.badgeRequired}>* 필수</span>
          AI 면접 진행 및 평가 사실을 확인했으며, AI 평가는 참고용 보조 자료이고 최종 채용 결정은
          사람이 내린다는 점에 동의합니다.
        </label>
      </div>

      <div className={styles.checkboxRow}>
        <input
          type="checkbox"
          id="consent-voice"
          checked={voiceChecked}
          onChange={(e) => setVoiceChecked(e.target.checked)}
        />
        <label htmlFor="consent-voice">
          <span className={styles.badgeOptional}>* 선택</span>
          생체정보(음성) 수집에 동의합니다.
          <span className={styles.helperText}>
            음성으로도 답변하실 계획이면 지금 동의하시면 면접 중 별도 절차 없이 바로 진행됩니다.
            나중에 면접장에서 음성 버튼을 처음 누를 때 동의를 받을 수도 있습니다.
          </span>
        </label>
      </div>

      {submitError && (
        <div className="banner-error" role="alert">
          {submitError}
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className="submit-button"
          disabled={!noticeChecked || submitting}
          onClick={handleSubmit}
        >
          {submitting ? "처리 중..." : "동의하고 시작"}
        </button>
      </div>

      <p className={styles.declineHint}>
        동의하지 않으면 면접을 시작할 수 없습니다. <Link href="/">지원자 홈으로 돌아가기</Link>
      </p>
      <Link href="/legal" className={styles.legalLink}>
        법률/컴플라이언스 고지 전문 보기 (REQ-034)
      </Link>
    </div>
  );
}
