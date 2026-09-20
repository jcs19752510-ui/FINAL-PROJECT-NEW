// unit-20 06단계 — 백엔드 API 회귀(A3) + 권한/경계. 화면 배선이 의존하는 코드 제출·화이트보드 API 계약을
// 변경 없음 그대로 재확인한다(Next 서버 불필요, 백엔드만 필요). TC-A3-*.
import { expect, test } from "@playwright/test";
import { call, createAccount, createRoom } from "./support";

test.describe("A3 코드 제출 API", () => {
  test("정상: POST 201 → GET 최신순, language 필터, 언어 정규화", async () => {
    const { account, interviewId } = await createRoom("live");
    const t = account.token;
    const a = await call("POST", `/interviews/${interviewId}/code-submissions`, t, { language: "python", content: "print(1)" });
    expect(a.status).toBe(201);
    expect(a.json.language).toBe("python");
    const b = await call("POST", `/interviews/${interviewId}/code-submissions`, t, { language: "go", content: "package main" });
    expect(b.status).toBe(201);
    const c = await call("POST", `/interviews/${interviewId}/code-submissions`, t, { language: "PYTHON ", content: "print(2)" });
    expect(c.status).toBe(201);
    expect(c.json.language).toBe("python"); // 서버가 strip+lower 정규화
    const all = await call("GET", `/interviews/${interviewId}/code-submissions`, t);
    expect(all.status).toBe(200);
    expect(all.json.map((x: { content: string }) => x.content)).toEqual(["print(2)", "package main", "print(1)"]);
    const py = await call("GET", `/interviews/${interviewId}/code-submissions?language=python`, t);
    expect(py.json.map((x: { content: string }) => x.content)).toEqual(["print(2)", "print(1)"]);
    const none = await call("GET", `/interviews/${interviewId}/code-submissions?language=rust`, t);
    expect(none.json).toEqual([]);
  });

  test("경계: content 0자·20000자 허용, 20001자는 422, 허용 목록 밖 언어 422", async () => {
    const { account, interviewId } = await createRoom("live");
    const t = account.token;
    const url = `/interviews/${interviewId}/code-submissions`;
    expect((await call("POST", url, t, { language: "python", content: "" })).status).toBe(201);
    expect((await call("POST", url, t, { language: "python", content: "a".repeat(20000) })).status).toBe(201);
    const over = await call("POST", url, t, { language: "python", content: "a".repeat(20001) });
    expect(over.status).toBe(422);
    expect(typeof over.json.detail).toBe("string");
    const bad = await call("POST", url, t, { language: "cobol", content: "x" });
    expect(bad.status).toBe(422);
    expect((await call("POST", url, t, { language: "", content: "x" })).status).toBe(422);
    expect((await call("POST", url, t, { content: "x" })).status).toBe(422);
  });

  test("권한 경계: 타인 지원자/채용담당자 403, 무토큰·위조 토큰 401, 없는 세션 404, UUID 아님 422", async () => {
    const { account, interviewId } = await createRoom("live");
    const other = await createAccount("candidate");
    const recruiter = await createAccount("recruiter");
    const url = `/interviews/${interviewId}/code-submissions`;
    const body = { language: "python", content: "x" };
    for (const who of [other, recruiter]) {
      expect((await call("POST", url, who.token, body)).status).toBe(403);
      expect((await call("GET", url, who.token)).status).toBe(403);
    }
    expect((await call("POST", url, undefined, body)).status).toBe(401);
    expect((await call("GET", url, "not.a.jwt")).status).toBe(401);
    expect((await call("GET", `/interviews/00000000-0000-4000-8000-000000000000/code-submissions`, account.token)).status).toBe(404);
    expect((await call("GET", `/interviews/not-a-uuid/code-submissions`, account.token)).status).toBe(422);
    // 타인이 쓰려 한 시도가 소유자 데이터에 흔적을 남기지 않았는지
    expect((await call("GET", url, account.token)).json).toEqual([]);
  });

  test("[관찰] 서버는 세션 상태(completed)를 검사하지 않는다 — 비-live 차단은 프런트(탭 disabled)에만 있다", async () => {
    const { account, interviewId } = await createRoom("completed");
    const r = await call("POST", `/interviews/${interviewId}/code-submissions`, account.token, { language: "python", content: "x" });
    test.info().annotations.push({ type: "observation", description: `completed 세션에 코드 POST → ${r.status} (설계상 서버 상태검사 없음, unit-20-note §3-3)` });
    expect(r.status).toBe(201);
  });
});

test.describe("A3 화이트보드 API", () => {
  const stroke = (n: number) => ({ points: Array.from({ length: n }, (_, i) => ({ x: i, y: i })), color: "#1f2937", width: 3 });

  test("정상: 저장 전 GET은 null, PUT 200 → GET 최신 1건, 빈 strokes 저장 가능", async () => {
    const { account, interviewId } = await createRoom("live");
    const t = account.token;
    const url = `/interviews/${interviewId}/whiteboard`;
    const first = await call("GET", url, t);
    expect(first.status).toBe(200);
    expect(first.json).toBeNull();
    const put = await call("PUT", url, t, { strokes: [stroke(3)] });
    expect(put.status).toBe(200);
    expect(put.json.strokes).toHaveLength(1);
    expect((await call("PUT", url, t, { strokes: [] })).status).toBe(200);
    const latest = await call("GET", url, t);
    expect(latest.json.strokes).toEqual([]); // 가장 최근 저장본(빈 캔버스)
  });

  test("경계·예외: 2000 스트로크 허용/2001 거부, 점 0개·width 0·width 65 거부, 5000점 허용/5001 거부", async () => {
    const { account, interviewId } = await createRoom("live");
    const t = account.token;
    const url = `/interviews/${interviewId}/whiteboard`;
    expect((await call("PUT", url, t, { strokes: Array.from({ length: 2000 }, () => stroke(1)) })).status).toBe(200);
    expect((await call("PUT", url, t, { strokes: Array.from({ length: 2001 }, () => stroke(1)) })).status).toBe(422);
    expect((await call("PUT", url, t, { strokes: [{ points: [], color: "#000", width: 3 }] })).status).toBe(422);
    expect((await call("PUT", url, t, { strokes: [{ ...stroke(2), width: 0 }] })).status).toBe(422);
    expect((await call("PUT", url, t, { strokes: [{ ...stroke(2), width: 65 }] })).status).toBe(422);
    expect((await call("PUT", url, t, { strokes: [stroke(5000)] })).status).toBe(200);
    expect((await call("PUT", url, t, { strokes: [stroke(5001)] })).status).toBe(422);
    expect((await call("PUT", url, t, { strokes: "x" })).status).toBe(422);
  });

  test("권한 경계: 타인·채용담당자 403, 무토큰 401", async () => {
    const { account, interviewId } = await createRoom("live");
    const other = await createAccount("candidate");
    const recruiter = await createAccount("recruiter");
    const url = `/interviews/${interviewId}/whiteboard`;
    await call("PUT", url, account.token, { strokes: [stroke(2)] });
    for (const who of [other, recruiter]) {
      expect((await call("PUT", url, who.token, { strokes: [] })).status).toBe(403);
      expect((await call("GET", url, who.token)).status).toBe(403);
    }
    expect((await call("GET", url, undefined)).status).toBe(401);
    expect((await call("GET", url, account.token)).json.strokes).toHaveLength(1); // 타인의 PUT이 덮어쓰지 못함
  });
});
