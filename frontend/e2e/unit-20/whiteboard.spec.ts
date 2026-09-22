// unit-20 06단계 — 화이트보드 패널 배선: 그리기/저장/복원/좌표계/오류/터치. TC-B3, B9.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  TAB_WB,
  box,
  call,
  canvasPoint,
  createRoom,
  drawStroke,
  hasInkNear,
  openRoom,
  openWhiteboardPanel,
  sidePanel,
  tab,
  watchConsole,
  watchRequests,
  whiteboardCanvas,
} from "./support";

const saveBtn = (page: import("@playwright/test").Page) => sidePanel(page).getByRole("button", { name: "저장", exact: true });
const putResponse = (page: import("@playwright/test").Page) =>
  page.waitForResponse((r) => /\/whiteboard$/.test(r.url()) && r.request().method() === "PUT");

test.describe("데스크톱 1280x900", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("캔버스가 패널 폭 안에 맞고 640:400 비율 유지, 흰 배경", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    const cv = await box(whiteboardCanvas(page));
    const pn = await box(sidePanel(page));
    expect(cv.x).toBeGreaterThanOrEqual(pn.x);
    expect(cv.x + cv.width).toBeLessThanOrEqual(pn.x + pn.width);
    expect(Math.abs(cv.width / cv.height - 1.6)).toBeLessThan(0.02);
    expect(cv.width).toBeGreaterThan(300);
    const bg = await whiteboardCanvas(page).evaluate((c) => getComputedStyle(c).backgroundColor);
    expect(bg).toBe("rgb(255, 255, 255)");
  });

  test("그리기 → 저장 PUT 200: 저장 좌표계는 640x400 논리 좌표(CSS 스케일에 무관), 색·굵기 반영, 새로고침 후 픽셀 복원", async ({ page }) => {
    const problems = watchConsole(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    await page.getByRole("button", { name: "색상 #3b82f6" }).click();
    await drawStroke(page, [0.25, 0.25], [0.75, 0.75]);
    expect(await hasInkNear(page, 320, 200)).toBe(true); // 화면에 실제로 그려짐(중앙)
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).click()]);
    expect(resp.status()).toBe(200);
    const body = JSON.parse(resp.request().postData() ?? "{}");
    expect(body.strokes).toHaveLength(1);
    const pts = body.strokes[0].points as { x: number; y: number }[];
    expect(pts.length).toBeGreaterThan(2);
    expect(Math.abs(pts[0].x - 160)).toBeLessThan(3);
    expect(Math.abs(pts[0].y - 100)).toBeLessThan(3);
    expect(Math.abs(pts[pts.length - 1].x - 480)).toBeLessThan(3);
    expect(Math.abs(pts[pts.length - 1].y - 300)).toBeLessThan(3);
    expect(body.strokes[0].color).toBe("#3b82f6");
    expect(body.strokes[0].width).toBe(3);
    await expect(sidePanel(page).getByText("저장됨", { exact: true })).toBeVisible();
    await page.reload();
    await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
    await openWhiteboardPanel(page);
    await expect.poll(() => hasInkNear(page, 320, 200)).toBe(true);
    expect(await hasInkNear(page, 60, 350)).toBe(false); // 그리지 않은 곳은 비어 있음
    expect(problems).toEqual([]);
  });

  test("굵기 슬라이더 최대(12)로 그린 스트로크의 width=12 저장", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    await sidePanel(page).getByRole("slider").fill("12");
    await drawStroke(page, [0.2, 0.5], [0.8, 0.5]);
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).click()]);
    expect(JSON.parse(resp.request().postData() ?? "{}").strokes[0].width).toBe(12);
  });

  test("지우기 → 픽셀 제거, 빈 캔버스 저장(strokes=[]) → 새로고침 후에도 빈 캔버스", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await call("PUT", `/interviews/${room.interviewId}/whiteboard`, room.account.token, {
      strokes: [{ points: [{ x: 100, y: 100 }, { x: 500, y: 300 }], color: "#ef4444", width: 5 }],
    });
    await page.reload();
    await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
    await openWhiteboardPanel(page);
    await expect.poll(() => hasInkNear(page, 300, 200)).toBe(true); // 서버에 있던 스냅샷 복원
    await sidePanel(page).getByRole("button", { name: "지우기" }).click();
    expect(await hasInkNear(page, 300, 200)).toBe(false);
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).click()]);
    expect(JSON.parse(resp.request().postData() ?? "{}").strokes).toEqual([]);
    await page.reload();
    await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
    await openWhiteboardPanel(page);
    await page.waitForTimeout(500);
    expect(await hasInkNear(page, 300, 200)).toBe(false);
  });

  test("제자리 클릭(점 1개)은 스트로크로 저장되지 않는다(경계)", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    const p = await canvasPoint(page, 0.5, 0.5);
    await page.mouse.click(p.x, p.y);
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).click()]);
    expect(JSON.parse(resp.request().postData() ?? "{}").strokes).toEqual([]);
  });

  test("저장 전 그림은 탭 전환(코드 탭 다녀옴)·패널 닫기 후에도 유지되고 재조회하지 않는다", async ({ page }) => {
    const reqs = watchRequests(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    await drawStroke(page, [0.2, 0.2], [0.6, 0.4]);
    const gets = () => reqs.filter((r) => /\/whiteboard$/.test(r.url) && r.method === "GET").length;
    const before = gets();
    await tab(page, TAB_CODE).click();
    await tab(page, TAB_WB).click();
    expect(await hasInkNear(page, 256, 160, 8)).toBe(true);
    await sidePanel(page).getByRole("button", { name: "채팅으로 돌아가기" }).click();
    await tab(page, TAB_WB).click();
    expect(await hasInkNear(page, 256, 160, 8)).toBe(true);
    expect(gets()).toBe(before);
  });

  test("복원 GET 실패 → '이전 캔버스를 불러오지 못했습니다.' 후 빈 캔버스에 그리고 저장 가능", async ({ page }) => {
    const problems = watchConsole(page, [/Failed to load resource/]);
    const room = await createRoom("live");
    await page.route(/\/whiteboard$/, (route) => (route.request().method() === "GET" ? route.abort() : route.fallback()));
    await openRoom(page, room);
    await tab(page, TAB_WB).click();
    await expect(sidePanel(page).getByText("이전 캔버스를 불러오지 못했습니다.")).toBeVisible();
    await drawStroke(page, [0.3, 0.3], [0.7, 0.7]);
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).click()]);
    expect(resp.status()).toBe(200);
    expect(problems.filter((p) => p.startsWith("[pageerror]"))).toEqual([]);
  });

  test("저장 실패(PUT 500) → '저장되지 않았습니다.' 표시, 재시도 성공 → '저장됨'", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openWhiteboardPanel(page);
    await drawStroke(page, [0.3, 0.3], [0.7, 0.7]);
    await page.route(/\/whiteboard$/, (route) => (route.request().method() === "PUT" ? route.fulfill({ status: 500, body: "err" }) : route.fallback()));
    await saveBtn(page).click();
    await expect(sidePanel(page).getByText("저장되지 않았습니다.")).toBeVisible();
    expect(await hasInkNear(page, 320, 200)).toBe(true); // 로컬 그림은 보존
    await page.unroute(/\/whiteboard$/);
    await saveBtn(page).click();
    await expect(sidePanel(page).getByText("저장됨", { exact: true })).toBeVisible();
  });
});

