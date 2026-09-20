// unit-20 면접장 화면 e2e 공용 헬퍼 (06단계, docs/harness/units/unit-20-test.md).
//
// 실행 전제(docs/harness/test-infra.md §4·§5): 실행자가 백엔드와 Next dev 서버를 자기 포트로 직접 띄우고
//   E2E_BASE_URL     (프런트 origin, 예 http://127.0.0.1:3620)
//   E2E_API_BASE_URL (백엔드 `/api/v1` 주소, 예 http://127.0.0.1:8620/api/v1 — 프런트도 같은 값을
//                     NEXT_PUBLIC_API_BASE_URL로 기동해야 한다)
// 를 지정한다. 백엔드 CORS_ORIGINS에 프런트 origin이 포함되어야 한다.
//
// 테스트 데이터 규약(§3): 모든 계정은 `harness_test_<uuid4>@harness-test.example` 마커 이메일이며,
// 만든 계정은 JSONL 로그(E2E_ACCOUNT_LOG, 기본 `<repo>/.harness-tmp/e2e-accounts.jsonl`)에 남긴다.
// 실행 후 정리: 로그의 각 이메일에 대해 `python -m tests.support.cleanup --email <이메일>` (backend/에서).
import { randomBytes, randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import type { Page, WebSocketRoute } from "@playwright/test";

export const API_BASE = (process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
const ACCOUNT_LOG =
  process.env.E2E_ACCOUNT_LOG ?? path.resolve(process.cwd(), "..", ".harness-tmp", "e2e-accounts.jsonl");

export type Role = "candidate" | "recruiter";
export interface Account {
  id: string;
  email: string;
  password: string;
  token: string;
  role: Role;
}

export interface CallResult {
  status: number;
   
  json: any;
}

export async function call(method: string, url: string, token?: string, body?: unknown): Promise<CallResult> {
  const res = await fetch(`${API_BASE}${url}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json = await res.json().catch(() => null);
  return { status: res.status, json };
}

function logAccount(entry: { id: string; email: string; role: Role }) {
  mkdirSync(path.dirname(ACCOUNT_LOG), { recursive: true });
  appendFileSync(ACCOUNT_LOG, JSON.stringify({ ...entry, at: new Date().toISOString() }) + "\n");
}

export async function createAccount(role: Role = "candidate"): Promise<Account> {
  const email = `harness_test_${randomUUID()}@harness-test.example`;
  const password = randomBytes(12).toString("base64url");
  const reg = await call("POST", "/auth/register", undefined, { email, password, name: "u20 e2e", role });
  if (reg.status !== 201) throw new Error(`register failed: ${reg.status} ${JSON.stringify(reg.json)}`);
  logAccount({ id: reg.json.id, email, role });
  const login = await call("POST", "/auth/login", undefined, { email, password });
  if (login.status !== 200) throw new Error(`login failed: ${login.status}`);
  return { id: reg.json.id, email, password, token: login.json.access_token, role };
}

export type RoomState = "scheduled" | "live" | "completed";

export interface Room {
  account: Account;
  interviewId: string;
}

/** 새 지원자 계정 + 면접 세션 1개를 API로 만들고 원하는 상태까지 진행한다(scheduled -> live -> completed). */
export async function createRoom(state: RoomState = "live", account?: Account): Promise<Room> {
  const acc = account ?? (await createAccount("candidate"));
  const created = await call("POST", "/interviews", acc.token, {});
  if (created.status !== 201) {
    throw new Error(`create interview failed: ${created.status} ${JSON.stringify(created.json)}`);
  }
  const interviewId: string = created.json.id;
  if (state !== "scheduled") {
    const consent = await call("POST", "/consents", acc.token, { consent_type: "ai_interview_notice" });
    if (consent.status !== 201) throw new Error(`consent failed: ${consent.status} ${JSON.stringify(consent.json)}`);
    const started = await call("POST", `/interviews/${interviewId}/start`, acc.token);
    if (started.status !== 202) throw new Error(`start failed: ${started.status} ${JSON.stringify(started.json)}`);
    if (state === "completed") {
      const ended = await call("POST", `/interviews/${interviewId}/end`, acc.token);
      if (ended.status !== 202) throw new Error(`end failed: ${ended.status} ${JSON.stringify(ended.json)}`);
    }
  }
  return { account: acc, interviewId };
}

/** 토큰을 sessionStorage에 심고(모든 내비게이션/새로고침에 재적용) 면접장으로 이동한다. */
export async function openRoom(page: Page, room: Room, opts: { waitReady?: boolean } = {}): Promise<void> {
  await page.addInitScript((t) => window.sessionStorage.setItem("access_token", t), room.account.token);
  await page.goto(`/interviews/${room.interviewId}`);
  if (opts.waitReady !== false) {
    await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
  }
}

/** console error/warning + 페이지 예외를 수집한다. `ignore`에 해당하는 메시지는 제외(의도적으로 5xx를 모킹한 테스트용). */
export function watchConsole(page: Page, ignore: RegExp[] = []): string[] {
  const problems: string[] = [];
  const keep = (text: string) => !ignore.some((re) => re.test(text));
  page.on("console", (m) => {
    if ((m.type() === "error" || m.type() === "warning") && keep(m.text())) {
      problems.push(`[${m.type()}] ${m.text()}`);
    }
  });
  page.on("pageerror", (e) => {
    if (keep(e.message)) problems.push(`[pageerror] ${e.message}`);
  });
  return problems;
}

export interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  type: string;
  postData: string | null;
}

export function watchRequests(page: Page): SeenRequest[] {
  const seen: SeenRequest[] = [];
  page.on("request", (r) =>
    seen.push({
      url: r.url(),
      method: r.method(),
      headers: r.headers(),
      type: r.resourceType(),
      postData: r.postData(),
    }),
  );
  return seen;
}

export type MediaMode = "real" | "denied" | "notfound" | "aborted" | "none";

/** getUserMedia 호출/트랙 수명을 관찰하고(real) 또는 특정 오류로 대체한다. 서버 전송 관련 API 사용 여부도 센다. */
export async function installMediaSpy(page: Page, mode: MediaMode = "real"): Promise<void> {
  await page.addInitScript((m: string) => {
     
    const w = window as any;
    w.__media = { calls: [] as string[], tracks: [] as MediaStreamTrack[] };
    w.__spy = { mediaRecorder: 0, captureStream: 0, rtc: 0 };
    const OrigMR = w.MediaRecorder;
    if (OrigMR) {
      w.MediaRecorder = function (...args: unknown[]) {
        w.__spy.mediaRecorder++;
        return new OrigMR(...args);
      };
      w.MediaRecorder.isTypeSupported = OrigMR.isTypeSupported?.bind(OrigMR);
    }
    const cap = HTMLCanvasElement.prototype.captureStream;
    if (cap) {
      HTMLCanvasElement.prototype.captureStream = function (this: HTMLCanvasElement, ...a: []) {
        w.__spy.captureStream++;
        return cap.apply(this, a);
      };
    }
    const OrigRTC = w.RTCPeerConnection;
    if (OrigRTC) {
      w.RTCPeerConnection = function (...args: unknown[]) {
        w.__spy.rtc++;
        return new OrigRTC(...args);
      };
    }
    if (m === "none") {
      Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
      return;
    }
    const md = navigator.mediaDevices;
    if (m === "real") {
      const orig = md.getUserMedia.bind(md);
      md.getUserMedia = async (c?: MediaStreamConstraints) => {
        w.__media.calls.push(JSON.stringify(c));
        const s = await orig(c);
        s.getTracks().forEach((t) => w.__media.tracks.push(t));
        return s;
      };
    } else {
      const name = m === "denied" ? "NotAllowedError" : m === "notfound" ? "NotFoundError" : "AbortError";
      md.getUserMedia = async (c?: MediaStreamConstraints) => {
        w.__media.calls.push(JSON.stringify(c));
        throw new DOMException("mocked", name);
      };
    }
  }, mode);
}

export async function mediaState(
  page: Page,
): Promise<{ calls: number; liveTracks: number; mediaRecorder: number; captureStream: number; rtc: number }> {
  return page.evaluate(() => {
     
    const w = window as any;
    return {
      calls: w.__media.calls.length,
      liveTracks: w.__media.tracks.filter((t: MediaStreamTrack) => t.readyState === "live").length,
      mediaRecorder: w.__spy.mediaRecorder,
      captureStream: w.__spy.captureStream,
      rtc: w.__spy.rtc,
    };
  });
}

/** `/ws/interviews/*` WebSocket을 완전히 모킹한다(서버 미접속). send()로 서버->클라이언트 이벤트를 밀어 넣는다. */
export async function mockInterviewWs(page: Page) {
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket(/\/ws\/interviews\//, (ws) => {
    sockets.push(ws);
  });
  return {
    get count() {
      return sockets.length;
    },
    send(event: unknown) {
      const data = JSON.stringify(event);
      sockets.forEach((s) => s.send(data));
    },
    sendRaw(text: string) {
      sockets.forEach((s) => s.send(text));
    },
  };
}

/** `POST /interviews/{id}/turns`를 202 `{job_id}`로 모킹하고 요청 본문을 기록한다. */
export async function mockTurns(page: Page, jobId = "job-e2e-1") {
  const bodies: string[] = [];
  await page.route(/\/interviews\/[^/]+\/turns$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    bodies.push(route.request().postData() ?? "");
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ job_id: jobId }) });
  });
  return { bodies, jobId };
}

