// unit-20 06단계 — 면접장 레이아웃/보조 패널 토글/세션 상태별 동작/로딩·오류·권한 경계. TC-B1~B2, B5, B8, B9(GET 실패), A1.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  TAB_WB,
  box,
  createAccount,
  createRoom,
  docScrollsHorizontally,
  forceInterviewStatus,
  installMediaSpy,
  mediaState,
  mockInterviewWs,
  monacoReady,
  openCodePanel,
  openRoom,
  openWhiteboardPanel,
  sidePanel,
  splitRatio,
  tab,
  watchConsole,
  watchRequests,
} from "./support";

test.describe("데스크톱 1280x900 — live 세션 기본 상태와 60:40 분할", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("초기: 탭 2개 활성·aria-pressed=false·패널 숨김·웹캠 off·웹캠 토글 숨김·권한 프롬프트 없음", async ({ page }) => {
    const problems = watchConsole(page);
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    for (const name of [TAB_CODE, TAB_WB]) {
      await expect(tab(page, name)).toBeEnabled();
      await expect(tab(page, name)).toHaveAttribute("aria-pressed", "false");
      await expect(tab(page, name)).toHaveAttribute("aria-controls", "interview-side-panel");
    }
    await expect(sidePanel(page)).toBeHidden();
    await expect(sidePanel(page)).toHaveAttribute("hidden", "");
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toBeVisible();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 켜기" })).toBeVisible();
    await expect(page.getByRole("button", { name: /웹캠 (숨기기|보기)/ })).toBeHidden(); // 데스크톱은 토글 없음
    await expect(page.locator(".room-tabs__note")).toHaveCount(0);
    await page.waitForTimeout(1500);
    expect((await mediaState(page)).calls).toBe(0); // 켜기를 누르기 전엔 getUserMedia 미호출
    expect(problems).toEqual([]);
  });

  test("코드 탭: 패널 열림·60:40(±3%p)·dialog 시맨틱 없음·제목·Monaco, 같은 탭 재클릭으로 닫힘", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openCodePanel(page);
    await expect(sidePanel(page)).toBeVisible();
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "true");
    await expect(tab(page, TAB_WB)).toHaveAttribute("aria-pressed", "false");
    await expect(sidePanel(page)).not.toHaveAttribute("role", /.+/);
    await expect(sidePanel(page)).not.toHaveAttribute("aria-modal", /.+/);
    const ratio = await splitRatio(page);
    expect(ratio).toBeGreaterThan(0.57);
    expect(ratio).toBeLessThan(0.63);
    await tab(page, TAB_CODE).click();
    await expect(sidePanel(page)).toBeHidden();
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "false");
  });

  test("코드↔화이트보드 번갈아 전환: 한 번에 하나만 보이고 각 패널이 유지된다", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await openCodePanel(page);
    await openWhiteboardPanel(page);
    await expect(sidePanel(page).getByRole("heading", { name: TAB_WB })).toBeVisible();
    await expect(sidePanel(page).locator(".monaco-editor").first()).toBeHidden(); // 코드 패널은 hidden(언마운트 아님)
    await expect(tab(page, TAB_WB)).toHaveAttribute("aria-pressed", "true");
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "false");
    await tab(page, TAB_CODE).click();
    await expect(sidePanel(page).locator(".monaco-editor").first()).toBeVisible();
    await expect(sidePanel(page).locator("canvas")).toBeHidden();
  });

  test("채팅으로 돌아가기: 패널 닫힘·채팅 레이아웃 복귀(패널 폭 0)", async ({ page }) => {
    const room = await createRoom("live");
    await openRoom(page, room);
    await tab(page, TAB_WB).click();
    await sidePanel(page).getByRole("button", { name: "채팅으로 돌아가기" }).click();
    await expect(sidePanel(page)).toBeHidden();
    await expect(page.locator(".interview-room--split")).toHaveCount(0);
    await expect(tab(page, TAB_WB)).toHaveAttribute("aria-pressed", "false");
  });

  test("빠른 연타(코드 탭 11회 클릭)에도 최종 상태가 일관된다(홀수 → 열림)", async ({ page }) => {
    const problems = watchConsole(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    for (let i = 0; i < 11; i++) await tab(page, TAB_CODE).click({ delay: 0 });
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "true");
    await expect(sidePanel(page)).toBeVisible();
    await monacoReady(page);
    expect(problems).toEqual([]);
  });
});

