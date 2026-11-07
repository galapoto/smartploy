import test from "node:test";
import assert from "node:assert/strict";
import { fillReviewedAnswers } from "../page-questions.mjs";

// Synthetic owned DOM. No real employer data, browser permission or network.
const JOB = "https://careers.example.org/jobs/junior-analyst";
const LABEL = "Why are you interested in this role?";
const ANSWER = "I have relevant experience in Python and SQL.";

async function exercise(reaction) {
  const names = [
    "location", "document", "window", "getComputedStyle",
    "HTMLInputElement", "Event"
  ];
  const saved = Object.fromEntries(names.map(name => [name, globalThis[name]]));
  let submitEvents = 0;
  class MockInput {
    constructor() {
      this.tagName = "INPUT";
      this.type = "text";
      this.id = "why_role";
      this.name = "why_role";
      this.labels = [{ innerText: LABEL }];
      this.maxLength = 1500;
      this.required = true;
      this.disabled = false;
      this.readOnly = false;
      this.isConnected = true;
      this.value = "";
    }
    getAttribute(name) { return name === "placeholder" ? "" : null; }
    closest(selector) { return selector === "form" ? {} : null; }
    getClientRects() { return [1]; }
    dispatchEvent(event) {
      if (event.type === "submit") submitEvents++;
      if (event.type === "input") {
        if (reaction === "clear") setTimeout(() => { this.value = ""; }, 10);
        if (reaction === "rerender") setTimeout(() => { this.isConnected = false; }, 10);
      }
      return true;
    }
  }
  const field = new MockInput();
  const frame = {};
  globalThis.location = { href: JOB };
  globalThis.window = { top: frame, self: frame };
  globalThis.document = {
    querySelectorAll(selector) {
      assert.equal(selector, "input,textarea,select");
      return [field];
    },
    querySelector() { return null; },
  };
  globalThis.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  globalThis.HTMLInputElement = MockInput;
  const action = {
    index: 0, type: "text", label: LABEL,
    expected_id: "why_role", expected_name: "why_role",
    expected_placeholder: "", expected_max_length: 1500,
    value: ANSWER
  };
  try {
    const result = await fillReviewedAnswers([action], JOB, JOB);
    return { result, liveValue: field.value, submitEvents };
  } finally {
    for (const name of names) {
      if (saved[name] === undefined) delete globalThis[name];
      else globalThis[name] = saved[name];
    }
  }
}

test("V4 an employer answer counts only after a stable re-read", async () => {
  const kept = await exercise("keep");
  assert.equal(kept.result.status, "filled_for_review");
  assert.equal(kept.result.filled, 1);
  assert.equal(kept.liveValue, ANSWER);
  assert.equal(kept.submitEvents, 0);

  const cleared = await exercise("clear");
  assert.equal(cleared.result.status, "blocked");
  assert.equal(cleared.result.filled, 0);
  assert.match(cleared.result.reason, /did not retain/i);
  assert.equal(cleared.submitEvents, 0);

  const replaced = await exercise("rerender");
  assert.equal(replaced.result.status, "blocked");
  assert.equal(replaced.result.filled, 0);
  assert.match(replaced.result.reason, /rerendered/i);
  assert.equal(replaced.submitEvents, 0);
});
