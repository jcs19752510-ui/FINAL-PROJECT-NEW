/**
 * 채용담당자 [R-02] 리포트 상세 — 최종 합격/불합격 처리 화면 검증 (면접 `completed` 건).
 * 백엔드 없이 API 를 page.route 로 모킹한다(서버 로직은 backend/tests/final_decision 이 검증).
 * 실행: cd frontend && E2E_BASE_URL=http://127.0.0.1:3011 npx playwright test e2e/recruiter-final
 */
import { expect, test, type Page } from "@playwright/test";

const ID = "00000000-0000-0000-0000-0000000000a1";
const ACCEPT_NOTE = "최종 합격을 진심으로 축하드립니다. 함께하게 되어 기쁩니다.";
const REJECT_NOTE = "아쉽게도 이번 채용에서는 최종 합격에 이르지 못했습니다. 좋은 결과로 다시 뵙기를 바랍니다.";

type State = {
  final_decision: "accepted" | "rejected" | null;
  final_decision_note: string | null;
  final_decided_at: string | null;
  final_notified_at: string | null;
};

function detail(status: string, s: State) {
  return {
    interview_id: ID,
    candidate_name: "정찬성",
    candidate_email: "cand@example.com",
    status,
    report_status: "none",
    started_at: null,
    ended_at: null,
    overall_score: null,
    report_available: false,
    message: "아직 리포트 생성이 요청되지 않았습니다.",
    technical_score: null,
    communication_score: null,
    cultural_fit_score: null,
    overall_recommendation: null,
    pass_fail_recommendation: null,
    star: null,
    summary_text: null,
    details: null,
    rubric: null,
    ...s,
  };
}

interface Opts {
  status?: string;
  role?: string;
  initial?: Partial<State>;
  notifyOnDecide?: boolean;
  patchStatus?: number;
}

async function setup(page: Page, opts: Opts = {}) {
  const state: State = {
    final_decision: null,
    final_decision_note: null,
    final_decided_at: null,
    final_notified_at: null,
    ...opts.initial,
  };
  const calls = { patch: [] as unknown[], draft: 0, mark: 0, detail: 0 };
  await page.addInitScript(() => sessionStorage.setItem("access_token", "fake"));
  await page.route("**/api/v1/auth/me", (r) =>
    r.fulfill({ json: { id: "u1", email: "r@example.com", name: "채용", role: opts.role ?? "recruiter", created_at: "2026-01-01T00:00:00Z" } }),
  );
  await page.route("**/api/v1/recruiter/rubric-templates", (r) => r.fulfill({ json: [] }));
  await page.route(`**/api/v1/recruiter/reports/${ID}`, (r) => {
    calls.detail++;
    return r.fulfill({ json: detail(opts.status ?? "completed", state) });
  });
  await page.route(`**/api/v1/recruiter/reports/${ID}/final-decision`, (r) => {
    const body = r.request().postDataJSON();
    calls.patch.push(body);
    if (opts.patchStatus && opts.patchStatus !== 200) {
      if (opts.patchStatus === 409) {
        state.final_decision = "accepted";
        state.final_decision_note = ACCEPT_NOTE;
        state.final_decided_at = "2026-10-07T01:00:00Z";
      }
      return r.fulfill({ status: opts.patchStatus, json: { detail: "이미 최종 결과가 처리되어 변경할 수 없습니다." } });
    }
    state.final_decision = body.status;
    state.final_decision_note = body.decision_note;
    state.final_decided_at = "2026-10-07T01:00:00Z";
    state.final_notified_at = opts.notifyOnDecide ? "2026-10-07T01:00:01Z" : null;
    return r.fulfill({ json: { interview_id: ID, ...state } });
  });
  await page.route(`**/api/v1/recruiter/reports/${ID}/final-notification-draft`, (r) => {
    calls.draft++;
    return r.fulfill({
      json: {
        to_email: "cand@example.com",
        subject: state.final_decision === "accepted" ? "[채용 안내] 최종 합격 안내" : "[채용 안내] 최종 결과 안내",
        body: `정찬성님, 안녕하세요.\n\n${state.final_decision_note}`,
      },
    });
  });
  await page.route(`**/api/v1/recruiter/reports/${ID}/final-mark-notified`, (r) => {
    calls.mark++;
    state.final_notified_at = "2026-10-07T02:00:00Z";
    return r.fulfill({ json: { interview_id: ID, ...state } });
  });
  await page.goto(`/recruiter/${ID}`);
  return calls;
}