/** 텍스트 답변을 보내 AI 대기 상태(activeJobId 설정)까지 진행한다. */
export async function sendTextTurn(page: Page, text: string): Promise<void> {
  await page.getByPlaceholder("답변을 입력하세요...").fill(text);
  await page.getByRole("button", { name: "전송", exact: true }).click();
  await page.getByText("AI가 답변을 준비하고 있어요...").waitFor();
}

/** GET /interviews/{id} 응답의 status만 바꿔 준다(paused/expired 등 API로 만들기 어려운 상태의 프런트 동작 검증용). */
export async function forceInterviewStatus(page: Page, status: string): Promise<void> {
  await page.route(/\/api\/v1\/interviews\/[^/]+$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const res = await route.fetch();
    const json = await res.json();
    await route.fulfill({ response: res, json: { ...json, status } });
  });
}

export async function docScrollsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
}

/** 대비 측정 결과(수동 axe 대체): 보이는 텍스트 요소의 실효 전경/배경색으로 WCAG 대비를 계산한다. */
export interface ContrastRow {
  text: string;
  ratio: number;
  required: number;
  fg: string;
  bg: string;
  fontPx: number;
  bold: boolean;
  tag: string;
}

export async function measureContrast(page: Page, rootSelector: string): Promise<ContrastRow[]> {
  return page.evaluate((sel) => {
    type C = { r: number; g: number; b: number; a: number };
    const parse = (s: string): C => {
      const m = s.match(/rgba?\(([^)]+)\)/);
      if (!m) return { r: 0, g: 0, b: 0, a: 0 };
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(parseFloat);
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    };
    const over = (top: C, bottom: C): C => ({
      r: top.r * top.a + bottom.r * (1 - top.a),
      g: top.g * top.a + bottom.g * (1 - top.a),
      b: top.b * top.a + bottom.b * (1 - top.a),
      a: 1,
    });
    const effBg = (el: Element): C => {
      const layers: C[] = [];
      let n: Element | null = el;
      while (n) {
        const c = parse(getComputedStyle(n).backgroundColor);
        if (c.a > 0) layers.push(c);
        if (c.a === 1) break;
        n = n.parentElement;
      }
      let base: C = { r: 255, g: 255, b: 255, a: 1 };
      for (const l of layers.reverse()) base = over(l, base);
      return base;
    };
    const opacityOf = (el: Element): number => {
      let o = 1;
      let n: Element | null = el;
      while (n) {
        o *= parseFloat(getComputedStyle(n).opacity);
        n = n.parentElement;
      }
      return o;
    };
    const lum = (c: C) => {
      const f = (v: number) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    };
    const root = document.querySelector(sel);
    const rows: {
      text: string;
      ratio: number;
      required: number;
      fg: string;
      bg: string;
      fontPx: number;
      bold: boolean;
      tag: string;
    }[] = [];
    if (!root) return rows;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const seen = new Set<Element>();
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const el = node.parentElement;
      if (!el || seen.has(el)) continue;
      const text = (node.textContent ?? "").trim();
      if (!text) continue;
      if (el.closest(".monaco-editor, canvas, script, style")) continue;
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      if (cs.visibility === "hidden" || cs.display === "none" || rect.width === 0 || rect.height === 0) continue;
      const ctl = el.closest("button, select, input, textarea") as HTMLButtonElement | null;
      if (ctl?.disabled) continue; // WCAG: 비활성 컨트롤은 대비 예외
      seen.add(el);
      const bg = effBg(el);
      const fgRaw = parse(cs.color);
      const op = opacityOf(el);
      const fg = over({ ...fgRaw, a: fgRaw.a * op }, bg);
      const l1 = lum(fg);
      const l2 = lum(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const fontPx = parseFloat(cs.fontSize);
      const bold = parseInt(cs.fontWeight, 10) >= 700;
      const large = fontPx >= 24 || (fontPx >= 18.66 && bold);
      const hex = (c: C) =>
        "#" +
        [c.r, c.g, c.b]
          .map((v) => Math.round(v).toString(16).padStart(2, "0"))
          .join("");
      rows.push({
        text: text.slice(0, 40),
        ratio: Math.round(ratio * 100) / 100,
        required: large ? 3 : 4.5,
        fg: hex(fg),
        bg: hex(bg),
        fontPx,
        bold,
        tag: el.tagName.toLowerCase(),
      });
    }
    return rows;
  }, rootSelector);
}

