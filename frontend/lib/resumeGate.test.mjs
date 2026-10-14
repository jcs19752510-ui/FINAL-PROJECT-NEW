import assert from "node:assert/strict";
import { test } from "node:test";

import {
  APPLY_PATH,
  RESUME_REQUIRED_MESSAGE,
  RESUME_UNREADABLE_MESSAGE,
  isResumeRequiredError,
  profileStatusWarning,
  resumeRequiredNotice,
} from "./resumeGate.mjs";

test("RESUME_REQUIRED 코드만 인식", () => {
  assert.equal(isResumeRequiredError({ status: 409, code: "RESUME_REQUIRED" }), true);
  assert.equal(isResumeRequiredError({ status: 409, code: "OTHER" }), false);
  assert.equal(isResumeRequiredError(null), false);
  assert.equal(isResumeRequiredError(new Error("x")), false);
});

test("안내 박스: 문구와 /apply 링크", () => {
  const n = resumeRequiredNotice({ code: "RESUME_REQUIRED" });
  assert.equal(n.message, RESUME_REQUIRED_MESSAGE);
  assert.equal(n.href, APPLY_PATH);
  assert.equal(resumeRequiredNotice({ code: "X" }), null);
});

test("profile_status unreadable만 경고", () => {
  assert.equal(profileStatusWarning({ profile_status: "unreadable" }), RESUME_UNREADABLE_MESSAGE);
  assert.equal(profileStatusWarning({ profile_status: "ready" }), null);
  assert.equal(profileStatusWarning({ profile_status: "pending" }), null);
  assert.equal(profileStatusWarning({}), null);
  assert.equal(profileStatusWarning(null), null);
});
