// unit-20 06단계 — 모바일(<768) 전체화면 모달·포커스·inert·터치 타깃·가로 스크롤·웹캠 토글. TC-B6.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  TAB_WB,
  box,
  createRoom,
  docScrollsHorizontally,
  installMediaSpy,
  mediaState,
  monacoReady,
  openCodePanel,
  openRoom,
  sidePanel,
  tab,
  watchConsole,
} from "./support";

test.use({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });

test.describe("모바일 390x800 — 웹캠 토글", () => {
  test("뷰포트 메타 적용(innerWidth=390), 웹캠 토글 기본 접힘→펼침, 버튼 높이 ≥44", async ({ page }) => {
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    expect(await page.evaluate(() => window.innerWidth)).toBe(390);
    const toggle = page.getByRole("button", { name: "웹캠 보기" });
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toHaveCount(0);
    expect((await box(toggle)).height).toBeGreaterThanOrEqual(44);
    for (const name of [TAB_CODE, TAB_WB]) expect((await box(tab(page, name))).height).toBeGreaterThanOrEqual(44);
    await toggle.click();
    await expect(page.getByRole("button", { name: "웹캠 숨기기" })).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toBeVisible();
    const on = page.getByRole("button", { name: "웹캠 미리보기 켜기" });
    expect((await box(on)).height).toBeGreaterThanOrEqual(44);
    expect((await mediaState(page)).calls).toBe(0);
    expect(await docScrollsHorizontally(page)).toBe(false);
  });
});