const acceptSel = (p: Page) => p.getByLabel("합격 안내 문구 (합격 처리 시 필수)");
const rejectSel = (p: Page) => p.getByLabel("불합격 안내 문구 (불합격 처리 시 필수)");
const acceptBtn = (p: Page) => p.getByRole("button", { name: "합격 처리", exact: true });
const rejectBtn = (p: Page) => p.getByRole("button", { name: "불합격 처리", exact: true });

test.describe("표시 조건", () => {
  test("[TC-F01] 면접 완료 건: 최종 합격/불합격 결정 영역 표시, 안내 영역은 미처리라 숨김", async ({ page }) => {
    await setup(page);
    await expect(page.getByRole("heading", { name: "최종 합격/불합격 결정" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "최종 합격/불합격 안내" })).toHaveCount(0);
    await expect(acceptSel(page).locator("option")).toHaveCount(4); // 안내 + 3개 문구
    await expect(rejectSel(page).locator("option")).toHaveCount(4);
    if (process.env.E2E_SHOT) await page.screenshot({ path: process.env.E2E_SHOT, fullPage: true });
    await expect(page.getByText("면접 일정 안내")).toHaveCount(0); // 일정 입력란 제외(사용자 결정)
    await expect(page.locator("input[type=date]")).toHaveCount(0);
  });

  for (const status of ["scheduled", "live", "paused", "expired"]) {
    test(`[TC-F02] 면접 상태 '${status}' 건에는 영역 없음`, async ({ page }) => {
      await setup(page, { status });
      await expect(page.getByText("아직 리포트 생성이 요청되지 않았습니다.")).toBeVisible();
      await expect(page.getByRole("heading", { name: "최종 합격/불합격 결정" })).toHaveCount(0);
    });
  }

  test("[TC-F03] 권한 경계: candidate 계정은 '권한이 없습니다', 처리 영역 없음", async ({ page }) => {
    await setup(page, { role: "candidate" });
    await expect(page.getByRole("heading", { name: "권한이 없습니다" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "최종 합격/불합격 결정" })).toHaveCount(0);
  });
});

