/**
 * 채용담당자 [R-02] 리포트 상세 — "채점 템플릿 / 이 템플릿으로 다시 채점" UI 제거 검증 (2026-10-07 사용자 요청).
 * 기본 루브릭 1개만 쓰므로 템플릿 선택·재채점 UI 는 없어야 하고, 루브릭 항목별 평가 표시는 그대로여야 한다.
 * 백엔드 없이 API 를 page.route 로 모킹한다.
 * 실행: cd frontend && E2E_BASE_URL=http://127.0.0.1:3011 npx playwright test e2e/recruiter-final
 */
import { expect, test, type Page } from "@playwright/test";

const ID = "00000000-0000-0000-0000-0000000000b2";

const REPORT = {
  interview_id: ID,
  candidate_name: "정찬성",
  candidate_email: "cand@example.com",
  status: "completed",
  report_status: "ready",
  started_at: "2026-10-02T00:42:12Z",
  ended_at: "2026-10-02T00:44:13Z",
  overall_score: "4.0",
  report_available: true,
  message: "리포트가 준비되었습니다.",
  technical_score: 4,
  communication_score: 4,
  cultural_fit_score: 4,
  overall_recommendation: "recommend",
  pass_fail_recommendation: null,
  star: null,
  summary_text: "요약 본문",
  details: null,
  rubric: {
    template_id: "tpl-default",
    name: "기본 루브릭",
    criteria: [
      { name: "기술 이해도", weight: 40, description: "정확성과 실무 적용 경험", score: 4, evidence: "구체적인 설명을 제공했다.", answer_refs: [5] },
      { name: "의사소통", weight: 30, description: "명료함과 논리적 구조", score: 4, evidence: "논리적 구조를 유지했다.", answer_refs: [1] },
    ],
    answers: [
      { no: 1, excerpt: "첫 번째 답변" },
      { no: 5, excerpt: "다섯 번째 답변" },
    ],
  },
  final_decision: null,
  final_decision_note: null,
  final_decided_at: null,
  final_notified_at: null,
};

async function setup(page: Page) {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(`${r.method()} ${new URL(r.url()).pathname}`));
  await page.addInitScript(() => sessionStorage.setItem("access_token", "fake"));
  await page.route("**/api/v1/auth/me", (r) =>
    r.fulfill({ json: { id: "u1", email: "r@example.com", name: "채용", role: "recruiter", created_at: "2026-01-01T00:00:00Z" } }),
  );
  // 템플릿 목록 API 가 값을 돌려줘도(과거 동작) 화면이 더 이상 쓰지 않아야 한다.
  await page.route("**/api/v1/recruiter/rubric-templates", (r) =>
    r.fulfill({ json: [{ id: "tpl-default", recruiter_id: null, name: "기본 루브릭", criteria: [], is_system_default: true, created_at: "2026-01-01T00:00:00Z" }] }),
  );
  await page.route(`**/api/v1/recruiter/reports/${ID}`, (r) => r.fulfill({ json: REPORT }));
  await page.goto(`/recruiter/${ID}`);
  await expect(page.getByRole("heading", { name: "정찬성" })).toBeVisible();
  return urls;
}

test("[TC-R01] 채점 템플릿 selectbox·'이 템플릿으로 다시 채점' 버튼이 없다", async ({ page }) => {
  await setup(page);
  await expect(page.getByText("채점 템플릿", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /다시 채점/ })).toHaveCount(0);
  await expect(page.locator("#rubric-template-select")).toHaveCount(0);
});

test("[TC-R02] 루브릭 항목별 평가(기본 루브릭) 표시는 그대로 유지된다", async ({ page }) => {
  await setup(page);
  await expect(page.getByText("루브릭 항목별 평가")).toBeVisible();
  await expect(page.getByText("기본 루브릭", { exact: true })).toBeVisible();
  await expect(page.getByText("기술 이해도", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("(가중치 40%)")).toBeVisible();
  await expect(page.getByText("기술 이해도: 4 / 5")).toBeVisible();
  await page.getByRole("button", { name: "답변 #5" }).click(); // 근거 답변 펼치기 동작 유지
  await expect(page.getByText("다섯 번째 답변")).toBeVisible();
});

test("[TC-R03] 화면이 템플릿 목록 API 를 더 이상 호출하지 않는다", async ({ page }) => {
  const urls = await setup(page);
  await page.waitForTimeout(500);
  expect(urls.filter((u) => u.includes("rubric-templates"))).toEqual([]);
  expect(urls.filter((u) => u.includes("/rubric-template"))).toEqual([]);
});

test("[TC-R04] 최종 합격/불합격 영역과 함께 표시돼도 레이아웃·콘솔 오류 없음", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await setup(page);
  await expect(page.getByRole("heading", { name: "최종 합격/불합격 결정" })).toBeVisible();
  await expect(page.getByText("본 리포트/평가는 참고용이며")).toBeVisible();
  expect(errors).toEqual([]);
});
