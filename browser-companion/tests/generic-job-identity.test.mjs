import test from "node:test";
import assert from "node:assert/strict";
import { fillReviewedAnswers } from "../page-questions.mjs";
import { attachReviewedPdf } from "../page-attachment.mjs";

// Test the original injected functions, not a replica of their URL guards.
// No website connection, applicant data or upload occurs in this test.
const approved = "https://careers.example.org/jobs/junior-analyst";

async function withEmployerTab(url, work) {
  const previous = {
    location: globalThis.location,
    window: globalThis.window,
    document: globalThis.document,
  };
  const top = {};
  globalThis.location = { href: url };
  globalThis.window = { top, self: top };
  globalThis.document = { querySelectorAll() { return []; } };
  try { return await work(); }
  finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
}

test("V4 injected fill and PDF attachment refuse another job on same employer host", async () => {
  for (const wrong of [
    "https://careers.example.org/jobs/other-analyst",
    "https://careers.example.org/apply?job=junior-analyst",
    approved + "/apply?job=other",
    "https://careers.example.org/jobs/junior-analyst-2/apply",
  ]) {
    await withEmployerTab(wrong, async () => {
      const answer = fillReviewedAnswers([{index:0}], approved, wrong);
      assert.equal(answer.status, "blocked", wrong);
      assert.equal(answer.reason, "The employer or application form changed.", wrong);
      const attachment = await attachReviewedPdf({
        application_url: approved, inspected_url: wrong,
      });
      assert.equal(attachment.status, "blocked", wrong);
      assert.equal(attachment.reason, "The employer job/form changed; reinspect before attaching.", wrong);
    });
  }
});

test("V4 bounded same-job application stages reach ordinary action checks", async () => {
  for (const expected of [
    approved, approved + "/apply", approved + "/application/step-2",
  ]) {
    await withEmployerTab(expected, async () => {
      const answer = fillReviewedAnswers([{index:0}], approved, expected);
      assert.equal(answer.reason, "At least one reviewed question changed; nothing was filled.");
      const attachment = await attachReviewedPdf({
        application_url: approved, inspected_url: expected,
      });
      assert.equal(attachment.reason, "The approved PDF or upload field identity is invalid.");
    });
  }
});
