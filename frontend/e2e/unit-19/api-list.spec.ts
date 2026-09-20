/**
 * unit-19 06단계 — `GET /api/v1/interviews`(내 면접 목록) API 수준 검증 (AC-B1~B10 + 회귀 + 경계/부하).
 * 사전 조건: 백엔드가 E2E_API_URL(기본 http://localhost:8720/api/v1)에서 동작, `final-project-db` 컨테이너 접근 가능,
 *            (AC-B11 회귀 케이스의 /start·/end 는 Celery job 을 enqueue 하므로 서버의 REDIS_URL 이 실행자 전용 논리 DB 여야 한다.)
 * 실행: cd frontend && E2E_API_URL=... npx playwright test e2e/unit-19/api-list.spec.ts
 */
import { API_BASE, LIST_KEYS, authHeader, createSessions, dbStatus, listBody, listInterviews, setSession, sql, test, expect } from "./helpers";
import type { ListItem } from "./helpers";

function orderedIds(candidateId: string): string[] {
  return sql(`select id from interviews where candidate_id='${candidateId}' order by coalesce(started_at, created_at) desc, id desc`).map((r) => r[0]);
}

test.describe("인증·권한 경계", () => {
  test("[AC-B1] Authorization 헤더 없음 -> 401 AUTH_INVALID_TOKEN (RFC 7807 본문)", async ({ request }) => {
    const res = await request.get(`${API_BASE}/interviews`);
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body.code).toBe("AUTH_INVALID_TOKEN");
    expect(body.status).toBe(401);
    expect(typeof body.detail).toBe("string");
  });

  test("[AC-B2] 쓰레기/변형 토큰 -> 401 AUTH_INVALID_TOKEN (500 아님)", async ({ request }) => {
    const bad = [
      "Bearer garbage",
      "Bearer a.b.c",
      "Bearer ",
      "Bearer null",
      "Basic Zm9vOmJhcg==",
      `Bearer ${"A".repeat(20000)}`,
      "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiLCJ0eXBlIjoiYWNjZXNzIn0.",
    ];
    for (const header of bad) {
      const res = await request.get(`${API_BASE}/interviews`, { headers: { Authorization: header } });
      expect(res.status(), `Authorization: ${header.slice(0, 40)}`).toBe(401);
      expect((await res.json()).code).toBe("AUTH_INVALID_TOKEN");
    }
  });

  test("[AC-B2+] 다른 종류 토큰(refresh 토큰)·탈퇴(deleted_at) 계정 토큰 -> 401", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const login = await request.post(`${API_BASE}/auth/login`, { data: { email: acct.email, password: acct.password } });
    const setCookie = login.headersArray().find((h) => h.name.toLowerCase() === "set-cookie" && h.value.startsWith("refresh_token="));
    expect(setCookie, "refresh_token 쿠키").toBeTruthy();
    const refresh = setCookie!.value.split(";")[0].slice("refresh_token=".length);
    const asBearer = await request.get(`${API_BASE}/interviews`, { headers: authHeader(refresh) });
    expect(asBearer.status()).toBe(401);
    expect((await asBearer.json()).code).toBe("AUTH_INVALID_TOKEN");

    expect((await listInterviews(request, acct.token)).status()).toBe(200);
    sql(`update users set deleted_at=now() where id='${acct.id}'`);
    const deleted = await listInterviews(request, acct.token);
    expect(deleted.status()).toBe(401);
  });

  test("[AC-B4] recruiter/admin -> 403 AUTH_FORBIDDEN (세션 유무·recruiter_id 지정과 무관)", async ({ request, kit }) => {
    const recruiter = await kit.create("recruiter");
    const empty = await listInterviews(request, recruiter.token);
    expect(empty.status()).toBe(403);
    expect((await empty.json()).code).toBe("AUTH_FORBIDDEN");

    const candidate = await kit.create("candidate");
    const [sid] = await createSessions(request, candidate.token, 1);
    sql(`update interviews set recruiter_id='${recruiter.id}' where id='${sid}'`);
    const withOwn = await listInterviews(request, recruiter.token);
    expect(withOwn.status()).toBe(403);
    expect(await withOwn.text()).not.toContain(sid);

    // 역할은 토큰 클레임이 아니라 DB의 현재 값으로 판정된다: candidate 토큰 발급 후 admin/recruiter 로 바뀌면 즉시 403
    sql(`update users set role='admin' where id='${candidate.id}'`);
    const admin = await listInterviews(request, candidate.token);
    expect(admin.status()).toBe(403);
    expect((await admin.json()).code).toBe("AUTH_FORBIDDEN");
    sql(`update users set role='recruiter' where id='${candidate.id}'`);
    expect((await listInterviews(request, candidate.token)).status()).toBe(403);
  });
});

