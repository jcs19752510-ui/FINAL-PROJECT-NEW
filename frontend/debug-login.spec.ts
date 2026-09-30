import { test, expect } from "@playwright/test";

test("debug login button", async ({ page }) => {
  page.on("console", (m) => console.log(`[console.${m.type()}]`, m.text()));
  page.on("pageerror", (e) => console.log("[pageerror]", e.message));
  page.on("requestfailed", (r) => console.log("[requestfailed]", r.url(), r.failure()?.errorText));

  await page.goto("http://127.0.0.1:3001/login");
  console.log("=== after goto ===");

  await page.getByLabel("이메일").fill("admin.test@local.dev");
  console.log("=== after email fill ===");
  const emailVal = await page.locator("#email").inputValue();
  console.log("email input value:", emailVal);

  await page.getByLabel("비밀번호").fill("Admin1234");
  console.log("=== after password fill ===");
  const pwVal = await page.locator("#password").inputValue();
  console.log("password input value:", pwVal);

  await page.waitForTimeout(500);
  const btn = page.getByRole("button", { name: "로그인", exact: true });
  const isDisabled = await btn.isDisabled();
  console.log("button disabled?", isDisabled);

  const html = await page.locator("form").innerHTML();
  console.log("=== form HTML ===");
  console.log(html);
});
