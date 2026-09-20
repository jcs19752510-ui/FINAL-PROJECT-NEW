import { statSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

// Next 앱/백엔드 없이 "브라우저 자동화 도구 자체가 동작하는가"만 증명하는 스모크.
// 앱 화면 검증은 e2e/<feature>/ 아래 별도 스펙이 맡는다.

const HTML = `<!doctype html>
<html lang="ko">
  <head><meta charset="utf-8"><title>하네스 스모크</title></head>
  <body>
    <h1 id="title">AI 모의면접 하네스 스모크</h1>
    <button id="go" type="button">면접 시작</button>
    <p id="out" role="status"></p>
    <script>
      document.getElementById("go").addEventListener("click", () => {
        document.getElementById("out").textContent = "시작됨";
      });
    </script>
  </body>
</html>`;

test("setContent: 한국어 텍스트 렌더링·DOM 조회·스크립트 실행·스크린샷", async ({ page }, testInfo) => {
  await page.setContent(HTML);

  await expect(page.locator("#title")).toHaveText("AI 모의면접 하네스 스모크");
  expect(await page.title()).toBe("하네스 스모크");

  await page.getByRole("button", { name: "면접 시작" }).click();
  await expect(page.getByRole("status")).toHaveText("시작됨");

  const box = await page.locator("#title").boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(0);
  expect(box?.height ?? 0).toBeGreaterThan(0);

  const shot = testInfo.outputPath("smoke-setcontent.png");
  await page.screenshot({ path: shot });
  expect(statSync(shot).size).toBeGreaterThan(0);
});

test("file://: 로컬 정적 HTML 로드", async ({ page }, testInfo) => {
  const file = testInfo.outputPath("smoke.html");
  writeFileSync(file, HTML, "utf-8");

  await page.goto(pathToFileURL(file).href);

  await expect(page.locator("#title")).toContainText("모의면접");
  const ua = await page.evaluate(() => navigator.userAgent);
  expect(ua).toMatch(/Chrome\//);
});