test.describe("브레이크포인트 경계(04 §6)", () => {
  const cases: { w: number; mode: "modal" | "half" | "sixty" }[] = [
    { w: 767, mode: "modal" },
    { w: 768, mode: "half" },
    { w: 1199, mode: "half" },
    { w: 1200, mode: "sixty" },
    { w: 1440, mode: "sixty" },
  ];
  for (const c of cases) {
    test(`${c.w}px → ${c.mode}`, async ({ page }) => {
      await page.setViewportSize({ width: c.w, height: 900 });
      const room = await createRoom("live");
      await openRoom(page, room);
      await tab(page, TAB_WB).click();
      await expect(sidePanel(page)).toBeVisible();
      if (c.mode === "modal") {
        await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
        await expect(sidePanel(page)).toHaveAttribute("aria-modal", "true");
      } else {
        await expect(sidePanel(page)).not.toHaveAttribute("role", /.+/);
        const r = await splitRatio(page);
        if (c.mode === "half") {
          expect(r).toBeGreaterThan(0.47);
          expect(r).toBeLessThan(0.53);
        } else {
          expect(r).toBeGreaterThan(0.57);
          expect(r).toBeLessThan(0.63);
        }
        const cv = await box(sidePanel(page).locator("canvas"));
        const pn = await box(sidePanel(page));
        expect(cv.width).toBeLessThanOrEqual(pn.width); // 캔버스가 패널을 넘지 않음
      }
      expect(await docScrollsHorizontally(page)).toBe(false);
    });
  }

  test("Monaco automaticLayout: 분할 열림 상태에서 창 폭을 1280→1000으로 줄이면 에디터 폭이 패널을 따라간다", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const room = await createRoom("live");
    await openRoom(page, room);
    await openCodePanel(page);
    await page.setViewportSize({ width: 1000, height: 900 });
    const pn = await box(sidePanel(page));
    await expect
      .poll(async () => (await box(sidePanel(page).locator(".monaco-editor").first())).width, { timeout: 8000 })
      .toBeLessThanOrEqual(pn.width);
    const ed = await box(sidePanel(page).locator(".monaco-editor").first());
    expect(ed.width).toBeGreaterThan(pn.width - 40 - 6); // 패널 패딩(16*2) 제외 폭에 근접
  });
});

test.describe("세션 상태별 동작", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("live: 탭 활성·WS 연결 시도·입력 활성", async ({ page }) => {
    const ws = await mockInterviewWs(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await expect(tab(page, TAB_CODE)).toBeEnabled();
    await expect.poll(() => ws.count).toBeGreaterThan(0);
    await expect(page.getByPlaceholder("답변을 입력하세요...")).toBeEnabled();
  });

  test("scheduled: 탭 2개 disabled + 안내 문구, WS 미연결, 입력 비활성, 코드/화이트보드 요청 0건", async ({ page }) => {
    const ws = await mockInterviewWs(page);
    const reqs = watchRequests(page);
    const room = await createRoom("scheduled");
    await openRoom(page, room);
    await expect(tab(page, TAB_CODE)).toBeDisabled();
    await expect(tab(page, TAB_WB)).toBeDisabled();
    await expect(page.getByText("면접이 진행 중(live)일 때만 사용할 수 있습니다.")).toBeVisible();
    await expect(page.getByText(/현재 진행 중\(live\)이 아니라 대화 이력만 열람할 수 있습니다 \(상태: scheduled\)/)).toBeVisible();
    await expect(page.getByPlaceholder("이 세션은 현재 답변을 제출할 수 없습니다.")).toBeDisabled();
    await page.waitForTimeout(800);
    expect(ws.count).toBe(0);
    expect(reqs.filter((r) => /code-submissions|whiteboard/.test(r.url))).toEqual([]);
  });

  test("completed: 탭 2개 disabled + 안내 문구, 강제 클릭해도 패널 안 열림, 관련 요청 0건, 대화 이력 열람 가능", async ({ page }) => {
    const ws = await mockInterviewWs(page);
    const reqs = watchRequests(page);
    const room = await createRoom("completed");
    await openRoom(page, room);
    await expect(tab(page, TAB_CODE)).toBeDisabled();
    await expect(tab(page, TAB_WB)).toBeDisabled();
    await expect(page.getByText("면접이 진행 중(live)일 때만 사용할 수 있습니다.")).toBeVisible();
    await tab(page, TAB_CODE).click({ force: true, timeout: 2000 }).catch(() => undefined);
    await expect(sidePanel(page)).toBeHidden();
    await expect(page.getByText(/상태: completed/)).toBeVisible();
    await expect(page.getByText("아직 대화 이력이 없습니다.")).toBeVisible();
    expect(ws.count).toBe(0);
    expect(reqs.filter((r) => /code-submissions|whiteboard/.test(r.url))).toEqual([]);
  });

  test("paused(GET 응답 status만 모킹): 탭 disabled, 입력·음성 비활성, WS는 연결", async ({ page }) => {
    const ws = await mockInterviewWs(page);
    await forceInterviewStatus(page, "paused");
    const room = await createRoom("live");
    await openRoom(page, room);
    await expect(tab(page, TAB_CODE)).toBeDisabled();
    await expect(page.getByPlaceholder("이 세션은 현재 답변을 제출할 수 없습니다.")).toBeDisabled();
    await expect(page.getByRole("button", { name: "음성으로 답변" })).toBeDisabled();
    await expect.poll(() => ws.count).toBeGreaterThan(0);
  });

  test("expired(GET 응답 status만 모킹): 탭 disabled, WS 미연결, 상태 안내", async ({ page }) => {
    const ws = await mockInterviewWs(page);
    await forceInterviewStatus(page, "expired");
    const room = await createRoom("live");
    await openRoom(page, room);
    await expect(tab(page, TAB_WB)).toBeDisabled();
    await expect(page.getByText(/상태: expired/)).toBeVisible();
    await page.waitForTimeout(800);
    expect(ws.count).toBe(0);
  });
});

