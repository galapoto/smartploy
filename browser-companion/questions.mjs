/* SmartPloy SP14: discover ONLY unfilled employer-specific text questions.
   Mirrors the ObumAI questionnaire/form-mapper decision: unknown and
   consequential answers remain unfilled until a human explicitly reviews them.
   No model, storage, network access, account inference or submission here. */
import { identifyField } from "./logic.mjs";

export class QuestionError extends Error {}
export const MAX_QUESTION_ANSWER = 1500;
export const MAX_QUESTION_ITEMS = 12;

// Deny-list is intentionally broader than auto-fill support. Questions about
// citizenship, protected traits, legal attestations, salary and authorization
// remain manual even if a user has typed a possible answer.
export const SENSITIVE_QUESTION =
  /\b(?:visa|citizenship|citizen|nationality|sponsor|sponsorship|work permit|right to work|work authori[sz]ation|salary|compensation|wage|expected pay|pay range|eeo|race|ethnic|gender|sex|sexual|religion|politic|union membership|disability|health condition|medical|veteran|military|criminal|felony|convict|background check|privacy|consent|gdpr|agree|agreement|attest|certif(?:y|ication)|signature|passport|social security|government id|tax id|birth date|date of birth|age|bank account|start date|notice period|työlupa|oleskelulupa|kansalaisuus|palkka|henkilötunnus|sukupuoli|uskonto|rikosrekisteri|suostumus|allekirjoitus|arbetstillstånd|medborgarskap|personnummer|samtycke|underskrift|lön|födelsetid|kön)\b/iu;

function tidy(value) {
  return String(value || "").normalize("NFKC").toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim().replace(/\s+/g, " ");
}

export function isSensitiveQuestion(row) {
  const material = tidy([row?.label, row?.name, row?.id, row?.placeholder].join(" "));
  return SENSITIVE_QUESTION.test(material);
}

export function planReviewedQuestions(elements) {
  if (!Array.isArray(elements) || elements.length > 250) {
    throw new QuestionError("The employer form contains too many fields for safe review.");
  }
  const questions = [];
  const humanOnly = [];
  const labels = new Set();
  const repeated = new Set();
  const possible = [];
  for (const row of elements) {
    if (!row || !row.required || row.hasValue || row.disabled ||
        row.readonly || !row.visible) continue;
    if (identifyField(row)) continue; // handled by existing exact approved-fact mapping
    const label = String(row.label || "").trim();
    if (!label || label.length > 150) {
      humanOnly.push("Unlabeled or invalid required question");
      continue;
    }
    if (!["text", "textarea"].includes(row.type) || isSensitiveQuestion(row)) {
      humanOnly.push(label); // no auto-select, radio, checkbox or legal/EEO answers
      continue;
    }
    if (!Number.isInteger(row.index) || row.index < 0 || row.index >= 250) {
      humanOnly.push(label);
      continue;
    }
    const limit = Number.isInteger(row.maxLength) && row.maxLength > 0
      ? Math.min(MAX_QUESTION_ANSWER, row.maxLength) : MAX_QUESTION_ANSWER;
    if (limit < 2) { humanOnly.push(label); continue; }
    const key = tidy(label);
    if (labels.has(key)) repeated.add(key);
    labels.add(key);
    possible.push({
      index: row.index, label, type: row.type,
      expected_id: String(row.id || ""), expected_name: String(row.name || ""),
      expected_placeholder: String(row.placeholder || ""),
      expected_max_length: row.maxLength ?? -1,
      max_answer_length: limit
    });
  }
  for (const item of possible) {
    if (repeated.has(tidy(item.label))) humanOnly.push(item.label);
    else questions.push(item);
  }
  if (questions.length > MAX_QUESTION_ITEMS) {
    throw new QuestionError("Too many unanswered text questions. Finish this form manually.");
  }
  return { questions, humanOnly, requiresManualReview: humanOnly.length > 0 };
}

export function validateReviewedAnswers(plan, values) {
  if (!plan || !Array.isArray(plan.questions) ||
      !Array.isArray(values) || values.length !== plan.questions.length ||
      values.length > MAX_QUESTION_ITEMS) {
    throw new QuestionError("The reviewed question plan is no longer valid.");
  }
  const actions = [];
  for (let i = 0; i < values.length; i++) {
    const question = plan.questions[i];
    const value = values[i];
    if (typeof value !== "string" ||
        value.length > MAX_QUESTION_ANSWER ||
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value) ||
        value.length > question.max_answer_length) {
      throw new QuestionError("A reviewed answer is invalid or too long.");
    }
    if (!value.trim()) continue;
    if (isSensitiveQuestion(question)) {
      throw new QuestionError("A sensitive question must be answered manually.");
    }
    actions.push({
      ...question, value: value.trim()
    });
  }
  if (!actions.length) {
    throw new QuestionError("Type at least one reviewed answer or finish the questions manually.");
  }
  return actions;
}
