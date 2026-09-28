"use client";

/**
 * [C-11]/[R-02] 리포트 상세 — 지원자/채용담당자 공용 (Feature E, REQ-009/010/012,
 * 03-system-design.md §4.2 캐노니컬 `GET /interviews/{id}/report`).
 *
 * 사용자 요청(2026-09-21)으로 신설: 리포트 생성 기능 자체가 이번에 처음 구현됐고,
 * 지원자가 자기 결과를 볼 화면이 아예 없었다. 03-design §4.2가 명시한 실시간 통지
 * 경로는 WebSocket `report_ready`이지만, 면접장(interviews/[id]/page.tsx)의 WS
 * 연결은 세션이 `completed`로 전환되는 순간 닫히도록 이미 구현되어 있어(그 효과가
 * `status`가 live/paused일 때만 열려 있음) 이 화면까지 그 연결을 그대로 이어받기는
 * 어렵다. §4.3이 "연결이 끊긴 뒤에는 GET으로 재확인" 폴백을 이미 명시적으로 허용하므로,
 * 이 화면은 WS 없이 폴링만으로 구현한다(설계서가 허용한 대체 경로 — 임의 축소가 아님).
 *
 * 렌더링 보안(REQ-036 새니타이즈 대상, `star`/`summary_text`/`details`는 LLM이 지원자
 * 답변을 참고해 생성한 텍스트라 원본에 있던 문자열이 섞여 나올 수 있음): 이 컴포넌트는
 * `dangerouslySetInnerHTML`을 전혀 쓰지 않고 JSX 텍스트 보간(`{text}`)만 사용한다 —
 * React가 모든 텍스트 노드를 자동 이스케이프하므로 별도 HTML 새니타이저(dompurify 등)
 * 없이도 XSS가 원천적으로 불가능하다(화이트리스트 새니타이즈보다 강한 보장).
 */
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type ReportOut, getReport, readAccessToken, regenerateReport } from "@/lib/api";
import RubricEvidenceSection from "@/components/RubricEvidenceSection";

const POLL_INTERVAL_MS = 3000;

const RECOMMENDATION_LABEL: Record<string, string> = {
  recommend: "긍정적",
  neutral: "중립",
  not_recommend: "부정적",
};

// 원안(REQ-F-006/007) 복원분(2026-09-22 사용자 명시 승인) — REQ-031과 긴장 관계라
// disclaimer 없이 단독 노출하지 않는다(app/models/evaluation_report.py 모듈 docstring,
// backend/app/schemas/interview.py 참고). 배포 전 법무 검토 필요.
const PASS_FAIL_LABEL: Record<string, string> = {
  pass: "합격 쪽에 가까움",
  fail: "불합격 쪽에 가까움",
  borderline: "판단 보류(애매함)",
};

function ScoreRow({ label, score }: { label: string; score: number | null }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0" }}>
      <span>{label}</span>
      <strong>{score !== null ? `${score} / 5` : "-"}</strong>
    </div>
  );
}