test.describe("정상 경로·응답 계약", () => {
  test("[AC-B3] 세션 없는 신규 candidate -> 200 [] (JSON 배열)", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const res = await listInterviews(request, acct.token);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("application/json");
    expect(await res.text()).toBe("[]");
  });

  test("[AC-B5] POST /interviews 3회 -> 3건 모두 scheduled/none/resumable=false, created_at 내림차순", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 3);
    const list = await listBody(request, acct.token);
    expect(list).toHaveLength(3);
    expect(list.map((i) => i.id)).toEqual([...ids].reverse());
    for (const item of list) {
      expect(item).toMatchObject({ status: "scheduled", report_status: "none", resumable: false, started_at: null, ended_at: null, overall_score: null });
    }
    const times = list.map((i) => Date.parse(i.created_at));
    expect(times[0]).toBeGreaterThanOrEqual(times[1]);
    expect(times[1]).toBeGreaterThanOrEqual(times[2]);
  });

  test("[AC-B6][AC-B10] 7개 상태 혼합 -> 값이 DB와 일치, 정렬=COALESCE(started_at,created_at) desc, 키 집합 정확", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 7);
    const [scheduled, live1h, paused2h, queued3h, failed4h, live25h, ready30h] = ids;
    setSession(live1h, { status: "live", startedAgo: "1 hour" });
    setSession(paused2h, { status: "paused", startedAgo: "2 hours" });
    setSession(queued3h, { status: "completed", report: "queued", startedAgo: "3 hours", endedAgo: "2 hours 30 minutes" });
    setSession(failed4h, { status: "completed", report: "failed", startedAgo: "4 hours", endedAgo: "3 hours" });
    setSession(live25h, { status: "live", startedAgo: "25 hours" });
    setSession(ready30h, { status: "completed", report: "ready", score: "7.5", startedAgo: "30 hours", endedAgo: "29 hours" });
    // scheduled 는 started_at NULL 이므로 created_at(방금)으로 정렬 -> 맨 앞
    const res = await listInterviews(request, acct.token);
    expect(res.status()).toBe(200);
    const list = (await res.json()) as ListItem[];
    expect(list.map((i) => i.id)).toEqual([scheduled, live1h, paused2h, queued3h, failed4h, live25h, ready30h]);
    const by = new Map(list.map((i) => [i.id, i]));
    expect(by.get(scheduled)).toMatchObject({ status: "scheduled", report_status: "none", resumable: false, overall_score: null });
    expect(by.get(live1h)).toMatchObject({ status: "live", report_status: "none", resumable: true });
    expect(by.get(paused2h)).toMatchObject({ status: "paused", resumable: true });
    expect(by.get(queued3h)).toMatchObject({ status: "completed", report_status: "queued", resumable: false });
    expect(by.get(failed4h)).toMatchObject({ status: "completed", report_status: "failed", resumable: false });
    expect(by.get(live25h)).toMatchObject({ status: "expired", resumable: false });
    expect(by.get(ready30h)).toMatchObject({ status: "completed", report_status: "ready", overall_score: "7.5", resumable: false });
    expect(by.get(ready30h)!.ended_at).not.toBeNull();
    // AC-B10 키 집합
    for (const item of list) {
      expect(Object.keys(item).sort()).toEqual(LIST_KEYS);
    }
    // DB 대조(응답 각 항목이 DB 행과 일치)
    for (const item of list) {
      const row = sql(
        `select status, report_status, coalesce(overall_score::text,''), started_at is not null, ended_at is not null from interviews where id='${item.id}'`,
      )[0];
      expect(row[0]).toBe(item.status);
      expect(row[1]).toBe(item.report_status);
      expect(row[2]).toBe(item.overall_score ?? "");
      expect(row[3] === "t").toBe(item.started_at !== null);
      expect(row[4] === "t").toBe(item.ended_at !== null);
    }
    expect(list.map((i) => i.id)).toEqual(orderedIds(acct.id));
  });

  test("[AC-B10] 응답에 candidate_id/recruiter_id/rubric_template_id/이메일 등 내부 식별자가 문자열로도 없다", async ({ request, kit }) => {
    const recruiter = await kit.create("recruiter");
    const acct = await kit.create("candidate");
    const [sid] = await createSessions(request, acct.token, 1);
    const tpl = sql(`insert into rubric_templates (id, recruiter_id, name, criteria_json) values (gen_random_uuid(), '${recruiter.id}', 'u19 tpl', '[]'::jsonb) returning id`)[0][0];
    sql(`update interviews set recruiter_id='${recruiter.id}', rubric_template_id='${tpl}' where id='${sid}'`);
    const text = await (await listInterviews(request, acct.token)).text();
    for (const secret of [acct.id, recruiter.id, tpl, acct.email, recruiter.email, "candidate_id", "recruiter_id", "rubric_template_id", "password"]) {
      expect(text, `응답에 ${secret} 노출`).not.toContain(secret);
    }
  });

  test("[AC-B6+] overall_score 경계값: 0.0 / 10.0 / 99.9 / 7.5 는 소수 1자리 문자열, null 은 null", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 5);
    ["0.0", "10.0", "99.9", "7.5"].forEach((score, idx) => {
      setSession(ids[idx], { status: "completed", report: "ready", score, startedAgo: `${idx + 1} hours`, endedAgo: "10 minutes" });
    });
    const list = await listBody(request, acct.token);
    // 마지막 생성(ids[4], scheduled, score null)이 맨 앞
    expect(list.map((i) => i.overall_score)).toEqual([null, "0.0", "10.0", "99.9", "7.5"]);
  });
});

