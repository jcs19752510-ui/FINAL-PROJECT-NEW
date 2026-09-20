/**
 * unit-19(06단계) 검증 헬퍼 — GET /interviews + [C-03] 지원자 홈.
 *
 * - 계정은 반드시 `harness_test_<uuid v4 전체 36자>@harness-test.example` 형식(docs/harness/test-infra.md §3).
 * - 세션 상태 조작·정리는 `docker exec <db 컨테이너> psql`로 수행한다(신규 패키지 없이 Node에서 DB에 닿는 유일한 경로).
 *   컨테이너/사용자/DB 이름은 개발용 docker-compose 값이며 E2E_DB_* 환경변수로 바꿀 수 있다. 비밀번호는 쓰지 않는다.
 * - 정리는 이 헬퍼가 만든 계정의 정확한 id로만 수행한다(`--all`류 광범위 삭제 없음).
 */
import { test as base, expect, type APIRequestContext, type APIResponse } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomBytes, randomUUID } from "node:crypto";

export { expect };

export const API_BASE = process.env.E2E_API_URL ?? "http://localhost:8720/api/v1";
const DB_CONTAINER = process.env.E2E_DB_CONTAINER ?? "final-project-db";
const DB_USER = process.env.E2E_DB_USER ?? "final_app";
const DB_NAME = process.env.E2E_DB_NAME ?? "final_project";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const MARKER_EMAIL_RE = /^harness_test_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@harness-test\.example$/;

/** psql 한 번 호출. 여러 문장은 하나의 트랜잭션으로 실행된다(-c 단일 문자열). 결과는 행 배열(열 구분 `|`). */
export function sql(query: string): string[][] {
  const out = execFileSync(
    "docker",
    ["exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-v", "ON_ERROR_STOP=1", "-At", "-c", query],
    { encoding: "utf8" },
  );
  return out
    .split(/\r?\n/)
    .filter((line) => line.length > 0 && !/^(INSERT|UPDATE|DELETE|BEGIN|COMMIT)( \d+)*$/.test(line))
    .map((line) => line.split("|"));
}

function assertUuid(id: string): string {
  if (!UUID_RE.test(id)) throw new Error(`UUID 형식이 아닌 값은 SQL에 넣지 않는다: ${id}`);
  return id;
}

export interface Account {
  id: string;
  email: string;
  password: string;
  name: string;
  role: "candidate" | "recruiter";
  token: string;
}

export interface ListItem {
  id: string;
  status: string;
  report_status: string;
  started_at: string | null;
  ended_at: string | null;
  overall_score: string | null;
  created_at: string;
  resumable: boolean;
}

export const LIST_KEYS = ["created_at", "ended_at", "id", "overall_score", "report_status", "resumable", "started_at", "status"];

export function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export class AccountKit {
  readonly ids: string[] = [];
  constructor(private readonly request: APIRequestContext) {}

  async create(role: "candidate" | "recruiter", name = `u19 ${role}`): Promise<Account> {
    const email = `harness_test_${randomUUID()}@harness-test.example`;
    const password = `Pw-${randomBytes(12).toString("base64url")}`;
    const reg = await this.request.post(`${API_BASE}/auth/register`, { data: { email, password, name, role } });
    if (reg.status() !== 201) throw new Error(`register 실패 ${reg.status()} ${await reg.text()}`);
    const user = (await reg.json()) as { id: string };
    this.ids.push(user.id);
    const login = await this.request.post(`${API_BASE}/auth/login`, { data: { email, password } });
    if (login.status() !== 200) throw new Error(`login 실패 ${login.status()} ${await login.text()}`);
    const body = (await login.json()) as { access_token: string };
    return { id: user.id, email, password, name, role, token: body.access_token };
  }

  /** 정확한 id로만, FK 순서대로, 단일 트랜잭션 삭제 후 잔여 0건을 확인한다. */
  cleanup(): void {
    if (this.ids.length === 0) return;
    const list = this.ids.map((id) => `'${assertUuid(id)}'`).join(",");
    const own = `(select id from interviews where candidate_id in (${list}))`;
    sql(
      [
        `delete from transcripts where interview_id in ${own}`,
        `delete from code_submissions where interview_id in ${own}`,
        `delete from whiteboard_snapshots where interview_id in ${own}`,
        `delete from interviews where candidate_id in (${list})`,
        `delete from consents where user_id in (${list})`,
        `delete from deletion_requests where user_id in (${list})`,
        `delete from rubric_templates where recruiter_id in (${list})`,
        `delete from users where id in (${list})`,
      ].join("; "),
    );
    const left = sql(
      `select (select count(*) from users where id in (${list})), (select count(*) from interviews where candidate_id in (${list}) or recruiter_id in (${list}))`,
    );
    if (left[0].join("|") !== "0|0") throw new Error(`정리 후 잔여 데이터 있음: ${left[0].join("|")}`);
  }
}