export default function InterviewReportPage() {
  const params = useParams<{ id: string }>();
  const interviewId = params.id;
  const router = useRouter();

  const [accessToken] = useState<string | null>(() => readAccessToken());
  const [report, setReport] = useState<ReportOut | null>(null);
  const [processing, setProcessing] = useState(false);
  const [notReadyMessage, setNotReadyMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  // regenerate 버튼이 폴링 이펙트를 다시 트리거하기 위한 값(값 자체는 쓰지 않음) —
  // 면접장 화면의 기존 로딩 이펙트 패턴(로더를 이펙트 내부 지역 함수로 두고 cancelled
  // 플래그로 정리)을 그대로 따른다.
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
    }
  }, [accessToken, router]);

  useEffect(() => {
    if (!accessToken || !interviewId) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    async function load() {
      try {
        const result = await getReport(accessToken!, interviewId);
        if (cancelled) return;
        if (result.status === "processing") {
          setProcessing(true);
          setFailed(false);
          setNotReadyMessage(null);
          timeoutId = setTimeout(load, POLL_INTERVAL_MS);
          return;
        }
        setProcessing(false);
        setFailed(false);
        setNotReadyMessage(null);
        setReport(result.report);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            router.push("/login");
            return;
          }
          if (err.status === 409 && err.code === "REPORT_GENERATION_FAILED") {
            setFailed(true);
            setProcessing(false);
            return;
          }
          if (err.status === 409) {
            // report_status=none — 면접이 아직 종료되지 않음.
            setNotReadyMessage(err.message);
            setProcessing(false);
            return;
          }
          setLoadError(err.message);
        } else {
          setLoadError("네트워크 오류로 리포트를 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [accessToken, interviewId, router, retryNonce]);

  async function handleRegenerate() {
    if (!accessToken || regenerating) return;
    setRegenerating(true);
    try {
      await regenerateReport(accessToken, interviewId);
      setFailed(false);
      setProcessing(true);
      setRetryNonce((n) => n + 1);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "재시도 요청 중 오류가 발생했습니다.");
    } finally {
      setRegenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p>리포트를 불러오는 중입니다...</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="banner-error">{loadError}</div>
          <Link href={`/interviews/${interviewId}`}>면접장으로 돌아가기</Link>
        </div>
      </div>
    );
  }

  if (notReadyMessage) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>리포트 없음</h1>
          <div className="banner-info">{notReadyMessage}</div>
          <Link href={`/interviews/${interviewId}`}>면접장으로 돌아가기</Link>
        </div>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>리포트 생성 실패</h1>
          <div className="banner-error">리포트 생성에 실패했습니다.</div>
          <button type="button" className="submit-button" disabled={regenerating} onClick={handleRegenerate}>
            {regenerating ? "재시도 중..." : "다시 생성하기"}
          </button>
        </div>
      </div>
    );
  }

  if (processing || !report) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>리포트 생성 중</h1>
          <div className="banner-info">
            AI가 면접 대화를 분석해 리포트를 작성하고 있습니다. 잠시만 기다려주세요 (자동으로
            갱신됩니다).
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: 640 }}>
        <h1>면접 리포트</h1>

        <div style={{ margin: "16px 0", textAlign: "center" }}>
          <div style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>종합 점수</div>
          <div style={{ fontSize: 40, fontWeight: 700 }}>
            {report.overall_score !== null ? report.overall_score : "-"}
            <span style={{ fontSize: 16, fontWeight: 400 }}> / 5</span>
          </div>
          {report.overall_recommendation && (
            <span className="status-badge">
              AI 참고 의견: {RECOMMENDATION_LABEL[report.overall_recommendation] ?? report.overall_recommendation}
            </span>
          )}
          {report.pass_fail_recommendation && (
            <div style={{ marginTop: 8 }}>
              <span className="status-badge" style={{ background: "var(--color-warning-bg, #fdf1de)" }}>
                ⚠ 참고용 합격/불합격 의견:{" "}
                {PASS_FAIL_LABEL[report.pass_fail_recommendation] ?? report.pass_fail_recommendation}
              </span>
            </div>
          )}
        </div>

        {(report.technical_score !== null ||
          report.communication_score !== null ||
          report.cultural_fit_score !== null) && (
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 16 }}>세부 점수</h2>
            <ScoreRow label="기술 이해도" score={report.technical_score} />
            <ScoreRow label="의사소통" score={report.communication_score} />
            <ScoreRow label="조직 적합도" score={report.cultural_fit_score} />
          </section>
        )}

        <RubricEvidenceSection rubric={report.rubric} />

        {report.star ? (
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 16 }}>대화 요약 (STAR)</h2>
            <p><strong>상황(Situation)</strong><br />{report.star.situation}</p>
            <p><strong>과제(Task)</strong><br />{report.star.task}</p>
            <p><strong>행동(Action)</strong><br />{report.star.action}</p>
            <p><strong>결과(Result)</strong><br />{report.star.result}</p>
          </section>
        ) : (
          report.summary_text && (
            <section style={{ marginBottom: 20 }}>
              <h2 style={{ fontSize: 16 }}>총평</h2>
              <p style={{ whiteSpace: "pre-wrap" }}>{report.summary_text}</p>
            </section>
          )
        )}

        <div className="banner-info" role="note">
          {report.disclaimer}
        </div>

        <div style={{ marginTop: 24 }}>
          <Link href={`/interviews/${interviewId}`}>면접장으로 돌아가기</Link>
          {" · "}
          <Link href="/">홈으로</Link>
        </div>
      </div>
    </div>
  );
}
