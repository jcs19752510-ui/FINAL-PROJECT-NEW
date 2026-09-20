// unit-20 06단계 — 코드 에디터 패널 배선: 편집/제출/유지/복원/오류/경계/XSS. TC-B2, B9, B12.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  call,
  createRoom,
  getEditorValue,
  openCodePanel,
  openRoom,
  setEditorValue,
  sidePanel,
  tab,
  watchConsole,
  watchRequests,
} from "./support";

test.use({ viewport: { width: 1280, height: 900 } });

const submitBtn = (page: import("@playwright/test").Page) => sidePanel(page).getByRole("button", { name: "제출", exact: true });
const status = (page: import("@playwright/test").Page, text: string) => sidePanel(page).getByText(text, { exact: true });

test("편집 → '미저장' → 제출 POST 201(language/content 일치) → '저장됨', 서버 GET에서 확인", async ({ page }) => {
  const problems = watchConsole(page);
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await expect(status(page, "저장됨")).toBeVisible();
  expect(await getEditorValue(page)).toBe("# 여기에 코드를 작성하세요\n"); // 빈 상태 = 기본 템플릿
  await setEditorValue(page, "print('hello')\n");
  await expect(status(page, "미저장")).toBeVisible();
  const [resp] = await Promise.all([
    page.waitForResponse((r) => /code-submissions$/.test(r.url()) && r.request().method() === "POST"),
    submitBtn(page).click(),
  ]);
  expect(resp.status()).toBe(201);
  expect(JSON.parse(resp.request().postData() ?? "{}")).toEqual({ language: "python", content: "print('hello')\n" });
  await expect(status(page, "저장됨")).toBeVisible();
  const server = await call("GET", `/interviews/${room.interviewId}/code-submissions`, room.account.token);
  expect(server.json[0].content).toBe("print('hello')\n");
  expect(problems).toEqual([]);
});

test("실제 키보드 입력도 onChange로 반영(미저장) — Monaco 포커스 후 타이핑", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await sidePanel(page).locator(".monaco-editor .view-lines").first().click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type("x = 1");
  await expect(status(page, "미저장")).toBeVisible();
  expect(await getEditorValue(page)).toContain("x = 1");
});

test("닫았다 다시 열어도 미제출 편집·'미저장' 상태 유지, 재오픈 시 GET 재조회로 덮어쓰지 않음", async ({ page }) => {
  const reqs = watchRequests(page);
  const room = await createRoom("live");
  await call("POST", `/interviews/${room.interviewId}/code-submissions`, room.account.token, { language: "python", content: "old = 1\n" });
  await openRoom(page, room);
  await openCodePanel(page);
  await expect.poll(() => getEditorValue(page)).toBe("old = 1\n"); // 이전 제출 복원
  await setEditorValue(page, "draft = 2\n");
  await expect(status(page, "미저장")).toBeVisible();
  const getsBefore = reqs.filter((r) => /code-submissions/.test(r.url) && r.method === "GET").length;
  await sidePanel(page).getByRole("button", { name: "채팅으로 돌아가기" }).click();
  await expect(sidePanel(page)).toBeHidden();
  await tab(page, TAB_CODE).click();
  await expect(sidePanel(page)).toBeVisible();
  expect(await getEditorValue(page)).toBe("draft = 2\n");
  await expect(status(page, "미저장")).toBeVisible();
  expect(reqs.filter((r) => /code-submissions/.test(r.url) && r.method === "GET").length).toBe(getsBefore);
  // 화이트보드 탭을 다녀와도 유지
  await tab(page, "화이트보드").click();
  await tab(page, TAB_CODE).click();
  expect(await getEditorValue(page)).toBe("draft = 2\n");
});

test("새로고침 후 다시 열면 마지막 제출(python) 복원, 미제출 편집은 사라진다", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, "saved = 1\n");
  await submitBtn(page).click();
  await expect(status(page, "저장됨")).toBeVisible();
  await setEditorValue(page, "unsaved = 2\n");
  await page.reload();
  await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
  await openCodePanel(page);
  await expect.poll(() => getEditorValue(page)).toBe("saved = 1\n");
  await expect(status(page, "저장됨")).toBeVisible();
});

