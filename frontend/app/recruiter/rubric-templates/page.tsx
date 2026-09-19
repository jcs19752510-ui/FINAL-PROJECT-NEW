"use client";

/**
 * [R-03] 질문지/루브릭 커스터마이징 — unit-13, Feature F, REQ-014.
 *
 * 04-ux-design.md v2 §2 [R-03] 명세: 템플릿 목록 + 템플릿 상세(이름, 평가 기준
 * 항목 리스트 — criteria_json을 구조화 폼으로 표현: 항목명+가중치/설명), 신규
 * 생성/수정/저장. 03-system-design.md §4.2 `/recruiter/rubric-templates`
 * GET/POST/PATCH 1:1 대응. 시스템 기본 템플릿(`is_system_default=true`)은 직접
 * 수정할 수 없고, 선택 시 그 내용을 그대로 새 템플릿 생성 폼에 채워 "복사해 시작"한다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  type RubricCriterion,
  type RubricTemplateOut,
  type UserOut,
  clearAccessToken,
  createRubricTemplate,
  getMe,
  listRubricTemplates,
  readAccessToken,
  updateRubricTemplate,
} from "@/lib/api";
import styles from "../recruiter.module.css";

function emptyCriterion(): RubricCriterion {
  return { name: "", weight: 0, description: "" };
}

export default function RubricTemplatesPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [templates, setTemplates] = useState<RubricTemplateOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formCriteria, setFormCriteria] = useState<RubricCriterion[]>([emptyCriterion()]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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
    if (!accessToken) return;
    listRubricTemplates(accessToken)
      .then(setTemplates)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "네트워크 오류로 목록을 불러오지 못했습니다.");
      });
  }

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter") return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, user]);

  function startNew() {
    setEditingId(null);
    setFormName("");
    setFormCriteria([emptyCriterion()]);
    setSaveError(null);
  }

  function startEdit(template: RubricTemplateOut) {
    // 시스템 기본 템플릿은 PATCH 대상이 아니므로 "복사해 시작"으로 처리한다
    // (editingId=null로 두어 저장 시 POST로 새 템플릿을 만든다).
    setEditingId(template.is_system_default ? null : template.id);
    setFormName(template.name);
    setFormCriteria(template.criteria.length > 0 ? template.criteria.map((c) => ({ ...c })) : [emptyCriterion()]);
    setSaveError(null);
  }

  function updateCriterion(index: number, patch: Partial<RubricCriterion>) {
    setFormCriteria((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  function addCriterion() {
    setFormCriteria((prev) => [...prev, emptyCriterion()]);
  }

  function removeCriterion(index: number) {
    setFormCriteria((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : prev));
  }

  async function handleSave() {
    if (!accessToken) return;
    const trimmedName = formName.trim();
    const cleanedCriteria = formCriteria
      .map((c) => ({ ...c, name: c.name.trim(), description: c.description.trim() }))
      .filter((c) => c.name.length > 0);

    if (trimmedName.length === 0) {
      setSaveError("템플릿 이름을 입력해주세요.");
      return;
    }
    if (cleanedCriteria.length === 0) {
      setSaveError("평가 기준을 최소 1개 이상 입력해주세요.");
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      if (editingId) {
        await updateRubricTemplate(accessToken, editingId, { name: trimmedName, criteria: cleanedCriteria });
      } else {
        await createRubricTemplate(accessToken, { name: trimmedName, criteria: cleanedCriteria });
      }
      startNew();
      reload();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
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
            질문지/루브릭 관리 화면은 채용담당자(recruiter) 계정만 접근할 수 있습니다.
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
      <Link href="/recruiter" className={styles.backLink}>
        &larr; 리포트 목록으로
      </Link>
      <h1>질문지/루브릭 커스터마이징</h1>
      <p className={styles.subtitle}>사전정의 템플릿 중 선택하거나 복사해 평가 기준을 최소한으로 편집할 수 있습니다.</p>

      {loadError && (
        <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
          {loadError}
        </div>
      )}

      {templates === null ? (
        <div className={styles.skeleton} aria-busy="true">
          목록을 불러오는 중입니다...
        </div>
      ) : (
        <div className={styles.rubricLayout}>
          <div>
            <div className={styles.detailHeader}>
              <h2>템플릿 목록</h2>
              <button type="button" className="submit-button" onClick={startNew}>
                새 템플릿 만들기
              </button>
            </div>
            {templates.length === 0 ? (
              <div className={styles.emptyText}>
                아직 만든 템플릿이 없습니다. 기본 템플릿을 복사해 시작하세요.
              </div>
            ) : (
              <ul className={styles.rubricList}>
                {templates.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      className={styles.rubricListItem}
                      onClick={() => startEdit(t)}
                    >
                      <span>{t.name}</span>
                      {t.is_system_default && <span className={styles.statusTag}>기본</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={styles.detailCard}>
            <h2>{editingId ? "템플릿 수정" : "새 템플릿"}</h2>

            <label className={styles.formLabel}>
              템플릿 이름
              <input
                className={styles.formInput}
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="예: 백엔드 신입 기본 템플릿"
              />
            </label>

            <div className={styles.criteriaHeader}>
              <span>평가 기준 항목</span>
              <button type="button" className={styles.linkButton} onClick={addCriterion}>
                + 항목 추가
              </button>
            </div>

            {formCriteria.map((c, i) => (
              <div key={i} className={styles.criteriaRow}>
                <input
                  className={styles.formInput}
                  value={c.name}
                  onChange={(e) => updateCriterion(i, { name: e.target.value })}
                  placeholder="항목명(예: 문제 해결력)"
                />
                <input
                  className={styles.formInputSmall}
                  type="number"
                  min={0}
                  max={100}
                  value={c.weight}
                  onChange={(e) => updateCriterion(i, { weight: Number(e.target.value) })}
                  placeholder="가중치"
                />
                <input
                  className={styles.formInput}
                  value={c.description}
                  onChange={(e) => updateCriterion(i, { description: e.target.value })}
                  placeholder="설명(선택)"
                />
                <button
                  type="button"
                  className={styles.linkButton}
                  onClick={() => removeCriterion(i)}
                  aria-label="항목 삭제"
                >
                  삭제
                </button>
              </div>
            ))}

            {saveError && (
              <div className="banner-error" role="alert" style={{ marginTop: 12 }}>
                {saveError}
              </div>
            )}

            <div style={{ marginTop: 16 }}>
              <button type="button" className="submit-button" onClick={handleSave} disabled={saving}>
                {saving ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
