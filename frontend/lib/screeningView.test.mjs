import assert from "node:assert/strict";
import { test } from "node:test";

import { aiBadge, formatScore, isDirty, validateCriteriaInput } from "./screeningView.mjs";

test("배지: 완료 합격/불합격", () => {
  assert.deepEqual(aiBadge("done", "pass"), { label: "AI 합격", tone: "pass" });
  assert.deepEqual(aiBadge("done", "fail"), { label: "AI 불합격", tone: "fail" });
});

test("배지: 대기/실패/미등록/알수없음", () => {
  assert.equal(aiBadge("pending", null).tone, "pending");
  assert.equal(aiBadge("failed", null).label, "분석 실패");
  assert.equal(aiBadge("no_criteria", null).label, "기준 미등록");
  assert.equal(aiBadge(undefined, undefined).tone, "none");
});

test("배지: 대기 중 이전 결과 표시", () => {
  const b = aiBadge("pending", "pass");
  assert.equal(b.tone, "pending");
  assert.match(b.label, /이전/);
  assert.equal(aiBadge("done", "fail", true).tone, "pending");
});

test("점수 표시", () => {
  assert.equal(formatScore(78), "78점");
  assert.equal(formatScore(77.6), "78점");
  assert.equal(formatScore(null), "-");
  assert.equal(formatScore(undefined), "-");
  assert.equal(formatScore(NaN), "-");
});

test("입력 검증: 정상", () => {
  assert.equal(validateCriteriaInput({ text: "필수: Java", threshold: 70 }).ok, true);
  assert.equal(validateCriteriaInput({ text: "x", threshold: "1" }).ok, true);
  assert.equal(validateCriteriaInput({ text: "x".repeat(4000), threshold: 100 }).ok, true);
});

test("입력 검증: 빈 문자열/공백/길이 초과", () => {
  assert.equal(validateCriteriaInput({ text: "   \n", threshold: 70 }).ok, false);
  assert.equal(validateCriteriaInput({ text: "x".repeat(4001), threshold: 70 }).ok, false);
});

test("입력 검증: 합격선 범위/정수", () => {
  for (const t of [0, 101, 70.5, "", "abc", NaN]) {
    assert.equal(validateCriteriaInput({ text: "x", threshold: t }).ok, false, String(t));
  }
});

test("변경 여부", () => {
  const saved = { text: "abc", threshold: 70 };
  assert.equal(isDirty(saved, { text: "abc  ", threshold: "70" }), false);
  assert.equal(isDirty(saved, { text: "abcd", threshold: 70 }), true);
  assert.equal(isDirty(saved, { text: "abc", threshold: 80 }), true);
});
