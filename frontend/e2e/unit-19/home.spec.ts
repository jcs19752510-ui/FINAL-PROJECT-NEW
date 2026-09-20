/**
 * unit-19 06단계 — [C-03] 지원자 홈 화면(브라우저) 검증: AC-F1~F6, F10, F11, F14 + 경계/예외.
 * 사전 조건: 백엔드(E2E_API_URL, 기본 http://localhost:8720/api/v1)와, 그 주소를 NEXT_PUBLIC_API_BASE_URL 로 빌드한
 *            프런트(E2E_BASE_URL, 기본 http://localhost:3720 — CORS_ORIGINS 에 포함되어야 함)가 떠 있어야 한다.
 * 실행: cd frontend && E2E_BASE_URL=http://localhost:3720 npx playwright test e2e/unit-19/home.spec.ts
 */
import { API_BASE, bulkCompleted, countInterviews, createSessions, expect, listBody, seedSevenStates, setSession, sql, test } from "./helpers";
import { banner, cards, cta, homeReady, storedToken, uiLogin, watch } from "./ui";

test.use({ locale: "ko-KR", timezoneId: "Asia/Seoul" });

test.describe("비로그인/빈 상태/새 면접 시작 동선", () => {
  test("[AC-F1] 비로그인 / : 랜딩(로그인·회원가입 링크), 목록 API 호출 없음, html lang=ko, 콘솔 오류 0", async ({ page }) => {
    const w = watch(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "AI 모의면접 플랫폼" })).toBeVisible();
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toHaveAttribute("href", "/login");
    await expect(page.getByRole("link", { name: "회원가입", exact: true })).toHaveAttribute("href", "/register");
    await expect(page.getByText("이후 작업 단위에서 추가됩니다")).toHaveCount(0); // stale 안내 문구 제거 확인
    await expect(page.locator("html")).toHaveAttribute("lang", "ko");
    await page.waitForTimeout(800);
    expect(w.listCalls).toHaveLength(0);
    expect(w.errors).toEqual([]);
  });

  test("[AC-F2] 신규 candidate(세션 0): 환영 문구·빈 상태 문구·카드 0·배너 없음·CTA 강조·목록 호출 정확히 1회·세션 자동 생성 없음", async ({ page, kit }) => {
    const acct = await kit.create("candidate", "홍길동");
    const w = watch(page);
    await uiLogin(page, acct);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("홍길동님, 환영합니다");
    await expect(page.getByRole("heading", { name: "최근 면접", level: 2 })).toBeVisible();
    await expect(page.getByText("아직 진행한 면접이 없습니다. 첫 모의면접을 시작해보세요.")).toBeVisible();
    await expect(cards(page)).toHaveCount(0);
    await expect(banner(page)).toHaveCount(0);
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    await expect(cta(page)).toHaveAttribute("href", "/interviews/new");
    // 빈 상태에서만 CTA 강조(outline 3px)
    const outline = await cta(page).evaluate((el) => getComputedStyle(el).outlineWidth);
    expect(outline).toBe("3px");
    await expect(page.getByRole("link", { name: "마이페이지" })).toHaveAttribute("href", "/mypage");
    await page.waitForTimeout(1500); // 무한 재요청 루프 감시
    expect(w.listCalls).toHaveLength(1);
    expect(w.createCalls).toHaveLength(0);
    expect(countInterviews(acct.id)).toBe(0); // CTA prefetch 등으로 세션이 만들어지지 않는다
    expect(w.errors).toEqual([]);
  });

  test("[AC-F3] '새 면접 시작' 클릭 -> POST 1회 -> /interviews/{id}/consent, 홈 복귀(뒤로가기·새로고침) 시 '시작 전' 카드 1개", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    const w = watch(page);
    await uiLogin(page, acct);
    await expect(cta(page)).toBeVisible();
    await Promise.all([page.waitForURL(/\/interviews\/[0-9a-f-]{36}\/consent$/), cta(page).click()]);
    const id = /interviews\/([0-9a-f-]{36})\/consent/.exec(page.url())![1];
    expect(w.createCalls).toHaveLength(1);
    expect(countInterviews(acct.id)).toBe(1);
    expect(sql(`select id from interviews where candidate_id='${acct.id}'`)[0][0]).toBe(id);

    for (const via of ["back", "goto"] as const) {
      if (via === "back") await page.goBack();
      else await page.goto("/");
      await homeReady(page);
      await expect(cards(page)).toHaveCount(1);
      const card = cards(page).first();
      await expect(card.locator("span")).toHaveText(["시작 전"]);
      const action = card.getByRole("link");
      await expect(action).toHaveText("사전고지 확인하고 시작");
      await expect(action).toHaveAttribute("href", `/interviews/${id}/consent`);
      await expect(banner(page)).toHaveCount(0);
      // 세션이 있으면 CTA 강조를 하지 않는다
      const emphasis = await cta(page).evaluate((el) => getComputedStyle(el).outlineStyle);
      expect(emphasis, "카드가 있으면 CTA 강조(outline solid)가 꺼져야 한다").not.toBe("solid");
    }
    expect(w.createCalls).toHaveLength(1);
    expect(countInterviews(acct.id)).toBe(1);
    expect(w.errors).toEqual([]);
  });

  test("키보드: CTA 에 포커스 후 Enter 로도 세션 생성·이동한다", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    await uiLogin(page, acct);
    await cta(page).focus();
    await Promise.all([page.waitForURL(/\/interviews\/[0-9a-f-]{36}\/consent$/), page.keyboard.press("Enter")]);
    expect(countInterviews(acct.id)).toBe(1);
  });
});