test("언어 전환: 언어별 템플릿·언어별 최신본 복원, 드롭다운 option 11개가 서버 화이트리스트와 일치", async ({ page }) => {
  const room = await createRoom("live");
  await call("POST", `/interviews/${room.interviewId}/code-submissions`, room.account.token, { language: "go", content: "package main\n" });
  await openRoom(page, room);
  await openCodePanel(page);
  const select = sidePanel(page).getByLabel("프로그래밍 언어 선택");
  const values = await select.locator("option").evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value));
  expect(values.sort()).toEqual(["c", "cpp", "csharp", "go", "java", "javascript", "plaintext", "python", "rust", "sql", "typescript"]);
  await select.selectOption("go");
  await expect.poll(() => getEditorValue(page)).toBe("package main\n");
  await select.selectOption("sql");
  await expect.poll(() => getEditorValue(page)).toBe("-- 여기에 코드를 작성하세요\n");
  // 서버 화이트리스트로 실제 저장 가능한지(드롭다운 값 전부 201)
  for (const v of values) {
    const r = await call("POST", `/interviews/${room.interviewId}/code-submissions`, room.account.token, { language: v, content: "x" });
    expect(r.status, v).toBe(201);
  }
});

test("[관찰 Q4] 마지막 제출이 go여도 재접속 직후는 기본 언어(python) 빈 템플릿 — 현재 동작 기록", async ({ page }) => {
  const room = await createRoom("live");
  await call("POST", `/interviews/${room.interviewId}/code-submissions`, room.account.token, { language: "go", content: "package main\n" });
  await openRoom(page, room);
  await openCodePanel(page);
  const select = sidePanel(page).getByLabel("프로그래밍 언어 선택");
  await expect(select).toHaveValue("python");
  expect(await getEditorValue(page)).toBe("# 여기에 코드를 작성하세요\n");
  await select.selectOption("go");
  await expect.poll(() => getEditorValue(page)).toBe("package main\n"); // 드롭다운을 바꿔야 복원
});

test("복원 GET 실패 → 안내 배너 + 빈 템플릿으로 계속 편집·제출 가능", async ({ page }) => {
  const problems = watchConsole(page, [/Failed to load resource/]);
  const room = await createRoom("live");
  await page.route(/code-submissions\?language=/, (route) => route.abort());
  await openRoom(page, room);
  await openCodePanel(page);
  await expect(sidePanel(page).getByText("이전 세션의 코드를 불러오지 못했습니다.")).toBeVisible();
  expect(await getEditorValue(page)).toBe("# 여기에 코드를 작성하세요\n");
  await expect(submitBtn(page)).toBeEnabled();
  await setEditorValue(page, "after_fail = 1\n");
  await submitBtn(page).click();
  await expect(status(page, "저장됨")).toBeVisible();
  const server = await call("GET", `/interviews/${room.interviewId}/code-submissions`, room.account.token);
  expect(server.json[0].content).toBe("after_fail = 1\n");
  expect(problems.filter((p) => p.startsWith("[pageerror]"))).toEqual([]);
});

test("제출 실패(POST 500 Problem Details) → 인라인 오류·'저장 실패'·본문 유지, 재시도 성공 시 오류 해제", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, "keep_me = 1\n");
  await page.route(/code-submissions$/, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "저장소 오류 시뮬레이션" }) })
      : route.fallback(),
  );
  await submitBtn(page).click();
  await expect(sidePanel(page).getByText("저장소 오류 시뮬레이션")).toBeVisible();
  await expect(status(page, "저장 실패")).toBeVisible();
  expect(await getEditorValue(page)).toBe("keep_me = 1\n");
  await page.unroute(/code-submissions$/);
  await submitBtn(page).click();
  await expect(status(page, "저장됨")).toBeVisible();
  await expect(sidePanel(page).getByText("저장소 오류 시뮬레이션")).toHaveCount(0);
});