test.describe("모바일 390x800 (터치)", () => {
  test.use({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });

  test("모달 안 캔버스가 뷰포트에 맞고, 터치 드래그로 그려지며 페이지가 스크롤되지 않고, 저장 좌표가 논리 좌표로 환산된다", async ({ page, context }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    // tab(...).tap() 만으로 이미 모달이 열린다 — openWhiteboardPanel()을 또 호출하면 탭 버튼이
    // (이제 inert 처리된 툴바 뒤로 가려진 채) 다시 클릭되어 같은 화면 좌표의 다른 요소(색상
    // 스와치)가 클릭을 가로채 타임아웃한다(06단계에서 발견한 테스트 중복 호출 버그).
    await tab(page, TAB_WB).tap();
    await sidePanel(page).getByRole("heading", { name: TAB_WB }).waitFor();
    await whiteboardCanvas(page).waitFor();
    await page.getByText("캔버스를 불러오는 중...").waitFor({ state: "hidden" });
    const cv = await box(whiteboardCanvas(page));
    expect(cv.x).toBeGreaterThanOrEqual(0);
    expect(cv.x + cv.width).toBeLessThanOrEqual(390);
    const cdp = await context.newCDPSession(page);
    const a = { x: cv.x + cv.width * 0.25, y: cv.y + cv.height * 0.5 };
    const b = { x: cv.x + cv.width * 0.75, y: cv.y + cv.height * 0.5 };
    const scrollBefore = await page.evaluate(() => window.scrollY + document.querySelector("#interview-side-panel")!.scrollTop);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [a] });
    for (let i = 1; i <= 8; i++) {
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: a.x + ((b.x - a.x) * i) / 8, y: a.y + i * 3 }],
      });
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    const scrollAfter = await page.evaluate(() => window.scrollY + document.querySelector("#interview-side-panel")!.scrollTop);
    expect(scrollAfter).toBe(scrollBefore); // touch-action:none — 그리는 동안 스크롤 없음
    expect(await hasInkNear(page, 320, 200, 20)).toBe(true);
    const [resp] = await Promise.all([putResponse(page), saveBtn(page).tap()]);
    expect(resp.status()).toBe(200);
    const pts = JSON.parse(resp.request().postData() ?? "{}").strokes[0].points as { x: number; y: number }[];
    expect(Math.abs(pts[0].x - 160)).toBeLessThan(4);
    expect(Math.abs(pts[pts.length - 1].x - 480)).toBeLessThan(4);
  });
});
