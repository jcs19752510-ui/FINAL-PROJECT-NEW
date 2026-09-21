// unit-20 06단계 — switch_to_coding 자동 노출(WS 모킹) + 채팅/음성 회귀. TC-B7, B10.
import { expect, test } from "@playwright/test";
import {
  TAB_CODE,
  TAB_WB,
  createRoom,
  installMediaSpy,
  mockInterviewWs,
  mockTurns,
  openCodePanel,
  openRoom,
  openWhiteboardPanel,
  sendTextTurn,
  sidePanel,
  tab,
  watchConsole,
  whiteboardCanvas,
} from "./support";

const JOB = "job-e2e-1";

// launchOptions는 파일(워커) 단위로만 지정 가능하다(describe 내부 test.use({launchOptions})는
// "forces a new worker" 오류로 거부됨 — 06단계에서 실행 중 발견해 최상위로 이동). 이 값은 "채팅/음성
// 회귀" describe에만 필요했지만, 다른 describe는 실제 카메라를 쓰지 않으므로 무해하다.
test.use({ launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] } });

async function setup(page: import("@playwright/test").Page) {
  const ws = await mockInterviewWs(page);
  await mockTurns(page, JOB);
  const room = await createRoom("live");
  await openRoom(page, room);
  await expect.poll(() => ws.count).toBeGreaterThan(0);
  return { ws, room };
}

