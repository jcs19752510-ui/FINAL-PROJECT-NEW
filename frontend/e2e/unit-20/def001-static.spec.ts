// unit-20 06단계 — 정적 확인(A2) + DEF-001(SSR/hydration) 검증. cwd는 frontend/ 여야 한다(npm run test:e2e / npx playwright test).
// DEF-001의 autoStart 경로는 현재 어느 실화면도 쓰지 않는다([C-05] 미구현). 그래서 실행자가 임시 라우트(autoStart WebcamPreview를
// 렌더하는 클라이언트 페이지)를 만들어 E2E_AUTOSTART_PATH로 알려줄 때만 실행한다(없으면 skip).
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { createRoom, installMediaSpy, mediaState, openCodePanel, openRoom, openWhiteboardPanel, watchConsole } from "./support";

const FRONT = process.cwd();

// launchOptions는 파일(워커) 단위로만 지정할 수 있다(describe 내부에서 test.use({launchOptions})는
// "forces a new worker" 오류로 거부됨) — 06단계에서 발견해 최상위로 옮김. "A2 정적 확인"은 page를
// 쓰지 않으므로 이 설정의 영향을 받지 않는다.
test.use({
  viewport: { width: 1280, height: 900 },
  launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
});

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (["node_modules", ".next", "e2e", "test-results", "playwright-report"].includes(name)) continue;
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|jsx?|css)$/.test(name)) out.push(p);
  }
  return out;
}

test.describe("A2 정적 확인", () => {
  test("frontend 소스에 dangerouslySetInnerHTML / innerHTML 사용 0건", () => {
    const hits = ["app", "components", "lib"].flatMap((d) => walk(path.join(FRONT, d))).filter((f) => /dangerouslySetInnerHTML|\.innerHTML|insertAdjacentHTML|document\.write\(/.test(readFileSync(f, "utf8")));
    expect(hits).toEqual([]);
  });

  test("WebcamPreview.tsx에 서버 전송·녹화·캡처 API 사용 없음(fetch/XHR/WebSocket/beacon/MediaRecorder/captureStream/RTCPeerConnection)", () => {
    const src = readFileSync(path.join(FRONT, "components", "WebcamPreview.tsx"), "utf8");
    const code = src.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(code).not.toMatch(/\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|MediaRecorder|captureStream|RTCPeerConnection|createObjectURL/);
    expect(code).toMatch(/getUserMedia/);
  });

  test("이 유닛이 추가한 런타임 의존성 없음(dependencies는 기존 4개)", () => {
    const pkg = JSON.parse(readFileSync(path.join(FRONT, "package.json"), "utf8"));
    expect(Object.keys(pkg.dependencies).sort()).toEqual(["@monaco-editor/react", "next", "react", "react-dom"]);
  });

  test("DEF-001 원인 제거: WebcamPreview의 초기 상태가 환경(브라우저 지원 여부)에 의존하지 않는다", () => {
    const src = readFileSync(path.join(FRONT, "components", "WebcamPreview.tsx"), "utf8");
    const init = src.match(/useState<WebcamPreviewStatus>\(([^;]*)\);/);
    expect(init).not.toBeNull();
    expect(init![1]).not.toMatch(/isGetUserMediaSupported|navigator|window/);
    expect(init![1]).toMatch(/autoStart/);
  });
});

test.describe("DEF-001 브라우저 실측", () => {
  test("면접장 전체 흐름(로드→코드→화이트보드→웹캠 켬/끔→새로고침)에서 콘솔 error/warning/pageerror 0건", async ({ page }) => {
    const problems = watchConsole(page);
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    await openCodePanel(page);
    await openWhiteboardPanel(page);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    await page.getByRole("button", { name: "웹캠 미리보기 끄기" }).click();
    await page.reload();
    await page.getByRole("heading", { name: "면접장", level: 1 }).waitFor();
    expect(problems).toEqual([]);
  });

  test("autoStart 경로 SSR HTML은 '카메라 권한 요청 중...'이고 '이 브라우저 또는 장치에서…'가 아니다 (E2E_AUTOSTART_PATH 필요)", async ({ request }) => {
    test.skip(!process.env.E2E_AUTOSTART_PATH, "임시 autoStart 라우트가 없으면 실행하지 않는다(E2E_AUTOSTART_PATH).");
    const html = await (await request.get(process.env.E2E_AUTOSTART_PATH!)).text();
    expect(html).toContain("카메라 권한 요청 중...");
    expect(html).not.toContain("이 브라우저 또는 장치에서");
  });

  for (const mode of ["real", "denied", "notfound", "none"] as const) {
    test(`autoStart hydration(${mode}): 콘솔 error/warning 0건, 최종 상태 전이 (E2E_AUTOSTART_PATH 필요)`, async ({ page }) => {
      test.skip(!process.env.E2E_AUTOSTART_PATH, "임시 autoStart 라우트가 없으면 실행하지 않는다(E2E_AUTOSTART_PATH).");
      const problems = watchConsole(page);
      await installMediaSpy(page, mode);
      await page.goto(process.env.E2E_AUTOSTART_PATH!);
      if (mode === "real") {
        await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
        expect((await mediaState(page)).liveTracks).toBe(1);
      } else if (mode === "denied") {
        await expect(page.getByText("카메라 권한이 거부되었습니다.")).toBeVisible();
      } else {
        await expect(page.getByText("이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다.")).toBeVisible();
      }
      await page.waitForTimeout(500);
      expect(problems).toEqual([]);
    });
  }
});
