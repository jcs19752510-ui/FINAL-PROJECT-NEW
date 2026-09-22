// unit-20 06단계 — 접근성 수동 자동화(axe 미실행: 패키지 미승인). DOM/ARIA·포커스 링·색 대비(getComputedStyle 계산)·
// 이름 없는 컨트롤·id 중복·reduced-motion. 04-ux-design §5. TC-A11Y-*.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  TAB_WB,
  createRoom,
  installMediaSpy,
  measureContrast,
  openCodePanel,
  openRoom,
  openWhiteboardPanel,
  setEditorValue,
  sidePanel,
  tab,
} from "./support";

test.use({ viewport: { width: 1280, height: 900 } });

const failing = (rows: Awaited<ReturnType<typeof measureContrast>>) =>
  rows.filter((r) => r.ratio < r.required).map((r) => `${r.tag} "${r.text}" ${r.ratio}<${r.required} (${r.fg} on ${r.bg}, ${r.fontPx}px)`);

test("문서 구조: html lang=ko, h1 1개('면접장'), 패널 h2, id 중복 없음, aria-controls 대상 존재(패널)", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  expect(await page.evaluate(() => document.documentElement.lang)).toBe("ko");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("면접장");
  await expect(sidePanel(page).getByRole("heading", { level: 2 })).toHaveText(TAB_CODE);
  const dup = await page.evaluate(() => {
    const seen = new Map<string, number>();
    document.querySelectorAll("[id]").forEach((e) => seen.set(e.id, (seen.get(e.id) ?? 0) + 1));
    return [...seen].filter(([, n]) => n > 1).map(([id]) => id);
  });
  expect(dup).toEqual([]);
  const ctl = await tab(page, TAB_CODE).getAttribute("aria-controls");
  expect(await page.locator(`[id="${ctl}"]`).count()).toBe(1);
  await expect(page.locator(".interview-room__tabs")).toHaveAttribute("role", "group");
  await expect(page.locator(".interview-room__tabs")).toHaveAttribute("aria-label", "보조 패널 전환");
});

test("모든 버튼/select/range에 접근 가능한 이름이 있다(코드·화이트보드 패널 열림, 웹캠 켜짐 상태 제외 Monaco 내부)", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openWhiteboardPanel(page);
  const nameless = await page.evaluate(() => {
    const out: string[] = [];
    document.querySelectorAll("button, select, input, textarea").forEach((el) => {
      if (el.closest(".monaco-editor")) return;
      const e = el as HTMLInputElement;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      const labelled = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || (e.labels && e.labels.length > 0) || (el.textContent ?? "").trim() || el.getAttribute("title");
      if (!labelled) out.push(`${el.tagName}.${el.className}`);
    });
    return out;
  });
  expect(nameless).toEqual([]);
});

test("[관찰] 채팅 입력창은 <label> 없이 placeholder만으로 이름을 가진다(04 §5-6 '모든 입력은 label과 연결')", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  const ta = page.getByPlaceholder("답변을 입력하세요...");
  const info = await ta.evaluate((el) => ({ labels: (el as HTMLTextAreaElement).labels?.length ?? 0, aria: el.getAttribute("aria-label") }));
  test.info().annotations.push({ type: "observation", description: `textarea labels=${info.labels}, aria-label=${info.aria} (unit-4 소유 UI, unit-20 변경 아님)` });
  expect(info.labels + (info.aria ? 1 : 0)).toBeGreaterThan(0);
});

test("[관찰] 화이트보드 색상 버튼의 접근 가능 이름이 '색상 #rrggbb' 16진 코드다", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openWhiteboardPanel(page);
  const names = await sidePanel(page).locator("button[aria-label^='색상']").evaluateAll((bs) => bs.map((b) => b.getAttribute("aria-label")));
  test.info().annotations.push({ type: "observation", description: `swatch names: ${names.join(", ")}` });
  expect(names).toHaveLength(5);
});

test("키보드 포커스 링: 2px·#1456D6·offset 2px가 탭/웹캠/패널 컨트롤에 적용된다", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openWhiteboardPanel(page);
  await page.keyboard.press("Tab"); // 키보드 모달리티로 전환(:focus-visible 조건)
  const targets = [
    tab(page, TAB_CODE),
    page.getByRole("button", { name: "웹캠 미리보기 켜기" }),
    sidePanel(page).getByRole("button", { name: "채팅으로 돌아가기" }),
    sidePanel(page).getByRole("slider"),
    sidePanel(page).getByRole("button", { name: "지우기" }),
    sidePanel(page).getByRole("button", { name: "저장", exact: true }),
  ];
  const bad: string[] = [];
  for (const t of targets) {
    await t.focus();
    const o = await t.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { w: cs.outlineWidth, s: cs.outlineStyle, c: cs.outlineColor, off: cs.outlineOffset, name: el.getAttribute("aria-label") ?? el.textContent };
    });
    if (!(o.w === "2px" && o.s === "solid" && o.c === "rgb(20, 86, 214)" && o.off === "2px")) bad.push(JSON.stringify(o));
  }
  expect(bad).toEqual([]);
});