test.describe("lazy expiry(24h) 경계·일관성", () => {
  test("[AC-B7] live 25h -> 응답 expired + DB 커밋, 재조회 일관", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const [sid] = await createSessions(request, acct.token, 1);
    setSession(sid, { status: "live", startedAgo: "25 hours" });
    expect(dbStatus(sid).status).toBe("live");
    const first = await listBody(request, acct.token);
    expect(first[0]).toMatchObject({ id: sid, status: "expired", resumable: false });
    expect(dbStatus(sid).status).toBe("expired");
    const second = await listBody(request, acct.token);
    expect(second).toEqual(first);
    // 상세 조회도 동일 상태
    const detail = await request.get(`${API_BASE}/interviews/${sid}`, { headers: authHeader(acct.token) });
    expect(detail.status()).toBe(200);
    expect(await detail.json()).toMatchObject({ status: "expired", resumable: false });
  });

  test("[AC-B7+] 경계: 23h59m55s 는 live 유지 / 24h00m05s 는 expired / paused 도 동일 / completed·started_at NULL live 는 만료 안 됨", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 6);
    setSession(ids[0], { status: "live", startedAgo: "23 hours 59 minutes 55 seconds" });
    setSession(ids[1], { status: "live", startedAgo: "24 hours 5 seconds" });
    setSession(ids[2], { status: "paused", startedAgo: "24 hours 5 seconds" });
    setSession(ids[3], { status: "paused", startedAgo: "23 hours 59 minutes 55 seconds" });
    setSession(ids[4], { status: "completed", report: "ready", score: "5.0", startedAgo: "100 hours", endedAgo: "99 hours" });
    // 이상 데이터: started_at NULL 인 live -> 만료 판정 불가, 크래시 없이 live 유지, 정렬은 created_at
    setSession(ids[5], { status: "live" });
    const list = await listBody(request, acct.token);
    const by = new Map(list.map((i) => [i.id, i]));
    expect(by.get(ids[0])!.status).toBe("live");
    expect(by.get(ids[1])!.status).toBe("expired");
    expect(by.get(ids[2])!.status).toBe("expired");
    expect(by.get(ids[3])!.status).toBe("paused");
    expect(by.get(ids[4])!.status).toBe("completed");
    expect(by.get(ids[5])).toMatchObject({ status: "live", started_at: null, resumable: true });
    expect(list[0].id).toBe(ids[5]); // created_at 이 가장 최근이라 started_at NULL 행이 맨 앞
  });

  test("[AC-B7++] 한 요청에서 여러 세션이 만료되어(요청 중 커밋 반복) 모든 항목 값이 올바르다", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 6);
    setSession(ids[0], { status: "live", startedAgo: "30 hours" });
    setSession(ids[1], { status: "completed", report: "ready", score: "8.5", startedAgo: "31 hours", endedAgo: "30 hours" });
    setSession(ids[2], { status: "paused", startedAgo: "32 hours" });
    setSession(ids[3], { status: "live", startedAgo: "33 hours" });
    setSession(ids[4], { status: "live", startedAgo: "1 hour" });
    const list = await listBody(request, acct.token);
    const by = new Map(list.map((i) => [i.id, i]));
    expect(by.get(ids[0])!.status).toBe("expired");
    expect(by.get(ids[1])).toMatchObject({ status: "completed", overall_score: "8.5", report_status: "ready" });
    expect(by.get(ids[2])!.status).toBe("expired");
    expect(by.get(ids[3])!.status).toBe("expired");
    expect(by.get(ids[4])).toMatchObject({ status: "live", resumable: true });
    expect(by.get(ids[5])).toMatchObject({ status: "scheduled" });
    for (const id of [ids[0], ids[2], ids[3]]) expect(dbStatus(id).status).toBe("expired");
    expect(dbStatus(ids[4]).status).toBe("live");
    expect(list.map((i) => i.id)).toEqual(orderedIds(acct.id));
  });

  test("[AC-B7+++] 동시 요청 5개가 같은 만료 대상을 다퉈도 전부 200, 동일 결과", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 4);
    ids.forEach((id) => setSession(id, { status: "live", startedAgo: "26 hours" }));
    const results = await Promise.all(Array.from({ length: 5 }, () => listInterviews(request, acct.token)));
    for (const r of results) expect(r.status()).toBe(200);
    const bodies = await Promise.all(results.map((r) => r.json() as Promise<ListItem[]>));
    for (const b of bodies) expect(b.every((i) => i.status === "expired")).toBe(true);
    ids.forEach((id) => expect(dbStatus(id).status).toBe("expired"));
  });
});