test.describe("데스크톱: turn_result.control 처리", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("switch_to_coding → 코드 패널 자동 노출(60:40), ai_text가 채팅에 표시, 대기 표시 해제", async ({ page }) => {
    const problems = watchConsole(page);
    const { ws } = await setup(page);
    await sendTextTurn(page, "지원 동기를 말씀드리겠습니다");
    await expect(sidePanel(page)).toBeHidden();
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "이제 코드를 작성해 볼까요?", control: { action: "switch_to_coding" } });
    await expect(sidePanel(page)).toBeVisible();
    await expect(sidePanel(page).getByRole("heading", { name: TAB_CODE })).toBeVisible();
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".chat-bubble--ai").getByText("이제 코드를 작성해 볼까요?")).toBeVisible();
    await expect(page.getByText("AI가 답변을 준비하고 있어요...")).toHaveCount(0);
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 45_000 });
    expect(problems).toEqual([]);
  });

  for (const action of ["none", "next_question", "end_interview", "switch_to_whiteboard", "SWITCH_TO_CODING", ""]) {
    test(`control.action=${JSON.stringify(action)} → 패널이 열리지 않는다(메시지는 표시)`, async ({ page }) => {
      const { ws } = await setup(page);
      await sendTextTurn(page, "답변");
      ws.send({ type: "turn_result", job_id: JOB, ai_text: `응답-${action}`, control: { action } });
      await expect(page.locator(".chat-bubble--ai").getByText(`응답-${action}`)).toBeVisible();
      await page.waitForTimeout(600);
      await expect(sidePanel(page)).toBeHidden();
      await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "false");
    });
  }

  test("control 필드 없음/null이어도 패널 안 열림·오류 없음", async ({ page }) => {
    const problems = watchConsole(page);
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "control 없음" });
    await expect(page.getByText("control 없음")).toBeVisible();
    await sendTextTurn(page, "답변2").catch(() => undefined);
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "control null", control: null });
    await page.waitForTimeout(500);
    await expect(sidePanel(page)).toBeHidden();
    expect(problems).toEqual([]);
  });

  test("job_id가 다른 turn_result(진행 중인 턴과 무관)는 무시된다 — 패널·메시지 모두 반영 안 됨", async ({ page }) => {
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "turn_result", job_id: "other-job", ai_text: "남의 응답", control: { action: "switch_to_coding" } });
    await page.waitForTimeout(700);
    await expect(sidePanel(page)).toBeHidden();
    await expect(page.getByText("남의 응답")).toHaveCount(0);
    await expect(page.getByText("AI가 답변을 준비하고 있어요...")).toBeVisible(); // 여전히 대기 중
  });

  test("이미 열린 코드 패널에 switch_to_coding이 또 와도 닫히지 않는다(토글 아님)", async ({ page }) => {
    const { ws } = await setup(page);
    await openCodePanel(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "코딩 계속", control: { action: "switch_to_coding" } });
    await expect(page.getByText("코딩 계속")).toBeVisible();
    await expect(sidePanel(page)).toBeVisible();
    await expect(tab(page, TAB_CODE)).toHaveAttribute("aria-pressed", "true");
  });

  test("화이트보드가 열려 있을 때 switch_to_coding → 코드로 전환(화이트보드는 언마운트되지 않고 숨김)", async ({ page }) => {
    const { ws } = await setup(page);
    await openWhiteboardPanel(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "코드로", control: { action: "switch_to_coding" } });
    await expect(sidePanel(page).getByRole("heading", { name: TAB_CODE })).toBeVisible();
    await expect(tab(page, TAB_WB)).toHaveAttribute("aria-pressed", "false");
    // 코드 패널이 새로 열리면 Monaco 자신의 canvas(오버뷰 룰러 등)도 DOM에 추가되므로 일반
    // "canvas" 셀렉터는 개수가 1을 초과해 strict-mode 위반이 난다(06단계에서 발견) —
    // 화이트보드 캔버스만 지정해 "언마운트되지 않고 숨겨짐"을 검증한다.
    await expect(whiteboardCanvas(page)).toHaveCount(1);
    await expect(whiteboardCanvas(page)).toBeHidden();
  });

  test("error 이벤트(활성 job) → 오류 배너, 패널 안 열림 / 잘못된 JSON·알 수 없는 type은 무시", async ({ page }) => {
    const problems = watchConsole(page);
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    ws.sendRaw("this is {not json"); // 깨진 JSON
    ws.send({ type: "queue_status", job_id: JOB, position: 3, eta_seconds: 10 });
    ws.send({ type: "totally_unknown", job_id: JOB });
    ws.send({ type: "error", job_id: JOB, code: "AI_SERVICE_TIMEOUT", message: "일시적 오류가 발생했습니다" });
    await expect(page.getByText("일시적 오류가 발생했습니다")).toBeVisible();
    await expect(sidePanel(page)).toBeHidden();
    expect(problems).toEqual([]);
  });

  test("stage_update(stt/llm/tts) → 처리 단계 문구 회귀", async ({ page }) => {
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "stage_update", job_id: JOB, stage: "stt" });
    await expect(page.getByText("음성 인식 중...")).toBeVisible();
    ws.send({ type: "stage_update", job_id: JOB, stage: "llm" });
    await expect(page.getByText("AI가 답변을 준비하고 있어요...")).toBeVisible();
    ws.send({ type: "stage_update", job_id: JOB, stage: "tts" });
    await expect(page.getByText("음성 합성 중...")).toBeVisible();
  });

  test("XSS: ai_text의 HTML은 텍스트로만 표시된다(DOM 주입·실행 없음)", async ({ page }) => {
    const problems = watchConsole(page);
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    const evil = `<img src=x onerror="window.__ai_xss=1"><b>굵게</b>`;
    ws.send({ type: "turn_result", job_id: JOB, ai_text: evil });
    await expect(page.locator(".chat-bubble--ai .chat-bubble__text").last()).toHaveText(evil);
    expect(await page.locator(".chat-bubble--ai img, .chat-bubble--ai b").count()).toBe(0);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => (window as unknown as { __ai_xss?: number }).__ai_xss)).toBeUndefined();
    expect(problems).toEqual([]);
  });
});

test.describe("모바일: switch_to_coding → 전체화면 모달 자동 노출", () => {
  test.use({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });

  test("모달로 열리고 제목에 포커스, Esc → 닫힘 + 탭 포커스 복귀, 채팅 이력 유지", async ({ page }) => {
    const { ws } = await setup(page);
    await sendTextTurn(page, "모바일 답변");
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "모바일 코딩 요청", control: { action: "switch_to_coding" } });
    await expect(sidePanel(page)).toHaveAttribute("role", "dialog");
    await expect(sidePanel(page)).toBeVisible();
    await expect(sidePanel(page).getByRole("heading", { name: TAB_CODE })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(sidePanel(page)).toBeHidden();
    await expect(tab(page, TAB_CODE)).toBeFocused();
    await expect(page.getByText("모바일 코딩 요청")).toBeVisible();
    await expect(page.getByText("모바일 답변")).toBeVisible();
  });

  test("모바일에서 none이면 모달이 뜨지 않는다", async ({ page }) => {
    const { ws } = await setup(page);
    await sendTextTurn(page, "답변");
    ws.send({ type: "turn_result", job_id: JOB, ai_text: "그냥 답", control: { action: "none" } });
    await expect(page.getByText("그냥 답")).toBeVisible();
    await page.waitForTimeout(500);
    await expect(sidePanel(page)).toBeHidden();
  });
});

