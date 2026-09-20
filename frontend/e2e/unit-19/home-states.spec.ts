/**
 * unit-19 06단계 — [C-03] 로딩/에러/401 상태 주입(AC-F7~F9) + 하이드레이션(AC-F12).
 * 응답 주입은 page.route 로 브라우저 안에서만 이뤄지며 백엔드/DB 는 변경하지 않는다.
 * 05 지적: Next 가 삽입하는 빈 role="alert" 라우트 어나운서를 피하려고 alert 로케이터는 `main [role="alert"]` 로 한정한다.
 */
import { createSessions, expect, setSession, test } from "./helpers";
import { banner, cards, cta, fulfillWithCors, homeReady, LIST_URL, seedToken, storedToken, uiLogin, watch } from "./ui";

test.use({ locale: "ko-KR", timezoneId: "Asia/Seoul" });

const ERROR_TEXT = "불러오지 못했습니다. 다시 시도해주세요.";

test.describe("로딩 상태", () => {
  test("[AC-F7] 목록 응답 지연 시 aria-busy 스켈레톤 3개, 그동안 CTA 표시·클릭 가능, 완료 후 스켈레톤 제거", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await createSessions(request, acct.token, 2);
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    await page.route(LIST_URL, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await gate;
      await route.continue();
    });
    const w = watch(page);
    await uiLogin(page, acct);
    const busy = page.locator('main ul[aria-busy="true"]');
    await expect(busy).toBeVisible();
    await expect(busy).toHaveAttribute("aria-label", "면접 목록을 불러오는 중");
    await expect(busy.locator("> li")).toHaveCount(3);
    await expect(busy.locator("> li[aria-hidden='true']")).toHaveCount(3);
    await expect(cta(page)).toBeVisible();
    await cta(page).click({ trial: true }); // 클릭 가능(가려지거나 비활성이 아님)
    await expect(cta(page)).toHaveAttribute("href", "/interviews/new");
    await expect(page.getByText("아직 진행한 면접이 없습니다.")).toHaveCount(0); // 로딩 중 빈 상태를 깜빡이지 않는다
    release();
    await expect(cards(page)).toHaveCount(2);
    await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
    expect(w.errors).toEqual([]);
  });

  test("[AC-F7+] 로딩 중에 CTA 를 실제로 클릭해도 동선이 동작한다(목록이 늦어도 핵심 기능 우선)", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    await page.route(LIST_URL, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await new Promise((r) => setTimeout(r, 4000));
      await route.continue().catch(() => {});
    });
    await uiLogin(page, acct);
    await expect(page.locator('main ul[aria-busy="true"]')).toBeVisible();
    await Promise.all([page.waitForURL(/\/interviews\/[0-9a-f-]{36}\/consent$/), cta(page).click()]);
  });
});

test.describe("에러 상태", () => {
  test("[AC-F8] 목록 500: 카드 영역에만 role=alert + '다시 시도', CTA 유지·토큰 유지, 주입 해제 후 재시도로 복구", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await createSessions(request, acct.token, 2);
    let fail = true;
    let listCalls = 0;
    await page.route(LIST_URL, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      listCalls += 1;
      if (fail) return fulfillWithCors(route, 500, { type: "about:blank", title: "Internal Server Error", status: 500, detail: "boom", code: "INTERNAL_ERROR" });
      return route.continue();
    });
    const w = watch(page);
    await uiLogin(page, acct);
    const alert = page.locator('main [role="alert"]');
    await expect(alert).toHaveCount(1);
    await expect(alert).toContainText(ERROR_TEXT);
    await expect(alert).not.toContainText("boom"); // 서버 내부 메시지는 사용자에게 노출하지 않는다
    await expect(alert.getByRole("button", { name: "다시 시도" })).toBeVisible();
    await expect(cards(page)).toHaveCount(0);
    await expect(page.getByText("아직 진행한 면접이 없습니다.")).toHaveCount(0); // 에러를 빈 상태로 오인시키지 않는다
    await expect(banner(page)).toHaveCount(0);
    await expect(cta(page)).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("님, 환영합니다"); // 헤더/계정 영역은 정상
    expect(await storedToken(page)).not.toBeNull(); // 500 은 토큰을 폐기하지 않는다

    fail = false;
    await alert.getByRole("button", { name: "다시 시도" }).click();
    await expect(cards(page)).toHaveCount(2);
    await expect(page.locator('main [role="alert"]')).toHaveCount(0);
    expect(listCalls).toBe(2); // 첫 호출 + 재시도 1회(루프 없음)
    expect(w.errors).toEqual([]); // 주입한 500 의 'Failed to load resource' 로그만 제외
    expect(w.rawErrors.some((e) => /500/.test(e))).toBe(true); // 주입이 실제로 브라우저에 500 으로 도달했음을 증명
  });

  test("[AC-F8+] 네트워크 단절(fetch 실패)·403·404 도 동일한 인라인 에러, 토큰은 유지", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    for (const mode of ["abort", "403", "404"] as const) {
      await page.unroute(LIST_URL).catch(() => {});
      await page.route(LIST_URL, async (route) => {
        if (route.request().method() !== "GET") return route.continue();
        if (mode === "abort") return route.abort("failed");
        return fulfillWithCors(route, Number(mode), { status: Number(mode), detail: "x", code: "X" });
      });
      await uiLogin(page, acct);
      await expect(page.locator('main [role="alert"]'), mode).toContainText(ERROR_TEXT);
      await expect(cta(page), mode).toBeVisible();
      expect(await storedToken(page), mode).not.toBeNull();
      await page.getByRole("button", { name: "로그아웃" }).click();
    }
  });

  test("[AC-F8++] 재시도 중에는 다시 로딩(스켈레톤)이 되고, 재시도도 실패하면 에러가 유지된다", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    let n = 0;
    await page.route(LIST_URL, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      n += 1;
      if (n === 2) await new Promise((r) => setTimeout(r, 1200));
      return fulfillWithCors(route, 500, { status: 500, detail: "boom", code: "INTERNAL_ERROR" });
    });
    await uiLogin(page, acct);
    const alert = page.locator('main [role="alert"]');
    await expect(alert).toContainText(ERROR_TEXT);
    await alert.getByRole("button", { name: "다시 시도" }).click();
    await expect(page.locator('main ul[aria-busy="true"]')).toBeVisible();
    await expect(alert).toHaveCount(0);
    await expect(page.locator('main [role="alert"]')).toContainText(ERROR_TEXT);
    expect(n).toBe(2);
  });

  test("[AC-F9] 목록 401: sessionStorage.access_token 삭제 + 랜딩 표시, 재호출 루프 없음", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    let listCalls = 0;
    await page.route(LIST_URL, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      listCalls += 1;
      return fulfillWithCors(route, 401, { type: "about:blank", title: "Unauthorized", status: 401, detail: "만료", code: "AUTH_INVALID_TOKEN" });
    });
    await uiLogin(page, acct);
    await expect(page.getByRole("heading", { name: "AI 모의면접 플랫폼" })).toBeVisible();
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toBeVisible();
    expect(await storedToken(page)).toBeNull();
    await expect(cards(page)).toHaveCount(0);
    await expect(page.locator('main [role="alert"]')).toHaveCount(0);
    await page.waitForTimeout(1200);
    expect(listCalls).toBe(1);
  });
});