test.describe("소유자 격리(수평 권한 상승)", () => {
  test("[AC-B8][AC-B9] A/B 격리, ?candidate_id=B 및 기타 쿼리 파라미터 무시", async ({ request, kit }) => {
    const a = await kit.create("candidate");
    const b = await kit.create("candidate");
    const aIds = await createSessions(request, a.token, 2);
    const bIds = await createSessions(request, b.token, 3);
    setSession(bIds[0], { status: "live", startedAgo: "1 hour" });

    const aList = await listBody(request, a.token);
    expect(aList.map((i) => i.id).sort()).toEqual([...aIds].sort());
    for (const id of bIds) expect(JSON.stringify(aList)).not.toContain(id);
    const bList = await listBody(request, b.token);
    expect(bList.map((i) => i.id).sort()).toEqual([...bIds].sort());
    for (const id of aIds) expect(JSON.stringify(bList)).not.toContain(id);

    const spoofs = [
      `?candidate_id=${b.id}`,
      `?candidate_id=${b.id}&candidate_id=${a.id}`,
      "?candidate_id=",
      "?candidate_id=not-a-uuid",
      `?user_id=${b.id}`,
      `?recruiter_id=${a.id}`,
      "?limit=1",
      "?offset=1",
      "?status=completed",
    ];
    for (const q of spoofs) {
      const res = await listInterviews(request, a.token, q);
      expect(res.status(), q).toBe(200);
      const body = (await res.json()) as ListItem[];
      expect(body.map((i) => i.id).sort(), q).toEqual([...aIds].sort());
    }
    // 반대로 A가 B 세션 상세를 조회하면 403(기존 동작)
    const cross = await request.get(`${API_BASE}/interviews/${bIds[0]}`, { headers: authHeader(a.token) });
    expect(cross.status()).toBe(403);
  });

  test("[AC-B8+] 다른 사용자의 lazy expiry 대상은 내 요청으로 만료 확정되지 않는다(부작용 격리)", async ({ request, kit }) => {
    const a = await kit.create("candidate");
    const b = await kit.create("candidate");
    const [bid] = await createSessions(request, b.token, 1);
    setSession(bid, { status: "live", startedAgo: "40 hours" });
    await listBody(request, a.token);
    expect(dbStatus(bid).status).toBe("live");
    await listBody(request, b.token);
    expect(dbStatus(bid).status).toBe("expired");
  });
});