test.describe("채팅/음성 회귀", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("텍스트 전송: 낙관적 표시·입력 초기화·카운터·대기 문구, 빈/공백 입력은 전송 불가, 4000자 상한", async ({ page }) => {
    await mockInterviewWs(page);
    const turns = await mockTurns(page, JOB);
    const room = await createRoom("live");
    await openRoom(page, room);
    const send = page.getByRole("button", { name: "전송", exact: true });
    await expect(send).toBeDisabled();
    await page.getByPlaceholder("답변을 입력하세요...").fill("   ");
    await expect(send).toBeDisabled();
    await page.getByPlaceholder("답변을 입력하세요...").fill("x".repeat(4100));
    await expect(page.getByText("4000/4000")).toBeVisible();
    await page.getByPlaceholder("답변을 입력하세요...").fill("첫 답변입니다");
    await expect(page.getByText("7/4000")).toBeVisible();
    await send.click();
    await expect(page.locator(".chat-bubble--user").getByText("첫 답변입니다")).toBeVisible();
    await expect(page.getByPlaceholder("답변을 입력하세요...")).toHaveValue("");
    await expect(page.getByText("AI가 답변을 준비하고 있어요...")).toBeVisible();
    expect(JSON.parse(turns.bodies[0])).toMatchObject({ text: "첫 답변입니다" });
  });

  test("음성 버튼: 동의 없으면 인라인 동의 프롬프트, 취소로 닫힘, 동의하면 실제 동의 등록 후 녹음 시작→중지→업로드(턴 모킹)", async ({ page }) => {
    await installMediaSpy(page, "real");
    await mockInterviewWs(page);
    let voiceBodyType = "";
    await page.route(/\/interviews\/[^/]+\/turns$/, async (route) => {
      voiceBodyType = route.request().headers()["content-type"] ?? "";
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ job_id: JOB }) });
    });
    const room = await createRoom("live");
    await openRoom(page, room);
    const mic = page.getByRole("button", { name: "음성으로 답변" });
    await expect(mic).toBeEnabled();
    await mic.click();
    await expect(page.getByText(/생체정보\(음성\) 수집 동의가 필요합니다/)).toBeVisible();
    await page.getByRole("button", { name: "취소" }).click();
    await expect(page.getByText(/생체정보\(음성\) 수집 동의가 필요합니다/)).toHaveCount(0);
    await mic.click();
    const [consentResp] = await Promise.all([
      page.waitForResponse((r) => /\/consents$/.test(r.url()) && r.request().method() === "POST"),
      page.getByRole("button", { name: "동의하고 녹음 시작" }).click(),
    ]);
    expect(consentResp.status()).toBe(201);
    await expect(page.getByRole("button", { name: /녹음 중지/ })).toBeVisible();
    await page.waitForTimeout(1200);
    await page.getByRole("button", { name: /녹음 중지/ }).click();
    await expect.poll(() => voiceBodyType).toMatch(/multipart\/form-data/);
    await expect(page.getByText("AI가 답변을 준비하고 있어요...")).toBeVisible();
  });

  test("음성 동의가 이미 있으면 프롬프트 없이 바로 녹음", async ({ page }) => {
    await mockInterviewWs(page);
    const room = await createRoom("live");
    const { call } = await import("./support");
    await call("POST", "/consents", room.account.token, { consent_type: "biometric_voice" });
    await openRoom(page, room);
    await page.getByRole("button", { name: "음성으로 답변" }).click();
    await expect(page.getByRole("button", { name: /녹음 중지/ })).toBeVisible();
    await expect(page.getByText(/생체정보\(음성\) 수집 동의가 필요합니다/)).toHaveCount(0);
    await page.getByRole("button", { name: /녹음 중지/ }).click(); // 정리(녹음 중지 → 업로드 시도는 서버 실호출이라 실패해도 무방)
  });

  test("코드 패널을 연 상태에서도 채팅 입력/전송이 그대로 동작한다", async ({ page }) => {
    await mockInterviewWs(page);
    await mockTurns(page, JOB);
    const room = await createRoom("live");
    await openRoom(page, room);
    await openCodePanel(page);
    await sendTextTurn(page, "분할 화면에서의 답변");
    await expect(page.locator(".chat-bubble--user").getByText("분할 화면에서의 답변")).toBeVisible();
  });
});
