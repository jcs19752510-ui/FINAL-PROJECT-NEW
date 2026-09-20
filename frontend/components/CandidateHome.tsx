"use client";

/**
 * [C-03] 지원자 홈(대시보드) — unit-19, Feature B, REQ-002 (04-ux-design.md §2 [C-03]).
 *
 * `GET /interviews`(내 면접 목록)로 "최근 면접" 카드, 중단 세션 배너, "리포트 준비 완료"
 * 배지를 그린다. 목록 조회 실패/로딩은 카드 영역에만 영향을 주고, "새 면접 시작" CTA는
 * 어떤 상태에서도 동작해야 한다(핵심 기능 우선, 04 [C-03] 에러 상태).
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  type InterviewListItemOut,
  type UserOut,
  clearAccessToken,
  listMyInterviews,
} from "@/lib/api";
import styles from "./CandidateHome.module.css";

// 설계서 미명시 표시 정책(비가역성 낮음): 홈은 "최근 면접"이므로 최근 N건만 그린다.
// 중단 세션 배너는 전체 응답에서 판단하므로 이 제한의 영향을 받지 않는다.
const RECENT_LIMIT = 10;

const STATUS_LABEL: Record<InterviewListItemOut["status"], string> = {
  scheduled: "시작 전",
  live: "진행 중",
  paused: "중단됨",
  completed: "완료",
  expired: "만료",
};

const REPORT_LABEL: Partial<Record<InterviewListItemOut["report_status"], string>> = {
  queued: "리포트 생성 중",
  ready: "리포트 준비 완료",
  failed: "리포트 생성 실패",
};

// 리포트 화면([C-10]/[C-11])은 이 유닛 범위 밖이라 배지는 링크 없이 상태만 알린다.
function itemHref(item: InterviewListItemOut): string {
  return item.status === "scheduled" ? `/interviews/${item.id}/consent` : `/interviews/${item.id}`;
}

function itemActionLabel(item: InterviewListItemOut): string {
  if (item.status === "scheduled") return "사전고지 확인하고 시작";
  if (item.resumable) return "이어서 진행";
  return "대화 이력 보기";
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

type ListState =
  | { kind: "loading" }
  | { kind: "ready"; items: InterviewListItemOut[] }
  | { kind: "error"; message: string };

interface Props {
  user: UserOut;
  accessToken: string;
  onLogout: () => void;
  onSessionExpired: () => void;
}

export default function CandidateHome({ user, accessToken, onLogout, onSessionExpired }: Props) {
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listMyInterviews(accessToken)
      .then((items) => {
        if (!cancelled) setState({ kind: "ready", items });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          clearAccessToken();
          onSessionExpired();
          return;
        }
        setState({ kind: "error", message: "불러오지 못했습니다. 다시 시도해주세요." });
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, reloadKey, onSessionExpired]);

  function retry() {
    setState({ kind: "loading" });
    setReloadKey((k) => k + 1);
  }

  const items = state.kind === "ready" ? state.items : [];
  const resumables = items.filter((item) => item.resumable);
  const isEmpty = state.kind === "ready" && items.length === 0;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>{user.name}님, 환영합니다</h1>
        <nav className={styles.nav} aria-label="계정">
          <Link href="/mypage">마이페이지</Link>
          <button type="button" className={styles.linkButton} onClick={onLogout}>
            로그아웃
          </button>
        </nav>
      </header>

      <section aria-labelledby="home-start-heading" className={styles.ctaSection}>
        <h2 id="home-start-heading" className={styles.srOnly}>
          새 면접
        </h2>
        <Link href="/interviews/new" className={`submit-button ${styles.cta} ${isEmpty ? styles.ctaEmphasis : ""}`}>
          새 면접 시작
        </Link>
      </section>

      {resumables.length > 0 && (
        <section className={styles.resumeBanner} role="status" aria-label="중단된 면접 안내">
          <div>
            <strong>중단된 면접이 있습니다.</strong>
            <span className={styles.resumeSub}>
              {formatDateTime(resumables[0].started_at ?? resumables[0].created_at)}에 시작한 면접을 이어서 진행할 수 있어요.
              {resumables.length > 1 ? ` (외 ${resumables.length - 1}건은 아래 목록에서 확인)` : ""}
            </span>
          </div>
          <Link href={itemHref(resumables[0])} className={styles.resumeLink}>
            이어서 진행
          </Link>
        </section>
      )}

      <section aria-labelledby="home-recent-heading" className={styles.listSection}>
        <h2 id="home-recent-heading">최근 면접</h2>

        {state.kind === "loading" && (
          <ul className={styles.list} aria-busy="true" aria-label="면접 목록을 불러오는 중">
            {[0, 1, 2].map((i) => (
              <li key={i} className={`${styles.card} ${styles.skeletonCard}`} aria-hidden="true" />
            ))}
          </ul>
        )}

        {state.kind === "error" && (
          <div className={styles.inlineError} role="alert">
            <span>{state.message}</span>
            <button type="button" className={styles.retryButton} onClick={retry}>
              다시 시도
            </button>
          </div>
        )}

        {isEmpty && (
          <p className={styles.emptyText}>아직 진행한 면접이 없습니다. 첫 모의면접을 시작해보세요.</p>
        )}

        {state.kind === "ready" && items.length > 0 && (
          <>
            <ul className={styles.list}>
              {items.slice(0, RECENT_LIMIT).map((item) => {
                const reportLabel = REPORT_LABEL[item.report_status];
                return (
                  <li key={item.id} className={styles.card}>
                    <div className={styles.cardMain}>
                      <div className={styles.cardDate}>{formatDateTime(item.started_at ?? item.created_at)}</div>
                      <div className={styles.tags}>
                        <span className={`${styles.tag} ${styles[`tag_${item.status}`]}`}>{STATUS_LABEL[item.status]}</span>
                        {reportLabel && (
                          <span className={`${styles.tag} ${styles[`report_${item.report_status}`]}`}>{reportLabel}</span>
                        )}
                      </div>
                      <div className={styles.score}>
                        종합 점수: {item.overall_score !== null ? item.overall_score : "아직 없음"}
                      </div>
                    </div>
                    <Link
                      href={itemHref(item)}
                      className={styles.cardAction}
                      aria-label={`${formatDateTime(item.started_at ?? item.created_at)} 면접 ${itemActionLabel(item)}`}
                    >
                      {itemActionLabel(item)}
                    </Link>
                  </li>
                );
              })}
            </ul>
            {items.length > RECENT_LIMIT && (
              <p className={styles.moreNote}>최근 {RECENT_LIMIT}건만 표시합니다 (전체 {items.length}건).</p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