test.describe("처리 동작", () => {
  test("[TC-F04] 문구 미선택 시 두 버튼 비활성, 합격 문구만 고르면 합격 버튼만 활성", async ({ page }) => {
    await setup(page);
    await expect(acceptBtn(page)).toBeDisabled();
    await expect(rejectBtn(page)).toBeDisabled();
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await expect(acceptBtn(page)).toBeEnabled();
    await expect(rejectBtn(page)).toBeDisabled();
  });

  test("[TC-F05] 합격 처리: PATCH 1회(status/문구 일치) → 잠금 + 결과 표시 + 안내 영역(자동 발송 문구)", async ({ page }) => {
    const calls = await setup(page, { notifyOnDecide: true });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).click();
    await expect(page.getByText("최종 합격", { exact: true })).toBeVisible();
    await expect(page.getByText("이미 최종 결과가 처리되어 변경할 수 없어요.")).toBeVisible();
    expect(calls.patch).toEqual([{ status: "accepted", decision_note: ACCEPT_NOTE }]);
    await expect(acceptBtn(page)).toBeDisabled();
    await expect(rejectBtn(page)).toBeDisabled();
    await expect(acceptSel(page)).toBeDisabled();
    await expect(acceptSel(page)).toHaveValue(ACCEPT_NOTE);
    await expect(page.getByRole("heading", { name: "최종 합격/불합격 안내" })).toBeVisible();
    await expect(page.getByText("시스템이 지원자에게 안내 메일을 자동으로 발송했습니다")).toBeVisible();
    await expect(page.getByText(/^안내 완료:/)).toBeVisible();
    await expect(page.getByRole("button", { name: "발송 완료로 표시" })).toHaveCount(0);
  });

  test("[TC-F06] 불합격 처리: status=rejected 로 전송, 최종 불합격 표시", async ({ page }) => {
    const calls = await setup(page, { notifyOnDecide: true });
    await rejectSel(page).selectOption({ label: REJECT_NOTE });
    await rejectBtn(page).click();
    await expect(page.getByText("최종 불합격", { exact: true })).toBeVisible();
    expect(calls.patch).toEqual([{ status: "rejected", decision_note: REJECT_NOTE }]);
    await expect(rejectSel(page)).toHaveValue(REJECT_NOTE);
  });

  test("[TC-F07] 더블클릭해도 PATCH 는 1회만", async ({ page }) => {
    const calls = await setup(page, { notifyOnDecide: true });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).dblclick();
    await expect(page.getByText("이미 최종 결과가 처리되어 변경할 수 없어요.")).toBeVisible();
    expect(calls.patch).toHaveLength(1);
  });

  test("[TC-F08] 자동 발송 실패(final_notified_at 없음): 안내 문구 + 미리보기 + 수동 '발송 완료로 표시'", async ({ page }) => {
    const calls = await setup(page, { notifyOnDecide: false });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).click();
    await expect(page.getByText("자동 발송이 아직 되지 않았습니다")).toBeVisible();
    await page.getByRole("button", { name: "안내 내용 미리보기" }).click();
    await expect(page.getByText("[채용 안내] 최종 합격 안내")).toBeVisible();
    await expect(page.getByText("받는 사람: cand@example.com")).toBeVisible();
    await page.getByRole("button", { name: "발송 완료로 표시" }).click();
    await expect(page.getByText(/^안내 완료:/)).toBeVisible();
    expect(calls.mark).toBe(1);
  });
});

test.describe("이미 처리된 건·예외", () => {
  test("[TC-F09] 이미 처리된 건 재진입: 잠금 상태 + 저장된 문구 표시, 처리 API 호출 없음", async ({ page }) => {
    const calls = await setup(page, {
      initial: {
        final_decision: "rejected",
        final_decision_note: "저장돼 있던 사용자 지정 문구",
        final_decided_at: "2026-10-06T01:00:00Z",
        final_notified_at: "2026-10-06T01:00:02Z",
      },
    });
    await expect(page.getByText("최종 불합격", { exact: true })).toBeVisible();
    await expect(rejectSel(page)).toHaveValue("저장돼 있던 사용자 지정 문구");
    await expect(acceptBtn(page)).toBeDisabled();
    await expect(rejectBtn(page)).toBeDisabled();
    expect(calls.patch).toHaveLength(0);
  });

  test("[TC-F10] 서버 409(동시 처리 등): 오류 안내 + 최신 상태로 잠금", async ({ page }) => {
    await setup(page, { patchStatus: 409 });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).click();
    await expect(page.getByRole("alert").filter({ hasText: "변경할 수 없습니다" })).toBeVisible();
    await expect(acceptBtn(page)).toBeDisabled();
    await expect(rejectBtn(page)).toBeDisabled();
  });

  test("[TC-F11] 서버 500: 오류 표시, 버튼은 다시 활성(재시도 가능)", async ({ page }) => {
    await setup(page, { patchStatus: 500 });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).click();
    await expect(page.locator(".banner-error")).toBeVisible();
    await expect(acceptBtn(page)).toBeEnabled();
  });

  test("[TC-F12] 콘솔 오류 0 (처리 전체 흐름)", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    await setup(page, { notifyOnDecide: true });
    await acceptSel(page).selectOption({ label: ACCEPT_NOTE });
    await acceptBtn(page).click();
    await page.getByRole("button", { name: "안내 내용 미리보기" }).click();
    await expect(page.getByText("[채용 안내] 최종 합격 안내")).toBeVisible();
    expect(errors).toEqual([]);
  });
});
