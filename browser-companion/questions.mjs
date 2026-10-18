/* SP14: only applicant-typed, ephemeral answers for two low-risk Lever questions.
   Reuses SmartPloy's reviewed packet and ObumAI's conservative field-policy
   decisions, rather than adding another CV/answer database or model. No network. */

export class QuestionError extends Error {}

const PLAIN_TYPES = new Set(["text", "textarea"]);
const SOURCE_LABEL = /^(?:(?:how|where) did you (?:hear|learn|find out) about (?:us|this (?:job|role|position|opportunity))\??|how did you find (?:us|this (?:job|role|position))\??|mistä kuulit (?:meistä|tästä (?:työpaikasta|tehtävästä))\??|hur hörde du talas om (?:oss|den här tjänsten)\??)$/i;
const MOTIVATION_LABEL = /^(?:why (?:are you interested in|do you want to apply for) this (?:job|role|position|opportunity)\??|what interests you about this (?:job|role|position)\??|why would you like to join (?:our team|us)\??|miksi olet kiinnostunut tästä tehtävästä\??|varför är du intresserad av den här tjänsten\??)$/i;
const RESTRICTED = /(?:\b(?:visa|sponsor(?:ship)?|immigration|work\s+authori[sz]ation|work\s+permit|salary|compensation|wage|criminal|background\s+check|gender|sex|sexual|race|ethnic|religion|disability|veteran|birth|age|date\s+of\s+birth|passport|nationality|citizen(?:ship)?|bank|social\s+security|ssn|privacy|terms|consent|agree|accept|attest|signature|certify|captcha|recaptcha|mfa|password)\b|palkka|oleskelulup|työlup|kansalaisuu|sukupuol|uskont|syntym|ikäsi|henkilötunnus|suostum|tietosuoj|löneanspråk|arbetstillstånd|medborgarskap|samtycke|personnummer)/i;
const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;

function normal(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function validLabel(raw) {
  return typeof raw === "string" && raw.length > 0 &&
    raw.length <= 150 && !CONTROL.test(raw);
}

function kindFor(label) {
  const labelText = normal(label);
  if (SOURCE_LABEL.test(labelText)) return "source";
  if (MOTIVATION_LABEL.test(labelText)) return "motivation";
  return null;
}

export function classifySupplementalQuestion(row) {
  if (!row || !Number.isInteger(row.index) || row.index < 0 || row.index >= 250 ||
      !PLAIN_TYPES.has(row.type) || !row.visible || row.disabled || row.readonly ||
      row.hasValue || !validLabel(row.label) ||
      String(row.name || "").length > 150 ||
      String(row.id || "").length > 150 ||
      String(row.placeholder || "").length > 150) return null;
  const descriptor = [row.label, row.name, row.id, row.placeholder].join(" ");
  if (RESTRICTED.test(descriptor)) return null;
  const kind = kindFor(row.label);
  if (!kind) return null;
  const maximum = kind === "source" ? 180 : 1200;
  const limit = Number.isInteger(row.maxLength) && row.maxLength > 0 ?
    Math.min(maximum, row.maxLength) : maximum;
  if (limit < 2) return null;
  return {
    index: row.index,
    kind,
    label: row.label,
    expected_id: String(row.id || ""),
    expected_name: String(row.name || ""),
    expected_type: row.type,
    maxLength: limit,
    required: row.required === true
  };
}

export function planSupplementalQuestions(elements) {
  if (!Array.isArray(elements) || elements.length > 250) {
    throw new QuestionError("Too many employer fields to inspect safely.");
  }
  const potential = elements.map(classifySupplementalQuestion).filter(Boolean);
  // A duplicated question intent is ambiguous, including when the labels differ.
  const counts = new Map();
  for (const row of potential) counts.set(row.kind, (counts.get(row.kind) || 0) + 1);
  return potential.filter(row => counts.get(row.kind) === 1);
}

export function buildOwnerQuestionActions(questions, answers) {
  if (!Array.isArray(questions) || questions.length > 2 ||
      !Array.isArray(answers) || answers.length !== questions.length) {
    throw new QuestionError("Reinspect the employer questions before answering.");
  }
  const seen = new Set();
  const actions = [];
  for (let i = 0; i < questions.length; i++) {
    const row = questions[i], answer = answers[i];
    if (!row || !Number.isInteger(row.index) || row.index < 0 || row.index >= 250 ||
        !["source", "motivation"].includes(row.kind) ||
        seen.has(row.kind) || kindFor(row.label) !== row.kind ||
        RESTRICTED.test([row.label, row.expected_id, row.expected_name].join(" ")) ||
        !PLAIN_TYPES.has(row.expected_type) || !Number.isInteger(row.maxLength) ||
        row.maxLength < 2 || row.maxLength > (row.kind === "source" ? 180 : 1200)) {
      throw new QuestionError("This supplemental field is no longer approved.");
    }
    seen.add(row.kind);
    if (typeof answer !== "string" || CONTROL.test(answer)) {
      throw new QuestionError("Enter only ordinary reviewed text.");
    }
    const value = answer.trim();
    if (!value) continue; // Unknown / sensitive answers remain for the employer form.
    if (value.length > row.maxLength) {
      throw new QuestionError("One reviewed answer exceeds the employer field limit.");
    }
    actions.push({
      index: row.index,
      question_kind: row.kind,
      key: "applicant_reviewed_question",
      value,
      label: row.label,
      expected_label: row.label,
      expected_id: row.expected_id,
      expected_name: row.expected_name,
      expected_type: row.expected_type
    });
  }
  return actions;
}