test.describe("하이드레이션", () => {
  test("[AC-F12] 토큰이 저장된 상태로 / 로드·새로고침: 콘솔 error·pageerror 0 (React #418 없음)", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await createSessions(request, acct.token, 2);
    const w = watch(page);
    await seedToken(page, acct.token);
    await page.goto("/");
    await homeReady(page);
    await expect(cards(page)).toHaveCount(2);
    for (let i = 0; i < 3; i++) {
      await page.reload();
      await homeReady(page);
      await expect(cards(page)).toHaveCount(2);
    }
    expect(w.rawErrors).toEqual([]); // 노이즈 필터 없이 전부 0건
    expect(w.errors).toEqual([]);
  });

  test("[AC-F12+] 토큰 없음/있음 조합으로 /, /login, /register, /mypage 로드해도 hydration 오류 0 (recruiter 포함)", async ({ page, kit }) => {
    const cand = await kit.create("candidate");
    const rec = await kit.create("recruiter");
    const w = watch(page);
    for (const path of ["/", "/login", "/register", "/mypage"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    for (const acct of [cand, rec]) {
      await page.evaluate((t) => window.sessionStorage.setItem("access_token", t), acct.token);
      for (const path of ["/", "/login", "/register", "/mypage"]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
      }
    }
    expect(w.rawErrors.filter((e) => !/Failed to load resource/.test(e))).toEqual([]);
  });

  test("[AC-F12 대조군] 검출기 자체가 동작한다: console.error 와 pageerror 가 실제로 수집된다", async ({ page }) => {
    const w = watch(page);
    await page.goto("/login");
    await page.evaluate(() => {
      console.error("Hydration failed probe");
      setTimeout(() => {
        throw new Error("probe pageerror");
      }, 0);
    });
    await page.waitForTimeout(300);
    expect(w.errors).toHaveLength(2);
    expect(w.errors[0]).toContain("Hydration failed probe");
    expect(w.errors[1]).toContain("probe pageerror");
  });

  test("[AC-F12++] 하이드레이션 전(서버 HTML)은 토큰 유무와 무관하게 '불러오는 중...' 이 아닌 랜딩이 아니라 로딩 셸이다 - JS 비활성 응답 확인", async ({ browser, kit, baseURL }) => {
    const acct = await kit.create("candidate");
    const ctx = await browser.newContext({ javaScriptEnabled: false, baseURL });
    const page = await ctx.newPage();
    await page.goto("/");
    // 서버는 sessionStorage 를 모르므로 항상 같은 HTML(로딩 셸)을 내려준다 -> 로그인 여부에 따라 달라지는 서버 HTML 이 없다
    await expect(page.getByText("불러오는 중...")).toBeVisible();
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toHaveCount(0);
    await ctx.close();
    expect(acct.id).toBeTruthy();
  });
});

test.describe("기타 상태 전이", () => {
  test("live 세션을 홈에서 25h 경과 상태로 만나면 배너가 뜨지 않고 카드는 '만료'로 표시된다(요청 시점 확정)", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const [sid] = await createSessions(request, acct.token, 1);
    setSession(sid, { status: "live", startedAt: "2026-01-01 00:00:00+09" });
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(1);
    await expect(cards(page).first().locator("span")).toHaveText(["만료"]);
    await expect(banner(page)).toHaveCount(0);
  });
});
