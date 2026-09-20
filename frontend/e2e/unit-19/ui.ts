/** unit-19 UI 스펙 공용 헬퍼 (브라우저 측). */
import type { Locator, Page, Route } from "@playwright/test";
import { expect } from "./helpers";
import type { Account } from "./helpers";

export const LIST_URL = /\/api\/v1\/interviews(\?.*)?$/;
const NOISE = /Failed to load resource/; // 의도적으로 주입한 4xx/5xx 응답이 남기는 브라우저 네트워크 로그

export interface Watch {
  /** console.error + pageerror (네트워크 로그 노이즈 제외) */
  errors: string[];
  /** 네트워크 로그 노이즈까지 포함한 모든 console.error */
  rawErrors: string[];
  /** GET /interviews(목록) 호출 URL */
  listCalls: string[];
  /** POST /interviews(세션 생성) 호출 수 */
  createCalls: string[];
}

export function watch(page: Page): Watch {
  const w: Watch = { errors: [], rawErrors: [], listCalls: [], createCalls: [] };
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    w.rawErrors.push(m.text());
    if (!NOISE.test(m.text())) w.errors.push(m.text());
  });
  page.on("pageerror", (e) => {
    w.errors.push(`pageerror: ${e.message}`);
    w.rawErrors.push(`pageerror: ${e.message}`);
  });
  page.on("request", (r) => {
    if (!LIST_URL.test(r.url())) return;
    if (r.method() === "GET") w.listCalls.push(r.url());
    if (r.method() === "POST") w.createCalls.push(r.url());
  });
  return w;
}

/** /login UI 로 로그인하고 홈 진입까지 기다린다(인수조건: 로그인은 UI 사용). */
export async function uiLogin(page: Page, acct: Account): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(acct.email);
  await page.getByLabel("비밀번호").fill(acct.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((u) => u.pathname === "/");
}

export function cards(page: Page): Locator {
  return page.locator('section[aria-labelledby="home-recent-heading"] ul:not([aria-busy]) > li');
}

export function cta(page: Page): Locator {
  return page.getByRole("link", { name: "새 면접 시작", exact: true });
}

export function banner(page: Page): Locator {
  return page.getByRole("status", { name: "중단된 면접 안내" });
}

/** 목록 API 응답을 가로채 대체 응답을 준다. 교차 출처 fetch 라 CORS 헤더를 직접 붙여야 프런트가 상태코드를 본다. */
export async function fulfillWithCors(route: Route, status: number, body: unknown): Promise<void> {
  const origin = route.request().headers()["origin"] ?? "*";
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": origin, "access-control-allow-credentials": "true" },
    body: JSON.stringify(body),
  });
}

export async function seedToken(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => window.sessionStorage.setItem("access_token", t), token);
}

export async function storedToken(page: Page): Promise<string | null> {
  return page.evaluate(() => window.sessionStorage.getItem("access_token"));
}

export async function homeReady(page: Page): Promise<void> {
  await expect(page.locator("main h1")).toBeVisible();
}