// ---- 화면 공통 보조 ----
export const TAB_CODE = "코드 에디터";
export const TAB_WB = "화이트보드";

export function sidePanel(page: Page) {
  return page.locator("#interview-side-panel");
}

export function tab(page: Page, name: string) {
  return page.locator(".interview-room__tabs").getByRole("button", { name, exact: true });
}

/** Monaco가 CDN에서 로드되어 모델이 생기고 복원 오버레이가 사라질 때까지 기다린다. */
export async function monacoReady(page: Page): Promise<void> {
  await page.locator(".monaco-editor").first().waitFor({ timeout: 45_000 });
  await page.waitForFunction(
     
    () => ((window as any).monaco?.editor.getModels().length ?? 0) > 0,
    null,
    { timeout: 45_000 },
  );
  await page.getByText("에디터를 불러오는 중입니다...").waitFor({ state: "hidden", timeout: 45_000 });
}

export async function setEditorValue(page: Page, value: string): Promise<void> {
  await page.evaluate(
     
    (v) => (window as any).monaco.editor.getModels()[0].setValue(v),
    value,
  );
}

export async function getEditorValue(page: Page): Promise<string> {
   
  return page.evaluate(() => (window as any).monaco.editor.getModels()[0].getValue() as string);
}

/** 코드 패널을 열고 Monaco 준비까지 기다린다. */
export async function openCodePanel(page: Page): Promise<void> {
  await tab(page, TAB_CODE).click();
  await sidePanel(page).getByRole("heading", { name: TAB_CODE }).waitFor();
  await monacoReady(page);
}

