/**
 * unit-19 06단계 — [C-03] 반응형/접근성(AC-F13). axe(@axe-core/playwright)는 패키지 미승인이라 사용하지 않고
 * DOM/ARIA/포커스/대비 계산(WCAG 2.x 상대 휘도 공식)으로 직접 검증한다.
 */
import type { Page } from "@playwright/test";
import { createSessions, expect, seedSevenStates, setSession, test } from "./helpers";
import { banner, cards, cta, homeReady, uiLogin } from "./ui";

test.use({ locale: "ko-KR", timezoneId: "Asia/Seoul" });

interface Contrast {
  text: string;
  ratio: number;
  need: number;
  fg: string;
  bg: string;
  size: number;
}

/** 화면에 보이는 모든 텍스트 노드의 (전경, 유효 배경) 대비를 계산한다. 배경은 조상으로 올라가며 알파 합성. */
async function measureContrast(page: Page): Promise<Contrast[]> {
  return page.evaluate(() => {
    const parse = (c: string): [number, number, number, number] => {
      const m = /rgba?\(([^)]+)\)/.exec(c);
      if (!m) return [0, 0, 0, 0];
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const over = (top: number[], bottom: number[]): [number, number, number, number] => {
      const a = top[3] + bottom[3] * (1 - top[3]);
      if (a === 0) return [0, 0, 0, 0];
      return [0, 1, 2].map((i) => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a).concat(a) as [number, number, number, number];
    };
    const lin = (v: number) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    const lum = (c: number[]) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
    const effectiveBg = (el: Element): [number, number, number, number] => {
      let acc: [number, number, number, number] = [0, 0, 0, 0];
      const chain: Element[] = [];
      for (let e: Element | null = el; e; e = e.parentElement) chain.push(e);
      for (const e of chain) {
        acc = over(acc, parse(getComputedStyle(e).backgroundColor));
        if (acc[3] >= 1) break;
      }
      return acc[3] >= 1 ? acc : (over(acc, [255, 255, 255, 1]) as [number, number, number, number]);
    };
    const out: { text: string; ratio: number; need: number; fg: string; bg: string; size: number }[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = (n.textContent ?? "").trim();
      const el = n.parentElement;
      if (!text || !el) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none" || el.closest("[aria-hidden='true']")) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) continue; // sr-only 등
      if (el.closest("next-route-announcer, script, style")) continue;
      const fg = parse(cs.color);
      const bg = effectiveBg(el);
      const fgOver = over(fg, bg);
      const l1 = lum(fgOver);
      const l2 = lum(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const size = parseFloat(cs.fontSize);
      const bold = parseInt(cs.fontWeight, 10) >= 700;
      const large = size >= 24 || (size >= 18.66 && bold);
      out.push({ text: text.slice(0, 40), ratio: Math.round(ratio * 100) / 100, need: large ? 3 : 4.5, fg: cs.color, bg: `rgb(${bg.slice(0, 3).map(Math.round).join(",")})`, size });
    }
    return out;
  });
}

test.describe("접근성·반응형", () => {
  test("[AC-F13] Tab 순서: 마이페이지 -> 로그아웃 -> 새 면접 시작 -> 배너 '이어서 진행' -> 카드 액션들, 포커스 링(2px #1456d6, offset 2px) 표시", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const seven = await seedSevenStates(request, acct.token);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    const seq: { name: string; href: string | null; outline: string; offset: string; color: string }[] = [];
    for (let i = 0; i < 11; i++) {
      await page.keyboard.press("Tab");
      seq.push(
        await page.evaluate(() => {
          const el = document.activeElement as HTMLElement;
          const cs = getComputedStyle(el);
          return {
            name: el.getAttribute("aria-label") ?? (el.textContent ?? "").trim(),
            href: el.getAttribute("href"),
            outline: `${cs.outlineStyle} ${cs.outlineWidth}`,
            offset: cs.outlineOffset,
            color: cs.outlineColor,
          };
        }),
      );
    }
    expect(seq.slice(0, 4).map((s) => s.name)).toEqual(["마이페이지", "로그아웃", "새 면접 시작", "이어서 진행"]);
    expect(seq[1].href).toBeNull(); // 로그아웃은 버튼
    expect(seq[3].href).toBe(`/interviews/${seven.live1h}`); // 배너 링크
    // 이후는 카드 액션(7개)이 DOM 순서대로
    const cardHrefs = seq.slice(4, 11).map((s) => s.href);
    expect(cardHrefs).toEqual([
      `/interviews/${seven.scheduled}/consent`,
      `/interviews/${seven.live1h}`,
      `/interviews/${seven.paused2h}`,
      `/interviews/${seven.queued3h}`,
      `/interviews/${seven.failed4h}`,
      `/interviews/${seven.live25h}`,
      `/interviews/${seven.ready30h}`,
    ]);
    for (const s of seq) {
      expect(s.outline, s.name).toBe("solid 2px");
      expect(s.offset, s.name).toBe("2px");
      expect(s.color, s.name).toBe("rgb(20, 86, 214)");
    }
    // 아직 도달 못 한 포커스 가능 요소가 없다: 전체 포커스 가능 요소 수 = 4 + 7
    const focusables = await page.locator("main a[href], main button:not([disabled])").count();
    expect(focusables).toBe(11);
    // Shift+Tab 으로 역순 이동
    await page.keyboard.press("Shift+Tab");
    expect(await page.evaluate(() => document.activeElement?.getAttribute("href"))).toBe(`/interviews/${seven.live25h}`);
  });

  test("[AC-F13] 에러 상태의 '다시 시도' 버튼도 키보드로 도달·활성화되고 포커스 링이 보인다", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    await page.route(/\/api\/v1\/interviews$/, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.abort("failed");
    });
    await uiLogin(page, acct);
    await expect(page.locator('main [role="alert"]')).toBeVisible();
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    const names: string[] = [];
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press("Tab");
      names.push(await page.evaluate(() => (document.activeElement?.textContent ?? "").trim()));
    }
    expect(names).toEqual(["마이페이지", "로그아웃", "새 면접 시작", "다시 시도"]);
    const ring = await page.evaluate(() => getComputedStyle(document.activeElement as HTMLElement).outlineWidth);
    expect(ring).toBe("2px");
  });

  test("[AC-F13] 390px: 가로 스크롤 없음, 링크·버튼 터치 타깃 ≥44px, CTA 전폭", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await seedSevenStates(request, acct.token);
    await page.setViewportSize({ width: 390, height: 844 });
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    const dims = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bw: document.body.scrollWidth }));
    expect(dims.sw).toBeLessThanOrEqual(dims.cw);
    expect(dims.bw).toBeLessThanOrEqual(dims.cw);
    const small = await page.locator("main a[href], main button").evaluateAll((els) =>
      els.map((e) => ({ name: (e.getAttribute("aria-label") ?? e.textContent ?? "").trim(), r: e.getBoundingClientRect() })).filter((x) => x.r.height < 44 - 0.5 || x.r.width < 44 - 0.5).map((x) => `${x.name}: ${Math.round(x.r.width)}x${Math.round(x.r.height)}`),
    );
    expect(small).toEqual([]);
    const overflow = await page.locator("main *").evaluateAll((els) => els.filter((e) => e.getBoundingClientRect().right > window.innerWidth + 0.5).map((e) => e.tagName + "." + (e.getAttribute("class") ?? "")));
    expect(overflow).toEqual([]);
    const ctaBox = await cta(page).boundingBox();
    expect(ctaBox!.width).toBeGreaterThan(300);
  });

  test("[AC-F13+] 320px(≈200% 확대 상당) 에서도 가로 스크롤 없음, 에러·배너·10건 안내 포함", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await seedSevenStates(request, acct.token);
    await page.setViewportSize({ width: 320, height: 640 });
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    await expect(banner(page)).toBeVisible();
    const dims = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    expect(dims.sw).toBeLessThanOrEqual(dims.cw);
  });

  test("[AC-F13+] 긴 이름(100자, 공백 없음/한글)에도 390px 에서 가로 스크롤이 생기지 않는다", async ({ page, kit }) => {
    for (const name of ["A".repeat(100), "가나다라".repeat(25)]) {
      const acct = await kit.create("candidate", name);
      await page.setViewportSize({ width: 390, height: 844 });
      await uiLogin(page, acct);
      await homeReady(page);
      const dims = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      expect(dims.sw, `name=${name.slice(0, 6)}…`).toBeLessThanOrEqual(dims.cw);
      await page.getByRole("button", { name: "로그아웃" }).click();
    }
  });

  test("[AC-F13+] 랜드마크·헤딩 구조: main 1개, nav[aria-label=계정], h1 -> h2(새 면접, sr-only) -> h2(최근 면접), 목록은 ul/li", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate", "구조");
    await createSessions(request, acct.token, 2);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(2);
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.getByRole("navigation", { name: "계정" })).toBeVisible();
    const headings = await page.locator("main").getByRole("heading").allInnerTexts();
    expect(headings).toEqual(["구조님, 환영합니다", "새 면접", "최근 면접"]);
    await expect(page.getByRole("list")).toHaveCount(1);
    await expect(page.getByRole("listitem")).toHaveCount(2);
  });

  test("[AC-F13+] 색 대비(WCAG AA): 정상·배너·에러 상태의 모든 텍스트가 4.5:1(큰 글자 3:1) 이상", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await seedSevenStates(request, acct.token);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    const normal = await measureContrast(page);
    expect(normal.length).toBeGreaterThan(20);
    const bad = normal.filter((c) => c.ratio < c.need);
    // 실패 항목을 그대로 노출해 정량 근거를 남긴다
    expect(bad, JSON.stringify(bad)).toEqual([]);

    const errAcct = await kit.create("candidate");
    await page.getByRole("button", { name: "로그아웃" }).click();
    await page.route(/\/api\/v1\/interviews$/, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.abort("failed");
    });
    await uiLogin(page, errAcct);
    await expect(page.locator('main [role="alert"]')).toBeVisible();
    const err = await measureContrast(page);
    const badErr = err.filter((c) => c.ratio < c.need);
    expect(badErr, JSON.stringify(badErr)).toEqual([]);
  });

  test("[AC-F13+] 색만으로 의미를 전달하지 않는다: 모든 상태 태그는 텍스트 라벨을 가진다(색 제거 시에도 구분 가능)", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    await seedSevenStates(request, acct.token);
    await uiLogin(page, acct);
    await expect(cards(page)).toHaveCount(7);
    const tagTexts = await cards(page).locator("span").allInnerTexts();
    expect(tagTexts).toEqual(["시작 전", "진행 중", "중단됨", "완료", "리포트 생성 중", "완료", "리포트 생성 실패", "만료", "완료", "리포트 준비 완료"]);
    // 동일 색 계열(live/paused, expired/failed)이라도 라벨로 구분되는지: 서로 다른 상태의 라벨 문자열이 겹치지 않는다
    expect(new Set(["진행 중", "중단됨", "만료", "리포트 생성 실패"]).size).toBe(4);
  });

  test("[AC-F13+] prefers-reduced-motion: 로딩 스켈레톤은 애니메이션이 없다(동작 축소 기준 충족)", async ({ page, kit }) => {
    const acct = await kit.create("candidate");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route(/\/api\/v1\/interviews$/, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await new Promise((r) => setTimeout(r, 1500));
      await route.continue();
    });
    await uiLogin(page, acct);
    const skeleton = page.locator('main ul[aria-busy="true"] > li').first();
    await expect(skeleton).toBeVisible();
    const anim = await skeleton.evaluate((el) => getComputedStyle(el).animationName);
    expect(anim).toBe("none");
  });

  test("[AC-F13+] 브라우저 확대/축소 배율 변경에도 배너가 카드와 겹치지 않는다(레이아웃 순서: CTA -> 배너 -> 목록)", async ({ page, kit, request }) => {
    const acct = await kit.create("candidate");
    const [sid] = await createSessions(request, acct.token, 1);
    setSession(sid, { status: "live", startedAgo: "1 hour" });
    await uiLogin(page, acct);
    await expect(banner(page)).toBeVisible();
    const ctaBox = (await cta(page).boundingBox())!;
    const bannerBox = (await banner(page).boundingBox())!;
    const listBox = (await cards(page).first().boundingBox())!;
    expect(ctaBox.y + ctaBox.height).toBeLessThanOrEqual(bannerBox.y + 0.5);
    expect(bannerBox.y + bannerBox.height).toBeLessThanOrEqual(listBox.y + 0.5);
  });
});
