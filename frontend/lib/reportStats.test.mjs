import assert from "node:assert/strict";
import { test } from "node:test";

import { countByStatus, scoreHistogram } from "./reportStats.ts";

const L = { scheduled: "예정", live: "진행 중", paused: "일시중지", completed: "완료", expired: "만료" };

test("상태 분포: 모든 상태가 순서대로 나오고 0건도 포함", () => {
  const r = countByStatus([{ status: "completed", overall_score: "4.0" }, { status: "completed", overall_score: null }, { status: "live", overall_score: null }], L);
  assert.deepEqual(r.map((x) => [x.key, x.count]), [["scheduled", 0], ["live", 1], ["paused", 0], ["completed", 2], ["expired", 0]]);
  assert.equal(r[3].label, "완료");
});

test("상태 분포: 알 수 없는 새 상태도 누락 없이 덧붙음", () => {
  const r = countByStatus([{ status: "archived", overall_score: null }], L);
  assert.deepEqual(r[r.length - 1], { key: "archived", label: "archived", count: 1 });
});

test("점수 분포: 경계값(1, 2, 3, 4, 5)과 소수", () => {
  const items = ["1", "1.99", "2", "2.5", "3", "3.99", "4", "4.5", "5"].map((s) => ({ status: "completed", overall_score: s }));
  const r = scoreHistogram(items);
  assert.deepEqual(r.bins.map((b) => b.count), [2, 2, 2, 3]); // 5점은 마지막 구간에 포함
  assert.equal(r.scored, 9);
  assert.equal(r.unscored, 0);
});

test("점수 분포: null·범위 밖·숫자 아님은 미산출로 센다", () => {
  const items = [null, "0.5", "5.1", "abc", "", "3.0"].map((s) => ({ status: "completed", overall_score: s }));
  const r = scoreHistogram(items);
  assert.equal(r.scored, 1);
  assert.equal(r.unscored, 5);
  assert.equal(r.bins[2].count, 1);
});

test("빈 목록", () => {
  const r = scoreHistogram([]);
  assert.equal(r.scored, 0);
  assert.equal(r.unscored, 0);
  assert.deepEqual(countByStatus([], L).map((x) => x.count), [0, 0, 0, 0, 0]);
});
