import { defineConfig, devices } from "@playwright/test";

// webServer는 의도적으로 설정하지 않는다: 앱 서버(next dev/start)는 테스트 실행자가 자기 PID 규칙으로
// 직접 띄우고 종료한다 (DEC-028, docs/harness/test-infra.md).
export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results",
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
