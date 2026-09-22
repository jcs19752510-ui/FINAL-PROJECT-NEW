// 버그 수정 검증(2026-09-22): 사용자 리포트 "면접장 들어오면 첫 질문 안내 후 반응 없음 /
// 음성 답변 후 문제 발생"의 실제 원인과 수정 검증.
//
// 근본 원인: WS(turn_result) 전달은 Redis Pub/Sub이라 발행 시점에 구독 중이 아니면
// 그 이벤트를 영구히 잃는다(재전달 없음). 기존 프런트는 이 유실에 대한 복구 수단이
// 전혀 없어 "AI 엔진 미구현"이라는 실제와 다른 문구에 영원히 머물렀다.
//
// 이 스펙은 `mockInterviewWs`로 WS를 완전히 블랙홀 처리해(서버가 실제로 보내는
// turn_result를 화면이 "받을 수 없는" 상태를 100% 재현) 그래도 화면이 GET 재조회
// 폴백으로 복구되는지를 실제 백엔드/Celery/LLM 파이프라인을 대상으로 검증한다.
//
// 실행 전제(docs/harness/test-infra.md와 동일): 백엔드(8010)·프런트(3000)·Celery
// 워커·llama-server가 이미 기동되어 있어야 한다(모킹 대상은 WS뿐, 나머지는 전부 실통신).
import { test, expect } from "@playwright/test";
import { createRoom, mockInterviewWs, openRoom, watchConsole } from "../unit-20/support";

test.setTimeout(120_000);

test("오프닝 질문: WS 이벤트가 유실돼도 GET 폴백으로 화면에 표시된다", async ({ page }) => {
  const problems = watchConsole(page);
  await mockInterviewWs(page); // 실제 WS를 완전히 블랙홀 처리 — turn_result가 화면에 절대 못 온다.
  const room = await createRoom("live"); // 실제 백엔드: /start 직후 opening_question job이 이미 enqueue됨.
  await openRoom(page, room);

  // 초기에는 (WS가 아무것도 못 주므로) 안내 문구만 보여야 한다.
  await expect(page.getByText("AI 면접관이 첫 질문을 준비하고 있습니다")).toBeVisible();

  // GET 폴백(3초 간격, 최대 45초)이 실제로 opening_question 응답을 찾아내 표시해야 한다.
  await expect(page.locator(".chat-bubble--ai").first()).toBeVisible({ timeout: 50_000 });
  const aiText = await page.locator(".chat-bubble--ai").first().locator(".chat-bubble__text").innerText();
  expect(aiText.length).toBeGreaterThan(0);

  // 옛 오탐 문구("엔진 미구현")가 더 이상 나타나지 않아야 한다.
  await expect(page.getByText(/엔진.*미구현|엔진 구현 예정|아직 준비 중입니다\(엔진/)).toHaveCount(0);

  expect(problems, problems.join("\n")).toEqual([]);
});

test("텍스트 턴: turn_result WS가 유실돼도 GET 재확인으로 답변이 표시된다", async ({ page }) => {
  const problems = watchConsole(page);
  const ws = await mockInterviewWs(page);
  const room = await createRoom("live");
  await openRoom(page, room);

  // 오프닝 질문도 같은 이유로 못 오므로, GET 폴백이 그것부터 채워줄 때까지 기다린다.
  await expect(page.locator(".chat-bubble--ai").first()).toBeVisible({ timeout: 50_000 });
  void ws; // WS는 계속 블랙홀 상태 유지(turn_result도 동일하게 유실시키기 위함).

  await page.getByPlaceholder("답변을 입력하세요...").fill("자기소개를 간단히 하겠습니다.");
  await page.getByRole("button", { name: "전송", exact: true }).click();

  // 12초 타임아웃 뒤 입력창은 기존 설계대로 즉시 재활성화되어야 한다(회귀 확인).
  await expect(page.getByPlaceholder("답변을 입력하세요...")).toBeEnabled({ timeout: 15_000 });

  // 그 뒤 배경 재확인(5초 간격, 최대 6회)이 실제 AI 답변을 찾아내 타임라인에 반영해야 한다.
  await expect(page.locator(".chat-bubble--ai")).toHaveCount(2, { timeout: 40_000 });

  await expect(page.getByText(/엔진.*미구현|엔진 구현 예정|아직 준비 중입니다\(엔진/)).toHaveCount(0);

  expect(problems, problems.join("\n")).toEqual([]);
});