test.describe("로딩·오류·권한 경계", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("A1 SSR: /interviews/{id} HTTP 200, 스켈레톤 문구 포함", async ({ request }) => {
    const res = await request.get("/interviews/00000000-0000-4000-8000-000000000000");
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toContain("면접장을 불러오는 중입니다...");
    expect(html).not.toContain("undefined");
  });

  test("세션 GET 네트워크 실패 → 오류 배너 + 홈 링크, 패널/탭 미렌더", async ({ page }) => {
    const room = await createRoom("live");
    await page.route(/\/api\/v1\/interviews\/[^/]+$/, (route) => route.abort());
    await openRoom(page, room, { waitReady: false });
    await expect(page.getByText("네트워크 오류로 면접장을 불러오지 못했습니다.")).toBeVisible();
    await expect(page.getByRole("link", { name: "홈으로 돌아가기" })).toBeVisible();
    await expect(page.locator(".interview-room__tabs")).toHaveCount(0);
  });

  test("세션 GET 500(Problem Details) → detail 문구 배너", async ({ page }) => {
    const room = await createRoom("live");
    await page.route(/\/api\/v1\/interviews\/[^/]+$/, (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "X", detail: "서버 내부 오류 시뮬레이션" }) }),
    );
    await openRoom(page, room, { waitReady: false });
    await expect(page.getByText("서버 내부 오류 시뮬레이션")).toBeVisible();
  });

  test("타인의 세션 URL(IDOR): 403 배너, 패널/코드·화이트보드 요청 0건", async ({ page }) => {
    const owner = await createRoom("live");
    const intruder = await createAccount("candidate");
    const reqs = watchRequests(page);
    await openRoom(page, { account: intruder, interviewId: owner.interviewId }, { waitReady: false });
    await expect(page.getByText("본인의 면접 세션만 조작할 수 있습니다.")).toBeVisible();
    await expect(page.locator(".interview-room__tabs")).toHaveCount(0);
    await expect(sidePanel(page)).toHaveCount(0);
    expect(reqs.filter((r) => /code-submissions|whiteboard/.test(r.url))).toEqual([]);
  });

  test("무토큰 → /login 이동, 위조 토큰(401) → /login 이동", async ({ page, context }) => {
    await page.goto("/interviews/00000000-0000-4000-8000-000000000000");
    await page.waitForURL(/\/login/);
    const p2 = await context.newPage();
    await p2.addInitScript(() => window.sessionStorage.setItem("access_token", "not.a.jwt"));
    await p2.goto("/interviews/00000000-0000-4000-8000-000000000000");
    await p2.waitForURL(/\/login/);
  });

  test("존재하지 않는 세션(404)·UUID가 아닌 id(422)는 배너로 처리되고 크래시하지 않는다", async ({ page }) => {
    const problems = watchConsole(page, [/Failed to load resource/]);
    const room = await createRoom("live");
    await openRoom(page, { account: room.account, interviewId: "00000000-0000-4000-8000-000000000000" }, { waitReady: false });
    await expect(page.locator(".banner-error")).toBeVisible();
    await openRoom(page, { account: room.account, interviewId: "not-a-uuid" }, { waitReady: false });
    await expect(page.locator(".banner-error")).toBeVisible();
    expect(problems.filter((p) => p.startsWith("[pageerror]"))).toEqual([]);
  });

  test("[관찰 Q1] [C-05] 장치점검 화면 없음: /interviews/{id}/ready 는 404", async ({ request }) => {
    const res = await request.get("/interviews/00000000-0000-4000-8000-000000000000/ready");
    test.info().annotations.push({ type: "observation", description: `GET /interviews/{id}/ready → ${res.status()}` });
    expect(res.status()).toBe(404);
  });
});