test.describe("목록 표시: 상태·정렬·링크·배지·점수·배너", () => {
  test("[AC-F4][AC-F10] 7개 상태: 카드 수·순서·라벨·배지·점수·액션·href, 배지는 ready 에만", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const other = await kit.create("candidate", "타인");
    const seven = await seedSevenStates(request, acct.token);
    const otherIds = await createSessions(request, other.token, 2);
    setSession(otherIds[0], { status: "completed", report: "ready", score: "9.9", startedAgo: "5 minutes", endedAgo: "1 minute" });
    const w = watch(page);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    const api = await listBody(request, acct.token);
    expect(api.map((i) => i.id)).toEqual([seven.scheduled, seven.live1h, seven.paused2h, seven.queued3h, seven.failed4h, seven.live25h, seven.ready30h]);
    const expected = [
      { id: seven.scheduled, tags: ["시작 전"], score: "종합 점수: 아직 없음", action: "사전고지 확인하고 시작", href: `/interviews/${seven.scheduled}/consent` },
      { id: seven.live1h, tags: ["진행 중"], score: "종합 점수: 아직 없음", action: "이어서 진행", href: `/interviews/${seven.live1h}` },
      { id: seven.paused2h, tags: ["중단됨"], score: "종합 점수: 아직 없음", action: "이어서 진행", href: `/interviews/${seven.paused2h}` },
      { id: seven.queued3h, tags: ["완료", "리포트 생성 중"], score: "종합 점수: 아직 없음", action: "대화 이력 보기", href: `/interviews/${seven.queued3h}` },
      { id: seven.failed4h, tags: ["완료", "리포트 생성 실패"], score: "종합 점수: 아직 없음", action: "대화 이력 보기", href: `/interviews/${seven.failed4h}` },
      { id: seven.live25h, tags: ["만료"], score: "종합 점수: 아직 없음", action: "대화 이력 보기", href: `/interviews/${seven.live25h}` },
      { id: seven.ready30h, tags: ["완료", "리포트 준비 완료"], score: "종합 점수: 7.5", action: "대화 이력 보기", href: `/interviews/${seven.ready30h}` },
    ];
    for (let i = 0; i < expected.length; i++) {
      const card = cards(page).nth(i);
      await expect(card.locator("span"), `card ${i}`).toHaveText(expected[i].tags);
      await expect(card, `card ${i}`).toContainText(expected[i].score);
      const action = card.getByRole("link");
      await expect(action, `card ${i}`).toHaveText(expected[i].action);
      await expect(action, `card ${i}`).toHaveAttribute("href", expected[i].href);
    }
    await expect(page.getByText("리포트 준비 완료", { exact: true })).toHaveCount(1);
    await expect(page.getByText("리포트 생성 중", { exact: true })).toHaveCount(1);
    await expect(page.getByText("리포트 생성 실패", { exact: true })).toHaveCount(1);
    // 만료 확정이 홈 로딩 한 번으로 DB 에 반영
    expect(sql(`select status from interviews where id='${seven.live25h}'`)[0][0]).toBe("expired");
    // AC-F10: 타인 세션 비노출 — 링크 href 뿐 아니라 문서 전체에 타인 id/점수가 없다
    const html = await page.content();
    for (const id of otherIds) expect(html).not.toContain(id);
    expect(await page.locator("main").innerText()).not.toContain("9.9");
    const hrefs = await page.locator("main a").evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""));
    for (const id of otherIds) expect(hrefs.join(" ")).not.toContain(id);
    // 카드 링크의 접근 가능한 이름은 서로 다르고(일시 포함) 보이는 라벨을 포함한다(WCAG 2.5.3)
    const names = await cards(page).getByRole("link").evaluateAll((els) => els.map((e) => ({ label: e.getAttribute("aria-label") ?? "", text: (e.textContent ?? "").trim() })));
    expect(new Set(names.map((n) => n.label)).size).toBe(7);
    for (const n of names) expect(n.label).toContain(n.text);
    await page.waitForTimeout(1000);
    expect(w.listCalls).toHaveLength(1);
    expect(w.errors).toEqual([]);
  });

  test("[AC-F4+] 일시 표시는 started_at(없으면 created_at)의 ko-KR 로케일·KST 표기이고, 점수 0.0/10.0/99.9 도 그대로 보인다", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const [a, b, c, d] = await createSessions(request, acct.token, 4);
    setSession(a, { status: "completed", report: "ready", score: "0.0", startedAt: "2026-03-01 09:05:07+09", endedAgo: "1 hour" });
    setSession(b, { status: "completed", report: "ready", score: "10.0", startedAt: "2026-02-01 23:59:59+09", endedAgo: "1 hour" });
    setSession(c, { status: "completed", report: "ready", score: "99.9", startedAt: "2026-01-01 00:00:00+09", endedAgo: "1 hour" });
    sql(`update interviews set created_at='2026-01-02 13:04:05+09' where id='${d}'`); // scheduled, started_at NULL -> created_at 표시
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(4);
    // 정렬: 03-01, 02-01, 01-02(created_at), 01-01
    await expect(cards(page).nth(0)).toContainText("2026. 3. 1. 오전 9:05:07");
    await expect(cards(page).nth(0)).toContainText("종합 점수: 0.0");
    await expect(cards(page).nth(1)).toContainText("2026. 2. 1. 오후 11:59:59");
    await expect(cards(page).nth(1)).toContainText("종합 점수: 10.0");
    await expect(cards(page).nth(2)).toContainText("2026. 1. 2. 오후 1:04:05");
    await expect(cards(page).nth(2)).toContainText("시작 전");
    await expect(cards(page).nth(3)).toContainText("2026. 1. 1. 오전 12:00:00");
    await expect(cards(page).nth(3)).toContainText("종합 점수: 99.9");
  });

  test("[AC-F5] 중단 배너: role=status, 가장 최근 resumable 링크, '(외 1건은 아래 목록에서 확인)', 클릭 시 /interviews/{id}", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const seven = await seedSevenStates(request, acct.token);
    await uiLogin(page, acct);
    const b = banner(page);
    await expect(b).toBeVisible();
    await expect(b).toContainText("중단된 면접이 있습니다.");
    await expect(b).toContainText("(외 1건은 아래 목록에서 확인)");
    await expect(b).toContainText("에 시작한 면접을 이어서 진행할 수 있어요.");
    // 배너의 일시는 대상(가장 최근 resumable = live 1h) 카드의 일시와 같다
    const cardDate = (await cards(page).nth(1).locator("div").nth(1).innerText()).trim();
    await expect(b).toContainText(cardDate);
    const link = b.getByRole("link", { name: "이어서 진행" });
    await expect(link).toHaveAttribute("href", `/interviews/${seven.live1h}`);
    await Promise.all([page.waitForURL(new RegExp(`/interviews/${seven.live1h}$`)), link.click()]);
  });

  test("[AC-F5+] resumable 1건이면 '외 N건' 없음 / 만료뿐이면 배너 없음 / completed 뿐이면 배너 없음", async ({ page, kit, request }) => {
    const one = await kit.create("candidate");
    const [sid] = await createSessions(request, one.token, 1);
    setSession(sid, { status: "paused", startedAgo: "3 hours" });
    await uiLogin(page, one);
    await expect(banner(page)).toBeVisible();
    await expect(banner(page)).not.toContainText("외 ");
    await expect(banner(page).getByRole("link")).toHaveAttribute("href", `/interviews/${sid}`);
    await page.getByRole("button", { name: "로그아웃" }).click();

    const stale = await kit.create("candidate");
    const [s2, s3] = await createSessions(request, stale.token, 2);
    setSession(s2, { status: "live", startedAgo: "48 hours" });
    setSession(s3, { status: "completed", report: "none", startedAgo: "5 hours", endedAgo: "4 hours" });
    await uiLogin(page, stale);
    await expect(cards(page)).toHaveCount(2);
    await expect(banner(page)).toHaveCount(0);
    await expect(cards(page).nth(1)).toContainText("만료");
  });

  test("[AC-F6] 10건 경계: 10건이면 안내 없음, 11건이면 카드 10개 + '최근 10건만 표시합니다 (전체 11건).'", async ({ page, kit }) => {
    const ten = await kit.create("candidate");
    bulkCompleted(ten.id, 10);
    await uiLogin(page, ten);
    await expect(cards(page)).toHaveCount(10);
    await expect(page.getByText("최근 10건만 표시합니다")).toHaveCount(0);
    await page.getByRole("button", { name: "로그아웃" }).click();

    const eleven = await kit.create("candidate");
    bulkCompleted(eleven.id, 11);
    await uiLogin(page, eleven);
    await expect(cards(page)).toHaveCount(10);
    await expect(page.getByText("최근 10건만 표시합니다 (전체 11건).")).toBeVisible();
  });

  test("[AC-F6+] 배너는 전체 응답 기준: 10건 밖(가장 오래된) live 세션도 배너로 안내되고, 카드에는 없다", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    bulkCompleted(acct.id, 12);
    const [old] = await createSessions(request, acct.token, 1);
    setSession(old, { status: "live", startedAgo: "20 hours" });
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(10);
    await expect(page.getByText("최근 10건만 표시합니다 (전체 13건).")).toBeVisible();
    await expect(banner(page).getByRole("link")).toHaveAttribute("href", `/interviews/${old}`);
    await expect(cards(page).locator(`a[href="/interviews/${old}"]`)).toHaveCount(0);
  });
});

