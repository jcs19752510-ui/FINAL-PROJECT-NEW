"use client";

/**
 * [C-13] 마이페이지 — 개인정보/동의 관리 (unit-15, Feature G, REQ-030/033).
 *
 * 04-ux-design.md v2 §2 [C-13] 명세 그대로: `GET /auth/me`, `GET /users/me/consents`,
 * `POST /consents/{id}/revoke`, `DELETE /users/me/biometric-data`,
 * `GET /users/me/deletion-requests`(모두 unit-14 `backend/app/api/v1/consents.py`,
 * unit-1 `auth.py` 소비) — 어떤 백엔드 파일도 이 유닛에서 수정하지 않았다.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  type ConsentOut,
  type ConsentType,
  type DeletionRequestOut,
  type UserOut,
  clearAccessToken,
  getMe,
  listMyConsents,
  listMyDeletionRequests,
  readAccessToken,
  requestBiometricDataDeletion,
  revokeConsent,
} from "@/lib/api";
import styles from "./mypage.module.css";

const CONSENT_LABELS: Record<ConsentType, string> = {
  ai_interview_notice: "AI 면접 진행/평가 사전고지",
  biometric_voice: "생체정보(음성) 수집",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function MyPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [consents, setConsents] = useState<ConsentOut[]>([]);
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequestOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [confirmingDeletion, setConfirmingDeletion] = useState(false);
  const [requestingDeletion, setRequestingDeletion] = useState(false);

  const loadAll = useCallback(
    async (token: string) => {
      setLoading(true);
      setLoadError(null);
      try {
        const [me, consentList, deletionList] = await Promise.all([
          getMe(token),
          listMyConsents(token),
          listMyDeletionRequests(token),
        ]);
        setUser(me);
        setConsents(consentList);
        setDeletionRequests(deletionList);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 401) {
            clearAccessToken();
            router.push("/login");
            return;
          }
          setLoadError(err.message);
        } else {
          setLoadError("네트워크 오류로 마이페이지 정보를 불러오지 못했습니다.");
        }
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
      return;
    }
    async function run() {
      await loadAll(accessToken!);
    }
    run();
  }, [accessToken, loadAll, router]);

  async function handleRevoke(consentId: string) {
    if (!accessToken) return;
    setRevokingId(consentId);
    setActionError(null);
    try {
      await revokeConsent(accessToken, consentId);
      await loadAll(accessToken);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "동의 철회 중 오류가 발생했습니다.");
    } finally {
      setRevokingId(null);
    }
  }

  async function handleConfirmDeletion() {
    if (!accessToken) return;
    setRequestingDeletion(true);
    setActionError(null);
    try {
      await requestBiometricDataDeletion(accessToken);
      setConfirmingDeletion(false);
      await loadAll(accessToken);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "삭제 요청 중 오류가 발생했습니다.");
    } finally {
      setRequestingDeletion(false);
    }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>마이페이지를 불러오는 중입니다...</div>
      </div>
    );
  }

  if (loadError || !user) {
    return (
      <div className={styles.page}>
        <div className="banner-error">{loadError ?? "사용자 정보를 찾을 수 없습니다."}</div>
        <button type="button" className="submit-button" onClick={() => accessToken && loadAll(accessToken)}>
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1>마이페이지</h1>
      <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
        동의 이력 관리, 생체정보(음성) 삭제 요청은 여기서 처리할 수 있습니다.
      </p>

      <section className={styles.section}>
        <h2>계정 정보</h2>
        <div className={styles.accountCard}>
          <div>이름: {user.name}</div>
          <div>이메일: {user.email}</div>
        </div>
      </section>

      {actionError && (
        <div className="banner-error" role="alert" style={{ marginTop: 16 }}>
          {actionError}
        </div>
      )}

      <section className={styles.section}>
        <h2>동의 이력</h2>
        {consents.length === 0 ? (
          <div className={styles.emptyText}>아직 동의 내역이 없습니다.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>동의 항목</th>
                <th>동의 일시</th>
                <th>상태</th>
                <th>동의 철회</th>
              </tr>
            </thead>
            <tbody>
              {consents.map((c) => {
                const active = c.revoked_at === null;
                return (
                  <tr key={c.id}>
                    <td>{CONSENT_LABELS[c.consent_type] ?? c.consent_type}</td>
                    <td>{formatDateTime(c.granted_at)}</td>
                    <td>
                      {active ? (
                        <span className={`${styles.statusTag} ${styles["statusTag--active"]}`}>동의함</span>
                      ) : (
                        <span className={`${styles.statusTag} ${styles["statusTag--revoked"]}`}>
                          철회됨 ({formatDateTime(c.revoked_at)})
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={styles.revokeButton}
                        disabled={!active || revokingId === c.id}
                        onClick={() => handleRevoke(c.id)}
                      >
                        {revokingId === c.id ? "철회 중..." : "철회"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className={styles.section}>
        <h2>생체정보(음성) 삭제 요청</h2>
        <div className={styles.deleteRequestBox}>
          <p style={{ margin: "0 0 8px", fontSize: 14 }}>
            음성 데이터의 즉시 삭제를 요청할 수 있습니다. 진행 중인 면접이 있다면 삭제 요청 후
            해당 면접은 텍스트 전용으로 전환됩니다.
          </p>
          {!confirmingDeletion ? (
            <button type="button" className={styles.revokeButton} onClick={() => setConfirmingDeletion(true)}>
              생체정보 즉시 삭제 요청
            </button>
          ) : (
            <div>
              <strong>정말 생체정보(음성) 삭제를 요청하시겠습니까?</strong>
              <div className={styles.confirmRow}>
                <button
                  type="button"
                  className={styles.confirmYes}
                  disabled={requestingDeletion}
                  onClick={handleConfirmDeletion}
                >
                  {requestingDeletion ? "요청 중..." : "확인"}
                </button>
                <button
                  type="button"
                  className={styles.confirmNo}
                  disabled={requestingDeletion}
                  onClick={() => setConfirmingDeletion(false)}
                >
                  취소
                </button>
              </div>
            </div>
          )}
        </div>

        <h2 style={{ fontSize: 15 }}>삭제 요청 이력</h2>
        {deletionRequests.length === 0 ? (
          <div className={styles.emptyText}>아직 삭제 요청 내역이 없습니다.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>대상</th>
                <th>요청 일시</th>
                <th>처리 상태</th>
              </tr>
            </thead>
            <tbody>
              {deletionRequests.map((d) => (
                <tr key={d.id}>
                  <td>{d.target === "biometric_only" ? "생체정보(음성)" : "전체 계정"}</td>
                  <td>{formatDateTime(d.requested_at)}</td>
                  <td>
                    {d.status === "completed" ? (
                      <span className={`${styles.statusTag} ${styles["statusTag--completed"]}`}>
                        처리 완료 ({formatDateTime(d.completed_at)})
                      </span>
                    ) : (
                      <span className={`${styles.statusTag} ${styles["statusTag--pending"]}`}>
                        처리 중 — 24시간 이내 완료 예정
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div style={{ marginTop: 32 }}>
        <Link href="/">홈으로 돌아가기</Link>
        {" · "}
        <Link href="/legal">법률/컴플라이언스 고지</Link>
      </div>
    </div>
  );
}
