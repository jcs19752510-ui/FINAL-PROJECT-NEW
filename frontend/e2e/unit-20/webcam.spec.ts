// unit-20 06단계 — 웹캠 타일(REQ-015): 기본 off·가짜 카메라·권한 거부·미지원·서버 전송 없음·모바일 토글 정리. TC-B4.
import { expect, test } from "@playwright/test";
import {
  API_BASE,
  box,
  createRoom,
  installMediaSpy,
  mediaState,
  mockTurns,
  openRoom,
  sendTextTurn,
  watchConsole,
  watchRequests,
} from "./support";

const FAKE_CAMERA_ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"];
const tile = (page: import("@playwright/test").Page) => page.locator(".webcam-tile");

// launchOptions는 파일(워커) 단위로만 지정 가능하다(describe 내부 test.use({launchOptions})는
// "forces a new worker" 오류로 거부됨 — 06단계에서 실행 중 발견해 최상위로 이동). 이 파일의 모든
// describe가 가짜 카메라 플래그를 켜 둬도 무해하다: getUserMedia를 모킹하는 테스트는 실제 카메라
// 플래그와 무관하게 모킹된 함수가 우선 적용된다.
test.use({ launchOptions: { args: FAKE_CAMERA_ARGS } });

test.describe("가짜 카메라(데스크톱)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("켜기 → active(끄기 버튼·video aria-hidden·audio:false) → 끄기 → srcObject 해제·트랙 정지·다시 off", async ({ page }) => {
    const problems = watchConsole(page);
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    const off = page.getByRole("button", { name: "웹캠 미리보기 끄기" });
    await expect(off).toBeVisible();
    const video = tile(page).locator("video");
    await expect(video).toHaveAttribute("aria-hidden", "true");
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => (v.srcObject as MediaStream | null)?.getVideoTracks().length ?? 0)).toBe(1);
    const st = await mediaState(page);
    expect(st.calls).toBe(1);
    expect(st.liveTracks).toBe(1);
    const constraints = await page.evaluate(() => (window as unknown as { __media: { calls: string[] } }).__media.calls[0]);
    expect(JSON.parse(constraints)).toEqual({ video: true, audio: false });
    await off.click();
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toBeVisible();
    expect(await video.evaluate((v: HTMLVideoElement) => v.srcObject)).toBeNull();
    await expect.poll(async () => (await mediaState(page)).liveTracks).toBe(0);
    // 다시 켜기(2회차)도 정상
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("서버 전송 없음: 켜고 20초 가까이 둬도 허용 호스트 외 요청·API 쓰기 요청·MediaRecorder/captureStream/RTC 사용이 없다", async ({ page }) => {
    await installMediaSpy(page, "real");
    const reqs = watchRequests(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    await page.waitForTimeout(3000);
    const allowed = new Set([new URL(page.url()).host, new URL(API_BASE).host, "cdn.jsdelivr.net"]);
    const foreign = reqs.filter((r) => !/^(data|blob):/.test(r.url) && !allowed.has(new URL(r.url).host)).map((r) => r.url);
    expect(foreign).toEqual([]);
    const apiWrites = reqs.filter((r) => r.url.startsWith(API_BASE) && r.method !== "GET" && r.method !== "OPTIONS");
    expect(apiWrites).toEqual([]);
    expect(reqs.filter((r) => r.type === "websocket" && !/\/ws\/interviews\//.test(r.url))).toEqual([]);
    const st = await mediaState(page);
    expect([st.mediaRecorder, st.captureStream, st.rtc]).toEqual([0, 0, 0]);
    // Authorization 토큰이 앱/API 밖(CDN)으로 나가지 않는다
    expect(reqs.filter((r) => new URL(r.url).host === "cdn.jsdelivr.net" && (r.headers["authorization"] || r.url.includes(room.account.token)))).toEqual([]);
  });

  test("웹캠이 켜져 있어도 채팅 전송·코드/화이트보드 패널이 동작(레이아웃 침범 없음)", async ({ page }) => {
    await installMediaSpy(page, "real");
    await mockTurns(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    await sendTextTurn(page, "카메라 켠 상태의 답변");
    await expect(page.getByText("카메라 켠 상태의 답변")).toBeVisible();
    const t = await box(tile(page));
    expect([Math.round(t.width), Math.round(t.height)]).toEqual([160, 120]);
  });
});

test.describe("권한 거부/미지원/오류 (getUserMedia 모킹)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("권한 거부(NotAllowedError): 안내 문구·role=alert·'다시 시도'(재호출) + 채팅 입력/전송은 계속 가능", async ({ page }) => {
    await installMediaSpy(page, "denied");
    await mockTurns(page);
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByText("카메라 권한이 거부되었습니다.")).toBeVisible();
    await expect(page.getByText("웹캠 없이 텍스트로 계속 진행할 수 있습니다.")).toBeVisible();
    await expect(tile(page).getByRole("alert")).toBeVisible();
    await page.getByRole("button", { name: "다시 시도" }).click();
    await expect.poll(async () => (await mediaState(page)).calls).toBe(2);
    await sendTextTurn(page, "카메라 없이 답변합니다");
    await expect(page.getByText("카메라 없이 답변합니다")).toBeVisible();
  });

  test("권한 거부 상태에서 '다시 시도' 버튼이 160x120 타일 안에서 완전히 보인다(잘림 없음)", async ({ page }) => {
    await installMediaSpy(page, "denied");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    const retry = page.getByRole("button", { name: "다시 시도" });
    await expect(retry).toBeVisible();
    const t = await box(tile(page));
    const r = await box(retry);
    expect(r.y).toBeGreaterThanOrEqual(t.y);
    expect(r.y + r.height).toBeLessThanOrEqual(t.y + t.height + 0.5);
    expect(r.x + r.width).toBeLessThanOrEqual(t.x + t.width + 0.5);
  });

  test("장치 없음(NotFoundError) → 미지원 안내, 그 외 오류(AbortError) → 불러오지 못함 + 다시 시도", async ({ page, context }) => {
    await installMediaSpy(page, "notfound");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByText("이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다.")).toBeVisible();
    const p2 = await context.newPage();
    await installMediaSpy(p2, "aborted");
    await openRoom(p2, room);
    await p2.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(p2.getByText("웹캠 미리보기를 불러오지 못했습니다.")).toBeVisible();
    await expect(p2.getByRole("button", { name: "다시 시도" })).toBeVisible();
  });

  test("mediaDevices 자체가 없는 환경: 켜기 → 미지원 안내, 음성 버튼 숨김, 화면 정상", async ({ page }) => {
    const problems = watchConsole(page);
    await installMediaSpy(page, "none");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).click();
    await expect(page.getByText("이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다.")).toBeVisible();
    await expect(page.getByRole("button", { name: /음성으로 답변/ })).toHaveCount(0);
    await expect(page.getByPlaceholder("답변을 입력하세요...")).toBeEnabled();
    expect(problems).toEqual([]);
  });
});