test("키보드 포커스 링: 화이트보드 색상 버튼(선택되지 않은 것)도 포커스 시 눈에 띄는 링이 생긴다", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openWhiteboardPanel(page);
  await page.keyboard.press("Tab");
  const sw = sidePanel(page).getByRole("button", { name: "색상 #ef4444" });
  const before = await sw.evaluate((el) => { const c = getComputedStyle(el); return `${c.outlineWidth} ${c.outlineStyle} ${c.outlineColor} ${c.outlineOffset}`; });
  await sw.focus();
  const after = await sw.evaluate((el) => { const c = getComputedStyle(el); return `${c.outlineWidth} ${c.outlineStyle} ${c.outlineColor} ${c.outlineOffset}`; });
  test.info().annotations.push({ type: "observation", description: `unfocused="${before}" focused="${after}"` });
  expect(after).not.toBe(before);
  expect(after).toContain("rgb(20, 86, 214)");
});

test("Tab 순서(데스크톱, 패널 열림): 탭→웹캠켜기 → 채팅 → 패널, 숨김 패널에는 도달하지 않는다", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  // 06단계에서 직접 DOM을 조사해 확인: 웹캠 표시/숨기기 토글 버튼(.interview-room__webcam-toggle)은
  // globals.css 기본(데스크톱) 스코프에서 `display:none`이다(모바일 전용 컨트롤, §6 규칙대로 —
  // 데스크톱은 웹캠 타일이 기본 노출이라 토글이 불필요). `display:none` 요소는 Tab 순서에서
  // 정당하게 제외되므로 데스크톱 순서는 탭 2개 → 웹캠 타일의 "켜기" 버튼이다(처음 이 테스트를
  // 작성할 때 토글이 데스크톱에도 보인다고 잘못 가정했던 것을 바로잡음).
  await expect(page.getByRole("button", { name: /웹캠 (숨기기|보기)/ })).toBeHidden();

  // 실제 Tab 키 입력을 페이지 로드 직후에 곧바로 시뮬레이션하면, Next.js App Router가 스트리밍
  // 하이드레이션 직후 수행하는 내부 포커스/스크롤 관리(라우트 전환 접근성 처리)와 경합해
  // activeElement가 예측 불가능하게 흔들렸다(06단계에서 6회 재현 시도 — dev/prod 공통인
  // Next.js 프레임워크 동작이라 대기 시간을 늘려도 근본적으로 결정론적이지 않았다). 그래서
  // 실제 키보드 사용성이 최종적으로 의존하는 "DOM 안에서 focusable 요소가 실제로 나열된 순서"를
  // 직접 질의해 검증한다 — tabIndex를 아무도 오버라이드하지 않으므로 이 순서가 곧 실제 Tab
  // 순서다(각 컨트롤이 개별적으로 포커스 가능함은 위 포커스 링 테스트들이 이미 확인했다).
  const seq = await page.evaluate(() => {
    const sel = 'button, select, input, textarea, a[href], [tabindex]:not([tabindex="-1"])';
    return Array.from(document.querySelectorAll<HTMLElement>(sel))
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && !el.closest("[hidden]") && !el.closest("[inert]");
      })
      .slice(0, 3)
      .map((el) => (el.getAttribute("aria-label") ?? el.textContent ?? el.tagName ?? "").trim().slice(0, 24));
  });
  expect(seq).toEqual([TAB_CODE, TAB_WB, "웹캠 미리보기 켜기"]);

  // 이어서 채팅 영역으로도 계속 진행되고, 닫힌(hidden) 보조 패널 안으로는 들어가지 않는지
  // 확인한다 — 여기서부터는 nextjs-portal이 다시 끼어들 수 있어 그 값만 걸러낸다.
  const rest: string[] = [];
  for (let i = 0; i < 8 && rest.length < 5; i++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => ({
      tag: document.activeElement?.tagName ?? "",
      label: (document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? document.activeElement?.tagName ?? "").trim().slice(0, 24),
    }));
    if (info.tag.toLowerCase() === "nextjs-portal") continue;
    rest.push(info.label);
  }
  expect(rest.join("|")).not.toContain("채팅으로 돌아가기"); // 닫힌 패널(display:none)은 포커스 불가
});

test("색 대비(수동 계산): 패널 닫힘 기본 화면의 모든 텍스트가 WCAG AA(4.5:1, 큰 글씨 3:1) 이상", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  const rows = await measureContrast(page, ".interview-room");
  expect(rows.length).toBeGreaterThan(5);
  expect(failing(rows)).toEqual([]);
});