export async function openWhiteboardPanel(page: Page): Promise<void> {
  await tab(page, TAB_WB).click();
  await sidePanel(page).getByRole("heading", { name: TAB_WB }).waitFor();
  await page.locator("#interview-side-panel canvas").waitFor();
  await page.getByText("캔버스를 불러오는 중...").waitFor({ state: "hidden" });
}

export async function box(loc: import("@playwright/test").Locator) {
  const b = await loc.boundingBox();
  if (!b) throw new Error("no bounding box");
  return b;
}

/** 채팅 컬럼 : 보조 패널 컬럼 폭 비율(채팅 / (채팅+패널)). */
export async function splitRatio(page: Page): Promise<number> {
  const chat = await box(page.locator(".interview-room__chat"));
  const panel = await box(sidePanel(page));
  return chat.width / (chat.width + panel.width);
}

/** 캔버스 논리 좌표(640x400) 기준 점을 화면 좌표로 환산한다. */
export async function canvasPoint(page: Page, fx: number, fy: number) {
  const b = await box(page.locator("#interview-side-panel canvas"));
  return { x: b.x + b.width * fx, y: b.y + b.height * fy, box: b };
}

export async function drawStroke(page: Page, from: [number, number], to: [number, number]): Promise<void> {
  const a = await canvasPoint(page, from[0], from[1]);
  const b = await canvasPoint(page, to[0], to[1]);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 6 });
  await page.mouse.move(b.x, b.y, { steps: 6 });
  await page.mouse.up();
}

/** 캔버스의 (cx,cy)(논리 좌표) 주변 반경 r 안에 불투명 픽셀이 하나라도 있는가. */
export async function hasInkNear(page: Page, cx: number, cy: number, r = 6): Promise<boolean> {
  return page.evaluate(
    ({ cx, cy, r }) => {
      const c = document.querySelector("#interview-side-panel canvas") as HTMLCanvasElement;
      const d = c.getContext("2d")!.getImageData(Math.max(0, cx - r), Math.max(0, cy - r), 2 * r, 2 * r).data;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 0) return true;
      return false;
    },
    { cx, cy, r },
  );
}