export const test = base.extend<{ kit: AccountKit }>({
  kit: async ({ request }, runTest) => {
    const kit = new AccountKit(request);
    try {
      await runTest(kit);
    } finally {
      kit.cleanup();
    }
  },
});

export async function listInterviews(request: APIRequestContext, token: string, query = ""): Promise<APIResponse> {
  return request.get(`${API_BASE}/interviews${query}`, { headers: authHeader(token) });
}

export async function listBody(request: APIRequestContext, token: string): Promise<ListItem[]> {
  const res = await listInterviews(request, token);
  expect(res.status()).toBe(200);
  return (await res.json()) as ListItem[];
}

/** POST /interviews로 scheduled 세션 n개 생성, 생성 순서대로 id 반환. */
export async function createSessions(request: APIRequestContext, token: string, n: number): Promise<string[]> {
  const ids: string[] = [];
  for (let i = 0; i < n; i++) {
    const res = await request.post(`${API_BASE}/interviews`, { headers: authHeader(token) });
    expect(res.status()).toBe(201);
    ids.push(((await res.json()) as { id: string }).id);
  }
  return ids;
}

export interface SessionSpec {
  status: "scheduled" | "live" | "paused" | "completed" | "expired";
  report?: "none" | "queued" | "ready" | "failed";
  score?: string; // SQL numeric literal, e.g. "7.5"
  startedAgo?: string; // postgres interval, e.g. "1 hour"; 생략 시 started_at NULL 유지
  endedAgo?: string;
  startedAt?: string; // 절대 시각(timestamptz 리터럴). startedAgo보다 우선
}

/** 이미 만든 세션 id에 상태를 SQL로 부여한다(paused/ready/score를 만드는 운영 경로가 아직 없어서, unit-19-note §4). */
export function setSession(id: string, spec: SessionSpec): void {
  assertUuid(id);
  const sets = [`status='${spec.status}'`, `report_status='${spec.report ?? "none"}'`];
  sets.push(spec.score !== undefined ? `overall_score=${spec.score}` : "overall_score=null");
  if (spec.startedAt) sets.push(`started_at='${spec.startedAt}'::timestamptz`);
  else if (spec.startedAgo) sets.push(`started_at=now()-interval '${spec.startedAgo}'`);
  else sets.push("started_at=null");
  sets.push(spec.endedAgo ? `ended_at=now()-interval '${spec.endedAgo}'` : "ended_at=null");
  sql(`update interviews set ${sets.join(", ")} where id='${id}'`);
}

export function dbStatus(id: string): { status: string; report: string } {
  const r = sql(`select status, report_status from interviews where id='${assertUuid(id)}'`);
  return { status: r[0][0], report: r[0][1] };
}

export function countInterviews(candidateId: string): number {
  return Number(sql(`select count(*) from interviews where candidate_id='${assertUuid(candidateId)}'`)[0][0]);
}

/** 7개 상태 세션을 만들고 "기대 표시 순서"(COALESCE(started_at,created_at) 내림차순)대로 id 를 돌려준다. */
export interface SevenStates {
  scheduled: string;
  live1h: string;
  paused2h: string;
  queued3h: string;
  failed4h: string;
  live25h: string;
  ready30h: string;
  ordered: string[];
}

export async function seedSevenStates(request: APIRequestContext, token: string): Promise<SevenStates> {
  const ids = await createSessions(request, token, 7);
  const [scheduled, live1h, paused2h, queued3h, failed4h, live25h, ready30h] = ids;
  setSession(live1h, { status: "live", startedAgo: "1 hour" });
  setSession(paused2h, { status: "paused", startedAgo: "2 hours" });
  setSession(queued3h, { status: "completed", report: "queued", startedAgo: "3 hours", endedAgo: "2 hours 30 minutes" });
  setSession(failed4h, { status: "completed", report: "failed", startedAgo: "4 hours", endedAgo: "3 hours" });
  setSession(live25h, { status: "live", startedAgo: "25 hours" });
  setSession(ready30h, { status: "completed", report: "ready", score: "7.5", startedAgo: "30 hours", endedAgo: "29 hours" });
  return { scheduled, live1h, paused2h, queued3h, failed4h, live25h, ready30h, ordered: ids };
}

/** started_at 이 (i)분 전인 completed 세션 n개를 한 번의 SQL 로 대량 생성(홈의 10건 제한 검증용). */
export function bulkCompleted(candidateId: string, n: number, hoursAgoBase = 0): void {
  sql(
    `insert into interviews (id, candidate_id, status, report_status, overall_score, started_at, ended_at, created_at)
     select gen_random_uuid(), '${assertUuid(candidateId)}', 'completed', 'ready', 6.5,
            now() - interval '${hoursAgoBase} hours' - (g || ' minutes')::interval,
            now() - interval '${hoursAgoBase} hours' - (g || ' minutes')::interval + interval '20 seconds',
            now() - interval '${hoursAgoBase} hours' - (g || ' minutes')::interval
     from generate_series(1, ${Math.trunc(n)}) g`,
  );
}