test("제출 실패(비-JSON 502 / 네트워크 abort) → 안내 문구 확인, 본문 유지", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, "keep_me = 2\n");
  await page.route(/code-submissions$/, (route) => (route.request().method() === "POST" ? route.fulfill({ status: 502, body: "Bad Gateway" }) : route.fallback()));
  await submitBtn(page).click();
  await expect(sidePanel(page).getByText("제출 실패 (status 502)")).toBeVisible();
  await page.unroute(/code-submissions$/);
  await page.route(/code-submissions$/, (route) => (route.request().method() === "POST" ? route.abort() : route.fallback()));
  await submitBtn(page).click();
  await expect(status(page, "저장 실패")).toBeVisible();
  const banner = await sidePanel(page).locator(".banner-error").innerText();
  test.info().annotations.push({ type: "observation", description: `네트워크 단절 시 사용자에게 보이는 문구: "${banner}"` });
  expect(await getEditorValue(page)).toBe("keep_me = 2\n");
});

test("경계: 정확히 20000자 제출 성공, 20001자 → 서버 422가 사용자에게 어떻게 보이는지(원문 에코 여부 포함)", async ({ page }) => {
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, "a".repeat(20000));
  await submitBtn(page).click();
  await expect(status(page, "저장됨")).toBeVisible();
  await setEditorValue(page, "b".repeat(20001));
  await submitBtn(page).click();
  await expect(status(page, "저장 실패")).toBeVisible();
  const banner = await sidePanel(page).locator(".banner-error").innerText();
  test.info().annotations.push({ type: "observation", description: `422 배너 길이=${banner.length}자, 앞 120자="${banner.slice(0, 120)}"` });
  // 사용자에게 보이는 오류에 제출한 코드 원문(20001자)이 그대로 다시 표시되어서는 안 된다.
  expect(banner.length).toBeLessThan(1000);
});

test("빈 내용 제출 허용(서버 min_length=0) + 저장 중 중복 클릭 방지(POST 1회)", async ({ page }) => {
  const reqs = watchRequests(page);
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, "");
  await status(page, "미저장").waitFor().catch(() => undefined);
  await page.route(/code-submissions$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await new Promise((r) => setTimeout(r, 700));
    await route.fallback();
  });
  await submitBtn(page).dblclick();
  await expect(status(page, "저장됨")).toBeVisible();
  const posts = reqs.filter((r) => /code-submissions$/.test(r.url) && r.method === "POST");
  expect(posts.length).toBe(1);
  const server = await call("GET", `/interviews/${room.interviewId}/code-submissions`, room.account.token);
  expect(server.json[0].content).toBe("");
});

test("XSS: HTML/스크립트 형태 코드를 제출·복원해도 실행/DOM 주입이 없다(에디터 값 그대로 보존)", async ({ page }) => {
  const problems = watchConsole(page);
  const payload = `<img src=x onerror="window.__xss=1"><script>window.__xss=2</script><svg onload="window.__xss=3"></svg>\n`;
  const room = await createRoom("live");
  await openRoom(page, room);
  await openCodePanel(page);
  await setEditorValue(page, payload);
  await submitBtn(page).click();
  await expect(status(page, "저장됨")).toBeVisible();
  await page.reload();
  await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
  await openCodePanel(page);
  await expect.poll(() => getEditorValue(page)).toBe(payload);
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(await page.locator("img[src='x']").count()).toBe(0);
  expect(await page.locator("svg[onload]").count()).toBe(0);
  const scripts = await page.evaluate(() => Array.from(document.scripts).filter((s) => s.textContent?.includes("__xss")).length);
  expect(scripts).toBe(0);
  expect(problems).toEqual([]);
});

test("다른 세션의 코드는 섞이지 않는다: 같은 계정의 두 번째 세션은 빈 템플릿", async ({ page }) => {
  const a = await createRoom("live");
  await call("POST", `/interviews/${a.interviewId}/code-submissions`, a.account.token, { language: "python", content: "session_a = 1\n" });
  const b = await createRoom("live", a.account);
  await openRoom(page, b);
  await openCodePanel(page);
  expect(await getEditorValue(page)).toBe("# 여기에 코드를 작성하세요\n");
});