test.describe("정렬 타이브레이커·started_at 경계", () => {
  test("동일 started_at 동률은 id 내림차순으로 고정되고 반복 호출에서도 순서가 흔들리지 않는다", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const ids = await createSessions(request, acct.token, 6);
    ids.forEach((id) => setSession(id, { status: "completed", startedAt: "2026-03-01 09:00:00+09" }));
    const expected = [...ids].sort().reverse();
    for (let i = 0; i < 5; i++) {
      const list = await listBody(request, acct.token);
      expect(list.map((x) => x.id)).toEqual(expected);
    }
    expect(orderedIds(acct.id)).toEqual(expected);
  });

  test("started_at NULL 세션(created_at 기준)과 started_at 보유 세션이 섞이면 표시 일시 기준으로 정렬된다", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const [old, mid, fresh] = await createSessions(request, acct.token, 3);
    // old: created 5시간 전이지만 started_at 이 1분 전 / mid: started_at NULL, created 2시간 전 / fresh: created 1시간 전이지만 started_at 10시간 전
    sql(`update interviews set created_at = now() - interval '5 hours' where id='${old}'`);
    sql(`update interviews set created_at = now() - interval '2 hours' where id='${mid}'`);
    sql(`update interviews set created_at = now() - interval '1 hour' where id='${fresh}'`);
    setSession(old, { status: "completed", startedAgo: "1 minute", endedAgo: "10 seconds" });
    setSession(fresh, { status: "completed", startedAgo: "10 hours", endedAgo: "9 hours" });
    const list = await listBody(request, acct.token);
    expect(list.map((i) => i.id)).toEqual([old, mid, fresh]);
  });
});

