/* SP14: serialized into one user-selected, previously inspected Lever form.
   No closure, network, storage, file, checkbox or final-submit actions.
   The employer itself may send text when native input/change fires. */
export function fillReviewedQuestions(payload) {
  const blocked = (reason) => ({status: "blocked", filled: 0, reason});
  const uncertain = () => ({status: "uncertain", filled: 0,
    reason: "The employer form changed while filling. Review it manually; do not retry automatically."});
  try {
    if (!payload || !Array.isArray(payload.actions) ||
        payload.actions.length < 1 || payload.actions.length > 2) {
      return blocked("No approved applicant-written answers were provided.");
    }
    const page = new URL(location.href);
    const observed = new URL(payload.inspected_url);
    const job = new URL(payload.application_url);
    const base = job.pathname.replace(/\/apply\/?$/, "").replace(/\/+$/, "");
    if (page.href !== observed.href || page.origin !== job.origin ||
        page.protocol !== "https:" ||
        !["jobs.lever.co", "jobs.eu.lever.co"].includes(page.hostname) ||
        ![base + "/apply", base + "/apply/"].includes(page.pathname) ||
        !/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(base) ||
        page.username || page.password || page.port !== "") {
      return blocked("The current employer form differs from the approved Lever job.");
    }
    const fields = Array.from(document.querySelectorAll("input,textarea,select"));
    if (fields.length > 250) return blocked("Employer form changed or has too many fields.");

    function visible(el) {
      if (!el || !el.isConnected || el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden" &&
        el.getClientRects().length > 0;
    }
    function liveLabel(el) {
      const value = el.labels?.[0]?.innerText ||
        el.getAttribute("aria-label") ||
        (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : "") ||
        el.getAttribute("placeholder") || el.getAttribute("name") || el.id || "";
      return String(value).trim().slice(0, 150);
    }
    function normalize(value) { return String(value || "").replace(/\s+/g, " ").trim(); }
    function liveKind(label) {
      const normalized = normalize(label);
      if (/^(?:(?:how|where) did you (?:hear|learn|find out) about (?:us|this (?:job|role|position|opportunity))\??|how did you find (?:us|this (?:job|role|position))\??|mistä kuulit (?:meistä|tästä (?:työpaikasta|tehtävästä))\??|hur hörde du talas om (?:oss|den här tjänsten)\??)$/i.test(normalized)) return "source";
      if (/^(?:why (?:are you interested in|do you want to apply for) this (?:job|role|position|opportunity)\??|what interests you about this (?:job|role|position)\??|why would you like to join (?:our team|us)\??|miksi olet kiinnostunut tästä tehtävästä\??|varför är du intresserad av den här tjänsten\??)$/i.test(normalized)) return "motivation";
      return null;
    }
    const restricted = /(?:\b(?:visa|sponsor(?:ship)?|immigration|work\s+authori[sz]ation|work\s+permit|salary|compensation|wage|criminal|background\s+check|gender|sex|sexual|race|ethnic|religion|disability|veteran|birth|age|date\s+of\s+birth|passport|nationality|citizen(?:ship)?|bank|social\s+security|ssn|privacy|terms|consent|agree|accept|attest|signature|certify|captcha|recaptcha|mfa|password)\b|palkka|oleskelulup|työlup|kansalaisuu|sukupuol|uskont|syntym|ikäsi|henkilötunnus|suostum|tietosuoj|löneanspråk|arbetstillstånd|medborgarskap|samtycke|personnummer)/i;
    const control = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;

    const prepared = [];
    const chosenIndexes = new Set();
    const chosenKinds = new Set();
    for (const action of payload.actions) {
      if (!action || action.key !== "applicant_reviewed_question" ||
          !Number.isInteger(action.index) || action.index < 0 ||
          action.index >= fields.length || chosenIndexes.has(action.index) ||
          chosenKinds.has(action.question_kind)) {
        return blocked("Question identity changed or an action is duplicated.");
      }
      const el = fields[action.index];
      const type = el.tagName === "TEXTAREA" ? "textarea" :
        el.tagName === "INPUT" ? (el.type || "text").toLowerCase() : "";
      const label = liveLabel(el);
      const descriptor = [label, el.name, el.id, el.getAttribute("placeholder") || ""].join(" ");
      if (!["text", "textarea"].includes(type) || type !== action.expected_type ||
          (el.id || "") !== action.expected_id || (el.name || "") !== action.expected_name ||
          label !== action.expected_label || liveKind(label) !== action.question_kind ||
          restricted.test(descriptor) || !visible(el) || el.disabled || el.readOnly ||
          !el.closest("form") || String(el.value || "").trim() ||
          typeof action.value !== "string" || !action.value.trim() ||
          control.test(action.value) ||
          action.value.length > (action.question_kind === "source" ? 180 : 1200) ||
          (el.maxLength > 0 && action.value.length > el.maxLength)) {
        return blocked("A reviewed question has changed or is no longer safe to fill.");
      }
      if (fields.filter(other => visible(other) && liveLabel(other) === label).length !== 1) {
        return blocked("An employer question is duplicated or ambiguous.");
      }
      chosenIndexes.add(action.index);
      chosenKinds.add(action.question_kind);
      prepared.push({el, type, value: action.value});
    }

    // Preflight every field before any edit. Never click Submit or select files.
    for (const {el, type, value} of prepared) {
      try {
        const proto = type === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (!setter || !visible(el) || String(el.value || "").trim()) return uncertain();
        setter.call(el, value);
        el.dispatchEvent(new Event("input", {bubbles: true, composed: true}));
        el.dispatchEvent(new Event("change", {bubbles: true, composed: true}));
        if (!el.isConnected || el.value !== value) return uncertain();
      } catch {
        return uncertain();
      }
    }
    return {status: "filled_locally", filled: prepared.length,
      reason: "Only applicant-reviewed text was placed in the employer form. Check every answer; no application was submitted."};
  } catch {
    return blocked("The employer page could not be verified. Complete these questions manually.");
  }
}