test.describe("역할별 화면·계정 전환", () => {
  test("[AC-F11] recruiter: 환영 카드 + /recruiter 링크, '새 면접 시작'·'최근 면접' 없음, GET /interviews 미호출, 콘솔 오류 0", async ({ page, kit }) => {
    const recruiter = await kit.create("recruiter", "채용담당");
    const w = watch(page);
    await uiLogin(page, recruiter);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("채용담당님, 환영합니다");
    await expect(page.getByText(`역할: 채용담당자 (${recruiter.email})`)).toBeVisible();
    await expect(page.getByRole("link", { name: "지원자 리포트 목록으로 이동" })).toHaveAttribute("href", "/recruiter");
    await expect(cta(page)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "최근 면접" })).toHaveCount(0);
    await page.waitForTimeout(1200);
    expect(w.listCalls).toHaveLength(0);
    expect(w.errors).toEqual([]);
  });

  test("[AC-F11+] admin 역할: 지원자 홈·recruiter 링크 없이 환영 카드만, 목록 미호출", async ({ page, kit }) => {
    const acct = await kit.create("candidate", "관리자");
    sql(`update users set role='admin' where id='${acct.id}'`);
    const w = watch(page);
    await page.addInitScript((t) => window.sessionStorage.setItem("access_token", t), acct.token);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("관리자님, 환영합니다");
    await expect(page.getByText("역할: admin")).toBeVisible();
    await expect(cta(page)).toHaveCount(0);
    await expect(page.getByRole("link", { name: "지원자 리포트 목록으로 이동" })).toHaveCount(0);
    await page.waitForTimeout(1000);
    expect(w.listCalls).toHaveLength(0);
  });

  test("[AC-F14] 로그아웃: 랜딩 전환·sessionStorage 토큰 삭제·새로고침 후에도 랜딩·이후 목록 호출 없음", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await createSessions(request, acct.token, 1);
    const w = watch(page);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(1);
    expect(await storedToken(page)).not.toBeNull();
    const before = w.listCalls.length;
    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toBeVisible();
    expect(await storedToken(page)).toBeNull();
    await page.reload();
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toBeVisible();
    await expect(cards(page)).toHaveCount(0);
    expect(w.listCalls.length).toBe(before);
  });

  test("계정 전환: 로그아웃 후 다른 candidate 로 로그인하면 이전 계정의 카드가 남지 않는다", async ({ page, kit, request }) => {
    const a = await kit.create("candidate", "에이");
    const b = await kit.create("candidate", "비");
    const aIds = await createSessions(request, a.token, 2);
    await uiLogin(page, a);
    await expect(cards(page)).toHaveCount(2);
    await page.getByRole("button", { name: "로그아웃" }).click();
    await uiLogin(page, b);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("비님, 환영합니다");
    await expect(cards(page)).toHaveCount(0);
    const html = await page.content();
    for (const id of aIds) expect(html).not.toContain(id);
    await expect(page.getByText("아직 진행한 면접이 없습니다.")).toBeVisible();
  });

  test("[보안] 사용자 이름의 HTML/스크립트는 실행되지 않고 문자 그대로 표시된다", async ({ page, kit }) => {
    const payload = `<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>`;
    const acct = await kit.create("candidate", payload);
    await uiLogin(page, acct);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(`${payload}님, 환영합니다`);
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    await expect(page.locator('main img[src="x"]')).toHaveCount(0);
  });

  test("[예외] sessionStorage 에 무효 토큰이 있으면 목록 호출 없이 랜딩으로, 토큰은 폐기된다", async ({ page }) => {
    const w = watch(page);
    await page.addInitScript(() => window.sessionStorage.setItem("access_token", "garbage.token.value"));
    await page.goto("/");
    await expect(page.getByRole("link", { name: "로그인", exact: true })).toBeVisible();
    expect(await storedToken(page)).toBeNull();
    expect(w.listCalls).toHaveLength(0);
    expect(w.errors).toEqual([]);
  });

  test("[예외] 다른 사용자가 목록에 접근할 수 없음을 UI 가 그대로 반영: 무토큰 상태에서 /interviews/new 는 로그인으로 보낸다", async ({ page }) => {
    await page.goto("/interviews/new");
    await page.waitForURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "로그인" })).toBeVisible();
  });
});

test.describe("API 호출 계약(프런트 -> 백엔드)", () => {
  test("홈 로딩 시 GET /interviews 에 Bearer 토큰을 실어 보내고 쿼리 파라미터는 없다", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    const reqs: { url: string; auth: string | undefined }[] = [];
    page.on("request", (r) => {
      if (r.method() === "GET" && r.url().startsWith(`${API_BASE}/interviews`)) reqs.push({ url: r.url(), auth: r.headers()["authorization"] });
    });
    await uiLogin(page, acct);
    await homeReady(page);
    await expect(page.getByText("아직 진행한 면접이 없습니다.")).toBeVisible();
    expect(reqs).toHaveLength(1);
    expect(reqs[0].url).toBe(`${API_BASE}/interviews`);
    expect(reqs[0].auth).toMatch(/^Bearer [\w-]+\.[\w-]+\.[\w-]+$/); // 로그인 시 발급된 JWT 형식
  });
});
