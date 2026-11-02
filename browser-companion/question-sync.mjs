/* SP117: short-lived, private, reviewed question handoff between employer
 * tab and the user's signed-in SmartPloy tab. The extension cannot access
 * SmartPloy's OIDC cookie, and never stores an applicant's answers, CV,
 * contact fields, employer URL, or a bearer credential.
 *
 * Only the already-approved Chrome question classifier may provide prompts.
 * Every prompt is validated again by the owner-private server on import.
 */
import { QuestionError, isSensitiveQuestion, MAX_QUESTION_ITEMS } from "./questions.mjs";

export const PENDING_QUESTION_SYNC_KEY = "smartploy.pending_questions.v1";
export const PENDING_QUESTION_SYNC_MS = 5 * 60 * 1000;
const HEX64 = /^[a-f0-9]{64}$/;
const WORKSPACE = /^kit-[a-f0-9]{30}$/;
const PRIVATE_VALUE = /https?:\/\/|\b\S+@\S+\.\S+/i;
const ALLOWED_KEYS = [
  "schema", "workspace_id", "expected_revision",
  "expected_document_sha256", "expected_cv_pdf_sha256",
  "expected_fields_sha256", "expected_application_url_sha256",
  "expected_cv_pdf_size", "questions", "expires_at",
];

function checkedQuestion(row) {
  if (!row || typeof row !== "object" ||
      typeof row.label !== "string" || row.label.trim().length < 3 ||
      row.label.length > 150 || /[\x00-\x1f\x7f]/.test(row.label) ||
      PRIVATE_VALUE.test(row.label) ||
      isSensitiveQuestion({
        label: row.label, id: row.expected_id,
        name: row.expected_name, placeholder: row.expected_placeholder,
      })) {
    throw new QuestionError("A protected or invalid question cannot be queued.");
  }
  const answerFree = { label: row.label.trim() };
  for (const key of ["expected_id", "expected_name", "expected_placeholder"]) {
    const value = row[key] || "";
    if (typeof value !== "string" || value.length > 150 ||
        /[\x00-\x1f\x7f]/.test(value) || PRIVATE_VALUE.test(value)) {
      throw new QuestionError("Invalid employer field identifier.");
    }
    answerFree[key] = value;
  }
  return answerFree;
}

export function validatePendingQuestionSync(batch, now = Date.now()) {
  if (!batch || typeof batch !== "object" ||
      Object.keys(batch).sort().join("|") !== [...ALLOWED_KEYS].sort().join("|") ||
      batch.schema !== "smartploy.pending_questions.v1" ||
      !WORKSPACE.test(batch.workspace_id || "") ||
      !Number.isInteger(batch.expected_revision) || batch.expected_revision < 1 ||
      !HEX64.test(batch.expected_document_sha256 || "") ||
      !HEX64.test(batch.expected_cv_pdf_sha256 || "") ||
      !HEX64.test(batch.expected_fields_sha256 || "") ||
      !HEX64.test(batch.expected_application_url_sha256 || "") ||
      !Number.isInteger(batch.expected_cv_pdf_size) ||
      batch.expected_cv_pdf_size < 12 || batch.expected_cv_pdf_size > 2 * 1024 * 1024 ||
      !Number.isFinite(batch.expires_at) || batch.expires_at <= now ||
      batch.expires_at > now + PENDING_QUESTION_SYNC_MS ||
      !Array.isArray(batch.questions) || batch.questions.length < 1 ||
      batch.questions.length > MAX_QUESTION_ITEMS) {
    throw new QuestionError("Pending question handoff is invalid or expired.");
  }
  const unique = new Set();
  for (const row of batch.questions) {
    const valid = checkedQuestion(row);
    if (Object.keys(row).sort().join("|") !== Object.keys(valid).sort().join("|")) {
      throw new QuestionError("Question handoff contains extra private fields.");
    }
    const key = valid.label.normalize("NFKC").trim().toLowerCase();
    if (unique.has(key)) throw new QuestionError("Duplicate question in handoff.");
    unique.add(key);
  }
  return batch;
}

export function buildPendingQuestionSync(packet, questions, digests, now = Date.now()) {
  if (!packet || !Array.isArray(questions) || questions.length < 1 ||
      questions.length > MAX_QUESTION_ITEMS) {
    throw new QuestionError("No safely reviewed employer questions to remember.");
  }
  const expiry = Math.min(Date.parse(packet.expires_at), now + PENDING_QUESTION_SYNC_MS);
  const batch = {
    schema: "smartploy.pending_questions.v1",
    workspace_id: packet.workspace_id,
    expected_revision: packet.revision,
    expected_document_sha256: packet.document_sha256,
    expected_cv_pdf_sha256: packet.cv_pdf_sha256,
    expected_fields_sha256: digests?.fields,
    expected_application_url_sha256: digests?.url,
    expected_cv_pdf_size: packet.cv_pdf_size,
    questions: questions.map(checkedQuestion),
    expires_at: expiry,
  };
  return validatePendingQuestionSync(batch, now);
}

function checkedStorage(storage) {
  if (!storage || typeof storage.get !== "function" ||
      typeof storage.set !== "function" || typeof storage.remove !== "function") {
    throw new QuestionError("Private temporary browser session storage is unavailable.");
  }
  return storage;
}

export async function queuePendingQuestions(storage, batch) {
  checkedStorage(storage);
  validatePendingQuestionSync(batch);
  await storage.set({ [PENDING_QUESTION_SYNC_KEY]: batch });
  return true;
}

export async function getPendingQuestions(storage, now = Date.now()) {
  checkedStorage(storage);
  const value = (await storage.get(PENDING_QUESTION_SYNC_KEY))[PENDING_QUESTION_SYNC_KEY];
  if (!value) return null;
  try {
    return validatePendingQuestionSync(value, now);
  } catch {
    await storage.remove(PENDING_QUESTION_SYNC_KEY);
    return null;
  }
}

export async function clearPendingQuestions(storage) {
  await checkedStorage(storage).remove(PENDING_QUESTION_SYNC_KEY);
}