test.describe("모바일 390x800 — 전체화면 모달", () => {
  test("열림: 뷰포트 전체 덮음·role=dialog·aria-modal·aria-labelledby·배경 inert·제목으로 포커스", async ({ page }) => {
    const problems = watchConsole(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    const panel = sidePanel(page);
    await expect(panel).toBeVisible();
    await expect(panel).toHaveAttribute("role", "dialog");
    await expect(panel).toHaveAttribute("aria-modal", "true");
    const b = await box(panel);
    expect([Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]).toEqual([0, 0, 390, 800]);
    const labelId = await panel.getAttribute("aria-labelledby");
    expect(labelId).toBeTruthy();
    await expect(page.locator(`[id="${labelId}"]`)).toHaveText(TAB_WB);
    await expect(page.locator(".interview-room__toolbar")).toHaveAttribute("inert", "");
    await expect(page.locator(".interview-room__chat")).toHaveAttribute("inert", "");
    const active = await page.evaluate(() => ({ tag: document.activeElement?.tagName, id: document.activeElement?.id, text: document.activeElement?.textContent }));
    expect(active).toMatchObject({ tag: "H2", text: TAB_WB });
    expect(await docScrollsHorizontally(page)).toBe(false);
    expect(problems).toEqual([]);
  });

  test("Esc로 닫힘 + 포커스가 열었던 탭으로 복귀 + inert/dialog 해제", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    await expect(sidePanel(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sidePanel(page)).toBeHidden();
    await expect(page.locator(".interview-room__toolbar")).not.toHaveAttribute("inert", /.*/);
    await expect(tab(page, TAB_WB)).toBeFocused();
    await expect(tab(page, TAB_WB)).toHaveAttribute("aria-pressed", "false");
  });

  test("'채팅으로 돌아가기' 버튼(44px)으로 닫힘 + 포커스 복귀", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_CODE).tap();
    const back = sidePanel(page).getByRole("button", { name: "채팅으로 돌아가기" });
    expect((await box(back)).height).toBeGreaterThanOrEqual(44);
    await back.tap();
    await expect(sidePanel(page)).toBeHidden();
    await expect(tab(page, TAB_CODE)).toBeFocused();
  });

  test("Monaco 안에서의 Esc는 패널을 닫지 않는다(자동완성 등 위젯용)", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_CODE).tap();
    await monacoReady(page);
    await sidePanel(page).locator(".monaco-editor textarea").first().focus();
    await page.keyboard.press("Escape");
    await expect(sidePanel(page)).toBeVisible();
    await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
  });

  test("모달 안 빈 영역을 누른 뒤 Esc → 닫힘(04 §5-3 '모달은 Esc로 닫힘')", async ({ page }) => {
    // 결함 후보: Esc 핸들러가 aside의 onKeyDown이라, 포커스가 body로 빠지면(빈 영역 클릭) Esc가 동작하지 않을 수 있다.
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    await expect(sidePanel(page)).toBeVisible();
    const b = await box(sidePanel(page));
    await page.touchscreen.tap(b.x + b.width - 8, b.y + b.height - 8); // 패널 우하단의 빈 영역
    const focusInside = await page.evaluate(() => document.querySelector("#interview-side-panel")!.contains(document.activeElement));
    test.info().annotations.push({ type: "observation", description: `빈 영역 탭 후 포커스가 패널 안: ${focusInside}` });
    await page.keyboard.press("Escape");
    await expect(sidePanel(page)).toBeHidden({ timeout: 2000 });
  });

  test("Tab 키를 25회 눌러도 포커스가 모달 밖(inert 배경)으로 나가지 않는다", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    await expect(sidePanel(page)).toBeVisible();
    const escaped: string[] = [];
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const ae = document.activeElement;
        const inside = document.querySelector("#interview-side-panel")!.contains(ae);
        return { inside, body: ae === document.body, desc: `${ae?.tagName}.${(ae as HTMLElement | null)?.className}` };
      });
      if (!info.inside && !info.body) escaped.push(info.desc);
    }
    expect(escaped).toEqual([]);
  });

  test("터치 타깃: 모달 안 모든 보이는 버튼/select/range가 44x44 이상(Monaco 내부 제외)", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    await expect(sidePanel(page)).toBeVisible();
    const small = await page.evaluate(() => {
      const out: string[] = [];
      document.querySelectorAll("#interview-side-panel button, #interview-side-panel select, #interview-side-panel input").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (r.width < 43.5 || r.height < 43.5) {
          out.push(`${el.tagName}[${(el as HTMLElement).getAttribute("aria-label") ?? (el as HTMLInputElement).type ?? el.textContent}] ${Math.round(r.width)}x${Math.round(r.height)}`);
        }
      });
      return out;
    });
    expect(small).toEqual([]);
  });

  test("웹캠 타일 버튼(모바일) 44px, 접히면 카메라 트랙 정지", async ({ page }) => {
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 보기" }).tap();
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).tap();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    const off = await box(page.getByRole("button", { name: "웹캠 미리보기 끄기" }));
    expect(off.height).toBeGreaterThanOrEqual(44);
    expect((await mediaState(page)).liveTracks).toBe(1);
    await page.getByRole("button", { name: "웹캠 숨기기" }).tap();
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toHaveCount(0);
    await expect.poll(async () => (await mediaState(page)).liveTracks).toBe(0);
  });

  test("가로 스크롤 없음: 320px·390px·640px(=200% 확대 환산)에서 패널 닫힘/열림/웹캠 펼침", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    for (const w of [320, 390, 640]) {
      await page.setViewportSize({ width: w, height: 800 });
      await page.getByRole("button", { name: /웹캠 (보기|숨기기)/ }).first().evaluate((el) => {
        if (el.textContent === "웹캠 보기") (el as HTMLButtonElement).click();
      });
      expect(await docScrollsHorizontally(page), `${w}px 패널 닫힘`).toBe(false);
      await tab(page, TAB_WB).tap();
      await expect(sidePanel(page)).toBeVisible();
      expect(await docScrollsHorizontally(page), `${w}px 화이트보드 모달`).toBe(false);
      const cv = await box(sidePanel(page).locator("canvas"));
      expect(cv.x + cv.width).toBeLessThanOrEqual(w);
      await page.keyboard.press("Escape");
      await expect(sidePanel(page)).toBeHidden();
    }
  });

  test("모달 열린 채 창을 1280으로 키우면(회전/리사이즈) dialog·inert 해제되고 분할 뷰로 전환", async ({ page }) => {
    const problems = watchConsole(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).tap();
    await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(sidePanel(page)).not.toHaveAttribute("role", /.+/);
    await expect(page.locator(".interview-room__toolbar")).not.toHaveAttribute("inert", /.*/);
    await expect(page.locator(".interview-room--split")).toHaveCount(1);
    await expect(sidePanel(page)).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("[관찰 Q2 보강] 화면 회전 등으로 데스크톱→모바일 전환 시 열려 있던 패널은 모달로 이어진다", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).click();
    await page.setViewportSize({ width: 390, height: 800 });
    await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
    await expect(sidePanel(page)).toBeVisible();
  });
});