test.describe("회귀 — 기존 세션 API (unit-2/3) 동작 무변경", () => {
  test("[AC-B11] POST /interviews 201 -> GET /{id} -> 동의 없이 /start 403 -> 동의 후 /start 202 -> /resume 멱등 -> /end 202 -> 종료 후 /resume 409 -> 목록 반영", async ({
    request,
    kit,
  }) => {
    const acct = await kit.create("candidate");
    const h = authHeader(acct.token);
    const created = await request.post(`${API_BASE}/interviews`, { headers: h });
    expect(created.status()).toBe(201);
    const iv = (await created.json()) as { id: string; candidate_id: string; status: string; report_status: string };
    expect(iv).toMatchObject({ candidate_id: acct.id, status: "scheduled", report_status: "none" });

    const detail = await request.get(`${API_BASE}/interviews/${iv.id}`, { headers: h });
    expect(detail.status()).toBe(200);
    const detailBody = await detail.json();
    expect(detailBody).toMatchObject({ status: "scheduled", resumable: false });
    expect(Object.keys(detailBody)).toContain("candidate_id"); // 상세는 기존 계약 유지(목록과 다름)

    const noConsent = await request.post(`${API_BASE}/interviews/${iv.id}/start`, { headers: h });
    expect(noConsent.status()).toBe(403);
    expect((await noConsent.json()).code).toBe("CONSENT_REQUIRED_NOTICE");

    const noResume = await request.post(`${API_BASE}/interviews/${iv.id}/resume`, { headers: h });
    expect(noResume.status()).toBe(409);

    const consent = await request.post(`${API_BASE}/consents`, { headers: h, data: { consent_type: "ai_interview_notice" } });
    expect(consent.status(), await consent.text()).toBe(201);

    const started = await request.post(`${API_BASE}/interviews/${iv.id}/start`, { headers: h });
    expect(started.status(), await started.text()).toBe(202);
    expect(dbStatus(iv.id).status).toBe("live");

    let list = await listBody(request, acct.token);
    expect(list[0]).toMatchObject({ id: iv.id, status: "live", resumable: true });
    expect(list[0].started_at).not.toBeNull();

    const resume = await request.post(`${API_BASE}/interviews/${iv.id}/resume`, { headers: h });
    expect(resume.status()).toBe(200);
    expect(await resume.json()).toMatchObject({ status: "live", resumable: true });

    const ended = await request.post(`${API_BASE}/interviews/${iv.id}/end`, { headers: h });
    expect(ended.status()).toBe(202);
    list = await listBody(request, acct.token);
    expect(list[0]).toMatchObject({ id: iv.id, status: "completed", report_status: "queued", resumable: false });
    expect(list[0].ended_at).not.toBeNull();

    const afterEnd = await request.post(`${API_BASE}/interviews/${iv.id}/resume`, { headers: h });
    expect(afterEnd.status()).toBe(409);
  });

  test("[AC-B11+] 만료 세션 상세 200(expired)/resume 410 SESSION_EXPIRED, recruiter 의 POST /interviews 403, 타인 세션 start 403, 없는 id 404, 형식 오류 422", async ({
    request,
    kit,
  }) => {
    const a = await kit.create("candidate");
    const b = await kit.create("candidate");
    const recruiter = await kit.create("recruiter");
    const [sid] = await createSessions(request, a.token, 1);
    setSession(sid, { status: "live", startedAgo: "48 hours" });
    const resume = await request.post(`${API_BASE}/interviews/${sid}/resume`, { headers: authHeader(a.token) });
    expect(resume.status()).toBe(410);
    expect((await resume.json()).code).toBe("SESSION_EXPIRED");
    const detail = await request.get(`${API_BASE}/interviews/${sid}`, { headers: authHeader(a.token) });
    expect(await detail.json()).toMatchObject({ status: "expired", resumable: false });
    expect((await request.post(`${API_BASE}/interviews`, { headers: authHeader(recruiter.token) })).status()).toBe(403);
    expect((await request.post(`${API_BASE}/interviews/${sid}/start`, { headers: authHeader(b.token) })).status()).toBe(403);
    expect((await request.get(`${API_BASE}/interviews/00000000-0000-0000-0000-000000000000`, { headers: authHeader(a.token) })).status()).toBe(404);
    expect((await request.get(`${API_BASE}/interviews/not-a-uuid`, { headers: authHeader(a.token) })).status()).toBe(422);
  });

  test("[AC-B11++] 라우트 충돌 없음: GET /interviews 200, PUT/DELETE /interviews 405", async ({ request, kit }) => {
    const acct = await kit.create("candidate");
    const h = authHeader(acct.token);
    expect((await request.put(`${API_BASE}/interviews`, { headers: h })).status()).toBe(405);
    expect((await request.delete(`${API_BASE}/interviews`, { headers: h })).status()).toBe(405);
    expect((await request.get(`${API_BASE}/interviews`, { headers: h })).status()).toBe(200);
  });
});

test.describe("규모 스모크(정밀 측정은 06 결과서 8절)", () => {
  test("세션 300건 + 만료 대상 28건: 200, 정렬·건수 정확, 응답 10초 이내", async ({ request, kit }) => {
    test.setTimeout(120_000);
    const acct = await kit.create("candidate");
    sql(
      `insert into interviews (id, candidate_id, status, report_status, started_at, created_at)
       select gen_random_uuid(), '${acct.id}', case when g % 10 = 0 then 'live'::interview_status else 'completed'::interview_status end, 'ready'::report_status,
              now() - (g || ' hours')::interval, now() - (g || ' hours')::interval
       from generate_series(1, 300) g`,
    );
    // g%10==0 인 30건 중 g=10,20 은 24h 이내라 live 유지, 나머지 28건은 만료 대상
    const t0 = Date.now();
    const res = await listInterviews(request, acct.token);
    const ms = Date.now() - t0;
    expect(res.status()).toBe(200);
    const list = (await res.json()) as ListItem[];
    expect(list).toHaveLength(300);
    expect(list.filter((i) => i.status === "expired")).toHaveLength(28);
    expect(list.filter((i) => i.status === "live")).toHaveLength(2);
    expect(ms, `응답 ${ms}ms`).toBeLessThan(10000);
    expect(list.map((i) => i.id)).toEqual(orderedIds(acct.id));
  });
});