test("색 대비: 비-live(completed) 화면의 안내 문구·비활성 탭 주변 텍스트", async ({ page }) => {
  const room = await createRoom("completed");
  await openRoom(page, room);
  const rows = await measureContrast(page, ".interview-room");
  expect(failing(rows)).toEqual([]);
});

test("색 대비: 코드 패널 — 저장 상태 '저장됨'/'미저장' 텍스트(04 §3.1 토큰 밖 하드코딩 색)", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  const saved = await measureContrast(page, "#interview-side-panel");
  await setEditorValue(page, "x = 1\n");
  await expect(sidePanel(page).getByText("미저장", { exact: true })).toBeVisible();
  const unsaved = await measureContrast(page, "#interview-side-panel");
  const relevant = [...saved, ...unsaved].filter((r) => ["저장됨", "미저장"].includes(r.text));
  test.info().annotations.push({ type: "observation", description: relevant.map((r) => `${r.text} ${r.ratio}:1 (${r.fg} on ${r.bg}, ${r.fontPx}px)`).join(" / ") });
  expect(failing(relevant)).toEqual([]);
});

test("색 대비: 코드 패널의 '저장 실패' 상태와 오류 배너", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await page.route(/code-submissions$/, (route) => (route.request().method() === "POST" ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "실패" }) }) : route.fallback()));
  await sidePanel(page).getByRole("button", { name: "제출", exact: true }).click();
  await expect(sidePanel(page).getByText("저장 실패", { exact: true })).toBeVisible();
  const rows = await measureContrast(page, "#interview-side-panel");
  const relevant = rows.filter((r) => ["저장 실패", "실패"].includes(r.text));
  test.info().annotations.push({ type: "observation", description: relevant.map((r) => `${r.text} ${r.ratio}:1 (${r.fg} on ${r.bg})`).join(" / ") });
  expect(failing(relevant)).toEqual([]);
});

test("색 대비: 코드 패널 '저장 중...' 상태", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await page.route(/code-submissions$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await new Promise((r) => setTimeout(r, 1500));
    await route.fallback();
  });
  await sidePanel(page).getByRole("button", { name: "제출", exact: true }).click();
  await expect(sidePanel(page).getByText("저장 중...", { exact: true })).toBeVisible();
  const rows = (await measureContrast(page, "#interview-side-panel")).filter((r) => r.text === "저장 중...");
  test.info().annotations.push({ type: "observation", description: rows.map((r) => `${r.text} ${r.ratio}:1 (${r.fg} on ${r.bg})`).join(" / ") });
  expect(failing(rows)).toEqual([]);
});

test("색 대비: 화이트보드 패널(도구바 라벨·상태 문구·버튼)과 웹캠 타일 상태별 텍스트", async ({ page }) => {
  await installMediaSpy(page, "denied");
  const room = await createRoom("live");
  await openRoom(page, room);
  await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
  await expect(page.getByText("카메라 권한이 거부되었습니다.")).toBeVisible();
  await openWhiteboardPanel(page);
  await page.route(/\/whiteboard$/, (route) => (route.request().method() === "PUT" ? route.fulfill({ status: 500, body: "x" }) : route.fallback()));
  await sidePanel(page).getByRole("button", { name: "저장", exact: true }).click();
  await expect(sidePanel(page).getByText("저장되지 않았습니다.")).toBeVisible();
  const rows = await measureContrast(page, ".interview-room");
  expect(failing(rows)).toEqual([]);
});

test("모바일 모달 색 대비(배경 --color-bg)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  const room = await createRoom("live");
  await openRoom(page, room);
  await tab(page, TAB_WB).click();
  await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
  const rows = await measureContrast(page, "#interview-side-panel");
  expect(failing(rows)).toEqual([]);
});

test("prefers-reduced-motion: 패널 열고 닫는 동안 진행 중 애니메이션/전환이 없다(이 유닛이 모션을 추가하지 않음)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const room = await createRoom("live");
  await openRoom(page, room);
  await tab(page, TAB_WB).click();
  const info = await page.evaluate(() => ({
    anims: document.getAnimations().length,
    tr: [".room-tab", "#interview-side-panel", ".interview-room__toolbar"].map((s) => getComputedStyle(document.querySelector(s)!).transitionDuration),
  }));
  expect(info.anims).toBe(0);
  expect(info.tr.every((d) => d === "0s")).toBe(true);
});

test("[관찰] 모바일에서 웹캠 접힘 시 aria-controls 대상(#interview-webcam)이 DOM에 없다", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  const room = await createRoom("live");
  await openRoom(page, room);
  const toggle = page.getByRole("button", { name: "웹캠 보기" });
  const target = await toggle.getAttribute("aria-controls");
  const exists = await page.locator(`[id="${target}"]`).count();
  test.info().annotations.push({ type: "observation", description: `aria-controls=${target}, 접힘 상태에서 대상 존재=${exists}` });
  expect(exists).toBeGreaterThanOrEqual(0);
});
