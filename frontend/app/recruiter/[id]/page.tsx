"use client";

/**
 * [R-02] 리포트 상세(열람 전용) — unit-12, Feature F, REQ-011.
 *
 * 04-ux-design.md v2 §2 [R-02] 명세와 편차: 캐노니컬 엔드포인트는
 * `GET /interviews/{id}/report`이나, 이 화면은 여전히 recruiter 전용
 * `GET /recruiter/reports/{interview_id}`(backend/app/api/v1/recruiter.py)를 쓴다 —
 * 그 엔드포인트가 Feature E 도입 이후 캐노니컬 로직의 얇은 래퍼로 축소되어 실제
 * 데이터는 동일하다(백엔드 모듈 docstring 참고). `report_available=false`일 때는
 * 여전히 상태 안내만 표시한다(가짜 데이터 금지 원칙 유지).
 * REQ-034 법률자문 고지 배너는 리포트 본문 유무와 무관하게 항상 노출한다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  type RecruiterReportDetailOut,
  type RubricTemplateOut,
  type UserOut,
  assignRubricTemplate,
  clearAccessToken,
  getMe,
  getRecruiterReportDetail,
  listRubricTemplates,
  readAccessToken,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RubricEvidenceSection from "@/components/RubricEvidenceSection";
import styles from "../recruiter.module.css";

const STATUS_LABEL: Record<RecruiterReportDetailOut["status"], string> = {
  scheduled: "예정",
  live: "진행 중",
  paused: "일시중지",
  completed: "완료",
  expired: "만료",
};

const RECOMMENDATION_LABEL: Record<string, string> = {
  recommend: "긍정적",
  neutral: "중립",
  not_recommend: "부정적",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function RecruiterReportDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [detail, setDetail] = useState<RecruiterReportDetailOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // v15(03-system-design v4 §4.6 (2), 04-ux-design [R-02], unit-37): 채점 템플릿
  // 변경 컨트롤. 브라우저 confirm()은 이 플랫폼에서 동작하지 않아(artifact/webview
  // 계열 공통 제약) 화면 내 확인 문구로 대체한다(04 명세 그대로).
  const [templates, setTemplates] = useState<RubricTemplateOut[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [confirmingApply, setConfirmingApply] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

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

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter" || !params.id) return;
    getRecruiterReportDetail(accessToken, params.id)
      .then((d) => {
        setDetail(d);
        if (d.rubric) setSelectedTemplateId(d.rubric.template_id);
      })
      .catch((err: unknown) => {
        setLoadError(
          err instanceof ApiError ? err.message : "네트워크 오류로 리포트를 불러오지 못했습니다.",
        );
      })
      .finally(() => setLoading(false));
  }, [accessToken, user, params.id, reloadNonce]);

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter") return;
    listRubricTemplates(accessToken)
      .then(setTemplates)
      .catch(() => {
        // 템플릿 목록 실패는 조용히 무시 — 리포트 본문 표시는 그대로 진행(부가 기능).
      });
  }, [accessToken, user]);

  async function handleApplyTemplate() {
    if (!accessToken || !params.id || !selectedTemplateId || applying) return;
    setApplying(true);
    setApplyError(null);
    setApplyMessage(null);
    try {
      const result = await assignRubricTemplate(accessToken, params.id, selectedTemplateId);
      if (result.job_id) {
        setApplyMessage("채점 중입니다. 잠시 후 새로고침하면 결과가 반영됩니다.");
      } else {
        setApplyMessage("적용됨");
      }
      setConfirmingApply(false);
      setReloadNonce((n) => n + 1);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setApplyError("이미 채점이 진행 중입니다.");
      } else if (err instanceof ApiError && err.status === 503) {
        setApplyError("지금 처리 대기 중인 작업이 많습니다. 잠시 후 다시 시도해 주세요.");
      } else {
        setApplyError(err instanceof ApiError ? err.message : "적용 중 오류가 발생했습니다.");
      }
      setConfirmingApply(false);
    } finally {
      setApplying(false);
    }
  }

  if (authLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>불러오는 중...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>로그인이 필요합니다</h1>
          <Link href="/login" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            로그인하러 가기
          </Link>
        </div>
      </div>
    );
  }

  if (user.role !== "recruiter") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>
            리포트 상세 화면은 채용담당자(recruiter) 계정만 접근할 수 있습니다.
          </p>
          <Link href="/" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            홈으로
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <HomeLink />
      <Link href="/recruiter" className={styles.backLink}>
        &larr; 목록으로
      </Link>

      {loading ? (
        <div className={styles.skeleton} aria-busy="true">
          리포트를 불러오는 중입니다...
        </div>
      ) : loadError || !detail ? (
        <div className="banner-error" role="alert">
          {loadError ?? "리포트를 찾을 수 없습니다."}
        </div>
      ) : (
        <div className={styles.detailCard}>
          <div className={styles.detailHeader}>
            <h2>{detail.candidate_name}</h2>
            <span className={styles.statusTag}>{STATUS_LABEL[detail.status]}</span>
          </div>
          <div className={styles.metaRow}>
            <span>이메일: {detail.candidate_email}</span>
            <span>응시 시작: {formatDateTime(detail.started_at)}</span>
            <span>응시 종료: {formatDateTime(detail.ended_at)}</span>
            <span>종합 점수: {detail.overall_score ?? "-"}</span>
          </div>

          {templates.length > 0 && (
            <div style={{ margin: "12px 0", padding: "10px 12px", border: "1px solid var(--color-border, #e5e5e5)", borderRadius: 8 }}>
              <label htmlFor="rubric-template-select" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                채점 템플릿
                {detail.rubric && !templates.some((t) => t.id === detail.rubric!.template_id) && (
                  <span style={{ color: "var(--color-text-secondary)", marginLeft: 6 }}>
                    (현재: {detail.rubric.name} — 다른 담당자 템플릿)
                  </span>
                )}
              </label>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <select
                  id="rubric-template-select"
                  value={selectedTemplateId}
                  onChange={(e) => {
                    setSelectedTemplateId(e.target.value);
                    setConfirmingApply(false);
                  }}
                >
                  {!detail.rubric && <option value="">선택...</option>}
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.is_system_default ? " (기본)" : ""}
                    </option>
                  ))}
                </select>
                {!confirmingApply ? (
                  <button
                    type="button"
                    className="submit-button"
                    disabled={!selectedTemplateId}
                    onClick={() => setConfirmingApply(true)}
                  >
                    이 템플릿으로 다시 채점
                  </button>
                ) : (
                  <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                    리포트가 새 기준으로 다시 생성되며 지원자 화면에도 반영됩니다.
                    <button type="button" className="submit-button" disabled={applying} onClick={handleApplyTemplate}>
                      {applying ? "적용 중..." : "다시 채점"}
                    </button>
                    <button type="button" onClick={() => setConfirmingApply(false)} disabled={applying}>
                      취소
                    </button>
                  </span>
                )}
              </div>
              {applyMessage && <div className="banner-info" style={{ marginTop: 8 }}>{applyMessage}</div>}
              {applyError && <div className="banner-error" style={{ marginTop: 8 }}>{applyError}</div>}
            </div>
          )}

          <div className={styles.reportBody}>
            {!detail.report_available ? (
              <div className={styles.emptyText}>{detail.message}</div>
            ) : (
              <>
                {(detail.technical_score !== null ||
                  detail.communication_score !== null ||
                  detail.cultural_fit_score !== null) && (
                  <div style={{ marginBottom: 16 }}>
                    <div>기술 이해도: {detail.technical_score ?? "-"} / 5</div>
                    <div>의사소통: {detail.communication_score ?? "-"} / 5</div>
                    <div>조직 적합도: {detail.cultural_fit_score ?? "-"} / 5</div>
                    {detail.overall_recommendation && (
                      <div>AI 참고 의견: {RECOMMENDATION_LABEL[detail.overall_recommendation]}</div>
                    )}
                  </div>
                )}
                <RubricEvidenceSection rubric={detail.rubric} />

                {detail.star ? (
                  <div>
                    <p><strong>상황(Situation)</strong><br />{detail.star.situation}</p>
                    <p><strong>과제(Task)</strong><br />{detail.star.task}</p>
                    <p><strong>행동(Action)</strong><br />{detail.star.action}</p>
                    <p><strong>결과(Result)</strong><br />{detail.star.result}</p>
                  </div>
                ) : (
                  detail.summary_text && <p style={{ whiteSpace: "pre-wrap" }}>{detail.summary_text}</p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <div className={styles.disclaimerBanner}>
        본 리포트/평가는 참고용이며 법적 효력이 없습니다. 채용 의사결정에 대한 법률적 판단은
        본 서비스가 대신하지 않습니다.
      </div>
    </div>
  );
}
