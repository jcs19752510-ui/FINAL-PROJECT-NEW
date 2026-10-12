import assert from "node:assert/strict";
import { test } from "node:test";

import {
  complexityText,
  confidenceLabel,
  formatCommentRatio,
  formatPassCount,
  formatPassRate,
  scoreToGrade,
  topViolations,
} from "./codeAnalysisView.ts";

test("통과율: 0/1 경계와 소수 한 자리", () => {
  assert.equal(formatPassRate(0), "0%");
  assert.equal(formatPassRate(1), "100%");
  assert.equal(formatPassRate(0.5), "50%");
  assert.equal(formatPassRate(2 / 3), "66.7%");
});

test("통과율: 범위 밖·NaN 은 보정", () => {
  assert.equal(formatPassRate(-0.2), "0%");
  assert.equal(formatPassRate(1.5), "100%");
  assert.equal(formatPassRate(Number.NaN), "0%");
});

test("통과 건수: 전체 0건이면 안내 문구", () => {
  assert.equal(formatPassCount(2, 3), "통과 2/3");
  assert.equal(formatPassCount(0, 3), "통과 0/3");
  assert.equal(formatPassCount(0, 0), "실행된 테스트 없음");
});

test("점수→등급: 경계값 90/80/70/60", () => {
  const cases = [[100, "A"], [90, "A"], [89.9, "B"], [80, "B"], [79, "C"], [70, "C"], [69, "D"], [60, "D"], [59.9, "F"], [0, "F"]];
  for (const [s, g] of cases) assert.equal(scoreToGrade(s), g, `score ${s}`);
});

test("점수→등급: 범위 밖·NaN", () => {
  assert.equal(scoreToGrade(150), "A");
  assert.equal(scoreToGrade(-5), "F");
  assert.equal(scoreToGrade(Number.NaN), "-");
});

test("복잡도 문구: 신뢰도 라벨·빈 추정값·미지의 신뢰도", () => {
  assert.equal(complexityText("O(n)", "low"), "추정 O(n) · 신뢰도 낮음");
  assert.equal(complexityText(" O(n log n) ", "medium"), "추정 O(n log n) · 신뢰도 보통");
  assert.equal(complexityText("  ", "low"), "판단 불가 · 신뢰도 낮음");
  assert.equal(confidenceLabel("high"), "high");
});

test("주석 비율 포맷", () => {
  assert.equal(formatCommentRatio(0.125), "12.5%");
  assert.equal(formatCommentRatio(0), "0%");
});

test("위반 상위 N건: 줄 번호 정렬, 나머지 건수, 원본 불변", () => {
  const items = [7, 3, 9, 1, 5, 2, 8].map((line) => ({ line }));
  const r = topViolations(items);
  assert.deepEqual(r.shown.map((x) => x.line), [1, 2, 3, 5, 7]);
  assert.equal(r.hidden, 2);
  assert.equal(items[0].line, 7);
  assert.deepEqual(topViolations(items.slice(0, 2)), { shown: [{ line: 3 }, { line: 7 }], hidden: 0 });
  assert.deepEqual(topViolations(items, 0), { shown: [], hidden: 7 });
});
