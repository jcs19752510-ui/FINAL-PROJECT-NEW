import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CRITERIA_MAX_LENGTH,
  DEFAULT_CRITERIA_TEMPLATE,
  aiBadge,
  describeCriteriaLoadError,
  formatScore,
  formatThreshold,
  isDirty,
  validateCriteriaInput,
} from "./screeningView.mjs";

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

test("기본 예시: 4000자 이하이고 검증을 통과한다", () => {
  assert.ok(DEFAULT_CRITERIA_TEMPLATE.length > 500);
  assert.ok(DEFAULT_CRITERIA_TEMPLATE.length <= CRITERIA_MAX_LENGTH);
  assert.deepEqual(validateCriteriaInput({ text: DEFAULT_CRITERIA_TEMPLATE, threshold: 70 }), { ok: true });
});

test("기본 예시: 경력 5년·바이브코딩·2026년 10월·필수 조건·배점 합계 100", () => {
  const t = DEFAULT_CRITERIA_TEMPLATE;
  for (const word of ["5년 이상", "바이브코딩", "2026년 10월", "[필수 조건]", "[감점 요인]", "RAG", "Claude Code"]) {
    assert.ok(t.includes(word), `${word} 누락`);
  }
  const points = [...t.matchAll(/^\d+\. .*\((\d+)점\)$/gm)].map((m) => Number(m[1]));
  assert.equal(points.length, 6);
  assert.equal(points.reduce((a, b) => a + b, 0), 100);
});

test("기본 예시: 저장본이 비어 있으면 변경됨으로 판단해 등록할 수 있다", () => {
  assert.equal(isDirty({ text: "", threshold: 70 }, { text: DEFAULT_CRITERIA_TEMPLATE, threshold: "70" }), true);
});

test("불러오기 실패 안내: 404는 서버 재시작을 안내한다", () => {
  assert.match(describeCriteriaLoadError(404, "Not Found"), /재시작/);
  assert.match(describeCriteriaLoadError(undefined, undefined), /8001/);
  assert.match(describeCriteriaLoadError(403, "x"), /채용담당자/);
  assert.equal(describeCriteriaLoadError(500, "서버 오류"), "서버 오류");
  assert.equal(describeCriteriaLoadError(500, ""), "면접기준을 불러오지 못했어요.");
});

test("합격선 표시: 값이 있으면 N점, 없으면 -", () => {
  assert.equal(formatThreshold(70), "70점");
  assert.equal(formatThreshold(65.4), "65점");
  assert.equal(formatThreshold(null), "-");
  assert.equal(formatThreshold(undefined), "-");
  assert.equal(formatThreshold(Number.NaN), "-");
});
