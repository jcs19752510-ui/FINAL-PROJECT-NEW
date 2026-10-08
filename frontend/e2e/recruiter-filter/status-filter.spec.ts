/**
 * 채용담당자 [R-01] 지원자 리포트 목록 — 면접 상태 조회 selectbox + 상단 탭 순서 검증.
 * 백엔드 없이 API(/auth/me, /recruiter/reports)를 page.route 로 모킹한다.
 * 실행: cd frontend && E2E_BASE_URL=http://127.0.0.1:3011 npx playwright test e2e/recruiter-filter
 */
import { expect, test, type Page } from "@playwright/test";

type Status = "scheduled" | "live" | "paused" | "completed" | "expired";

function row(i: number, status: Status, name = `지원자${i}`) {
  return {
    interview_id: `00000000-0000-0000-0000-00000000000${i}`,
    candidate_name: name,
    candidate_email: `c${i}@example.com`,
    status,
    report_status: status === "completed" ? "ready" : "none",
    started_at: null,
    ended_at: null,
    overall_score: null,
  };
}

const DATA = [
  row(1, "completed"),
  row(2, "live"),
  row(3, "live"),
  row(4, "scheduled"),
  row(5, "expired"),
];

async function open(page: Page, reports: unknown[], role = "recruiter", calls: string[] = []) {
  await page.addInitScript(() => sessionStorage.setItem("access_token", "fake"));
  await page.route("**/api/v1/auth/me", (r) =>
    r.fulfill({ json: { id: "u1", email: "r@example.com", name: "채용", role, created_at: "2026-01-01T00:00:00Z" } }),
  );
  await page.route("**/api/v1/recruiter/reports", (r) => {
    calls.push(r.request().url());
    return r.fulfill({ json: reports });
  });
  await page.goto("/recruiter");
}

const rows = (page: Page) => page.locator("tbody tr");
const select = (page: Page) => page.getByLabel("면접 상태");

test.describe("상단 탭 순서", () => {
  test("[TC-01] 이력서 검토 / 지원자 리포트 / 제출 절차 안내 / 채용담당자 추가 순서", async ({ page }) => {
    await open(page, DATA);
    await expect(page.locator("nav[aria-label='채용 관리 메뉴'] a")).toHaveText([
      "이력서 검토",
      "지원자 리포트",
      "제출 절차 안내",
      "채용담당자 추가",
    ]);
  });

  test("[TC-02] /recruiter 에서 '지원자 리포트' 탭만 활성(aria-current)", async ({ page }) => {
    await open(page, DATA);
    const active = page.locator("nav[aria-label='채용 관리 메뉴'] a[aria-current='page']");
    await expect(active).toHaveCount(1);
    await expect(active).toHaveText("지원자 리포트");
  });
});

test.describe("면접 상태 selectbox", () => {
  test("[TC-03] 설명 문구 바로 아래에 위치하고 옵션은 전체+5개 상태, 기본값 전체", async ({ page }) => {
    await open(page, DATA);
    await expect(rows(page)).toHaveCount(5);
    const sub = await page.getByText("우리 조직의 모든 지원자 면접 내역을 볼 수 있어요.").boundingBox();
    const sel = await select(page).boundingBox();
    const tbl = await page.locator("table").boundingBox();
    expect(sel!.y).toBeGreaterThan(sub!.y);
    expect(sel!.y).toBeLessThan(tbl!.y);
    await expect(select(page).locator("option")).toHaveText(["전체", "예정", "진행 중", "일시중지", "완료", "만료"]);
    await expect(select(page)).toHaveValue("all");
  });

  for (const [label, expected] of [
    ["예정", 1],
    ["진행 중", 2],
    ["완료", 1],
    ["만료", 1],
  ] as const) {
    test(`[TC-04] '${label}' 선택 시 ${expected}건만 표시`, async ({ page }) => {
      await open(page, DATA);
      await select(page).selectOption({ label });
      await expect(rows(page)).toHaveCount(expected);
      await expect(rows(page).locator("td:nth-child(3)")).toHaveText(Array(expected).fill(label));
    });
  }

  test("[TC-05] 해당 건 없는 상태(일시중지) → 안내 문구, 표 숨김 / 전체로 되돌리면 5건 복원", async ({ page }) => {
    await open(page, DATA);
    await select(page).selectOption({ label: "일시중지" });
    await expect(page.getByText("선택한 면접 상태의 내역이 없습니다.")).toBeVisible();
    await expect(page.locator("table")).toHaveCount(0);
    await select(page).selectOption({ label: "전체" });
    await expect(rows(page)).toHaveCount(5);
  });

  test("[TC-06] 필터 변경은 추가 API 호출 없이 클라이언트에서 처리 (목록 호출 1회)", async ({ page }) => {
    const calls: string[] = [];
    await open(page, DATA, "recruiter", calls);
    await expect(rows(page)).toHaveCount(5);
    for (const l of ["완료", "예정", "전체"]) await select(page).selectOption({ label: l });
    await page.waitForTimeout(500);
    expect(calls).toHaveLength(1);
  });

  test("[TC-07] 필터된 행 클릭 시 해당 지원자 상세로 이동", async ({ page }) => {
    await open(page, DATA);
    await select(page).selectOption({ label: "만료" });
    await rows(page).first().click();
    await expect(page).toHaveURL(/\/recruiter\/00000000-0000-0000-0000-000000000005$/);
  });

  test("[TC-08] 목록 0건이면 기존 안내 문구 유지, selectbox 는 표시", async ({ page }) => {
    await open(page, []);
    await expect(page.getByText("아직 열람 가능한 리포트가 없습니다.")).toBeVisible();
    await expect(select(page)).toBeVisible();
  });

  test("[TC-09] 키보드 조작(포커스 후 방향키)으로 필터 변경, label 연결(접근성)", async ({ page }) => {
    await open(page, DATA);
    await select(page).focus();
    await page.keyboard.press("ArrowDown"); // 전체 → 예정
    await expect(rows(page)).toHaveCount(1);
  });

  test("[TC-10] 권한 경계: candidate 계정은 selectbox 없이 '권한이 없습니다'", async ({ page }) => {
    await open(page, DATA, "candidate");
    await expect(page.getByRole("heading", { name: "권한이 없습니다" })).toBeVisible();
    await expect(page.getByLabel("면접 상태")).toHaveCount(0);
  });

  test("[TC-11] 콘솔 오류 0", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    await open(page, DATA);
    await select(page).selectOption({ label: "진행 중" });
    await expect(rows(page)).toHaveCount(2);
    expect(errors).toEqual([]);
  });
});
