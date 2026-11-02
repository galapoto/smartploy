import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPendingQuestionSync, clearPendingQuestions, getPendingQuestions,
  queuePendingQuestions, validatePendingQuestionSync,
  PENDING_QUESTION_SYNC_KEY, PENDING_QUESTION_SYNC_MS,
} from "../question-sync.mjs";
import { QuestionError } from "../questions.mjs";

const now = Date.now();
const packet = Object.freeze({
  workspace_id: "kit-" + "a".repeat(30), revision: 3,
  document_sha256: "b".repeat(64), cv_pdf_sha256: "c".repeat(64),
  cv_pdf_size: 12000, expires_at: new Date(now + 10 * 60_000).toISOString(),
  fields: {
    full_name: "Do not persist private name",
    cover_letter: "Never persist a private cover letter",
  },
  application_url: "https://jobs.ashbyhq.com/example/job/application",
});
const digests = Object.freeze({ fields: "d".repeat(64), url: "e".repeat(64) });
const questions = [{
  label: "Which programming languages have you worked with?",
  expected_id: "languages", expected_name: "languages", expected_placeholder: "",
  type: "textarea", value: "PRIVATE ANSWER NEVER SAVE",
}];
function storage() {
  const map = new Map();
  return {
    map,
    async get(key) { return { [key]: map.get(key) }; },
    async set(values) { for (const [k,v] of Object.entries(values)) map.set(k,v); },
    async remove(key) { map.delete(key); },
  };
}

test("temporary queue retains only safe question prompts, never answers, CV, URL or bearer", async () => {
  const store = storage();
  const batch = buildPendingQuestionSync(packet, questions, digests, now);
  assert.equal(batch.questions.length, 1);
  assert.deepEqual(Object.keys(batch.questions[0]).sort(), [
    "expected_id", "expected_name", "expected_placeholder", "label",
  ]);
  const serialized = JSON.stringify(batch);
  for (const forbidden of [
    "PRIVATE ANSWER", "Never persist", "Do not persist", "jobs.ashbyhq",
    "https://", "bearer_token", "session_cookie",
  ]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
  await queuePendingQuestions(store, batch);
  assert.deepEqual(await getPendingQuestions(store), batch);
  assert.deepEqual([...store.map.keys()], [PENDING_QUESTION_SYNC_KEY]);
  await clearPendingQuestions(store);
  assert.equal(await getPendingQuestions(store), null);
});

test("temporary queue expires and corrupt data is removed without retry or persistence", async () => {
  const store = storage();
  const batch = buildPendingQuestionSync(packet, questions, digests, now);
  store.map.set(PENDING_QUESTION_SYNC_KEY, batch);
  assert.equal(await getPendingQuestions(store, batch.expires_at + 1), null);
  assert.equal(store.map.size, 0);
  store.map.set(PENDING_QUESTION_SYNC_KEY, { ...batch, answers: ["leak"] });
  assert.equal(await getPendingQuestions(store, now), null);
  assert.equal(store.map.size, 0);
  assert.throws(() => validatePendingQuestionSync({
    ...batch, expires_at: now + PENDING_QUESTION_SYNC_MS + 60_000,
  }, now), QuestionError);
});

test("sensitive identifiers, duplicate labels, excessive questions and stale packets are blocked", () => {
  for (const unsafe of [
    { ...questions[0], label: "What is your visa status?" },
    { ...questions[0], expected_name: "salaryExpectation" },
    { ...questions[0], expected_id: "gdprConsent" },
    { ...questions[0], label: "Your bank account?" },
    { ...questions[0], label: "Verify person@example.invalid" },
    { ...questions[0], expected_placeholder: "https://example.invalid" },
  ]) {
    assert.throws(() => buildPendingQuestionSync(packet, [unsafe], digests, now), QuestionError);
  }
  const valid = buildPendingQuestionSync(packet, questions, digests, now);
  assert.throws(() => validatePendingQuestionSync({
    ...valid, questions: [valid.questions[0], valid.questions[0]],
  }, now), QuestionError);
  assert.throws(() => buildPendingQuestionSync(
    packet, Array.from({length:13},(_,i)=>({
      ...questions[0], label: "Ordinary question " + i,
    })), digests, now,
  ), QuestionError);
  assert.throws(() => buildPendingQuestionSync({
    ...packet, expires_at: new Date(now - 1).toISOString(),
  }, questions, digests, now), QuestionError);
  assert.throws(() => buildPendingQuestionSync(packet, questions, {
    fields: "not-a-digest", url: "e".repeat(64),
  }, now), QuestionError);
});

test("disabled temporary storage cannot silently claim profile sync", async () => {
  const batch = buildPendingQuestionSync(packet, questions, digests, now);
  await assert.rejects(queuePendingQuestions({}, batch), QuestionError);
  await assert.rejects(getPendingQuestions(null), QuestionError);
  await assert.rejects(clearPendingQuestions({}), QuestionError);
});