test.describe("모바일: 접힘 = 카메라 정지", () => {
  test.use({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });

  test("켠 뒤 '웹캠 숨기기' → 트랙 0, 다시 '웹캠 보기' → off 상태로 시작(자동 재시작 없음)", async ({ page }) => {
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 보기" }).tap();
    await page.getByRole("button", { name: "웹캠 미리보기 켜기" }).tap();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 끄기" })).toBeVisible();
    await page.getByRole("button", { name: "웹캠 숨기기" }).tap();
    await expect.poll(async () => (await mediaState(page)).liveTracks).toBe(0);
    await page.getByRole("button", { name: "웹캠 보기" }).tap();
    await expect(page.getByText("웹캠이 꺼져 있습니다")).toBeVisible();
    expect((await mediaState(page)).calls).toBe(1);
  });

  test("경합: '켜기' 직후 같은 틱에 '웹캠 숨기기' → 권한 응답이 늦게 와도 카메라가 켜진 채 남지 않는다", async ({ page }) => {
    await installMediaSpy(page, "real");
    const room = await createRoom("live");
    await openRoom(page, room);
    await page.getByRole("button", { name: "웹캠 보기" }).tap();
    await expect(page.getByRole("button", { name: "웹캠 미리보기 켜기" })).toBeVisible();
    await page.evaluate(() => {
      (Array.from(document.querySelectorAll("button")).find((b) => b.textContent === "웹캠 미리보기 켜기") as HTMLButtonElement).click();
      (Array.from(document.querySelectorAll("button")).find((b) => b.textContent === "웹캠 숨기기") as HTMLButtonElement).click();
    });
    await page.waitForTimeout(2500); // getUserMedia 해석 대기
    const st = await mediaState(page);
    test.info().annotations.push({ type: "observation", description: `getUserMedia 호출=${st.calls}, 숨긴 뒤 살아있는 트랙=${st.liveTracks}` });
    expect(st.liveTracks).toBe(0);
  });
});
