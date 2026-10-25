/* Serialized by Chrome only after user authorizes the selected answers.
   No upload, network fetch, navigation, submit or approval control selection.
   Source page can react to input/change; owner is warned before action. */
export function fillReviewedAnswers(actions, approvedUrl, inspectedUrl) {
  const stop = (reason, filled = 0) => ({
    status: filled ? "partial_needs_review" : "blocked", filled, reason
  });
  let here, intended;
  try {
    here = new URL(location.href); intended = new URL(approvedUrl);
  } catch { return stop("An application URL is invalid."); }
  const leverPosting = intended.pathname.replace(/\/apply\/?$/, "").replace(/\/+$/, "");
  const ashbyPosting = intended.pathname.replace(/\/application\/?$/, "").replace(/\/+$/, "");
  const lever = ["jobs.lever.co", "jobs.eu.lever.co"].includes(here.hostname) &&
    /^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/u.test(leverPosting) &&
    [leverPosting + "/apply", leverPosting + "/apply/"].includes(here.pathname);
  const ashby = here.hostname === "jobs.ashbyhq.com" &&
    /^\/[A-Za-z0-9_-]{1,100}\/[A-Za-z0-9_-]{1,160}$/u.test(ashbyPosting) &&
    !here.search && !intended.search && !here.hash && !intended.hash &&
    [ashbyPosting + "/application", ashbyPosting + "/application/"]
      .includes(here.pathname);
  const ghHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io"];
  const greenhouse = ghHosts.includes(here.hostname) &&
    ghHosts.includes(intended.hostname) &&
    /^\/[A-Za-z0-9_-]{1,100}\/jobs\/[0-9]{1,20}\/?$/u.test(intended.pathname) &&
    here.pathname.replace(/\/+$/, "") === intended.pathname.replace(/\/+$/, "") &&
    !here.search && !intended.search && !here.hash && !intended.hash;
  if (here.protocol !== "https:" || intended.protocol !== "https:" ||
      (here.origin !== intended.origin && !greenhouse) ||
      here.username || here.password || intended.username || intended.password ||
      here.port || intended.port || !(lever || ashby || greenhouse) ||
      (typeof window !== "undefined" && window.top !== window.self) ||
      location.href !== inspectedUrl) {
    return stop("The employer or application form changed.");
  }
  if (!Array.isArray(actions) || !actions.length || actions.length > 12) {
    return stop("The selected answer list is invalid.");
  }
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  if (all.length > 250) return stop("The employer form is too large.");
  const sensitive = /\b(?:visa|citizenship|citizen|nationality|sponsor|sponsorship|work permit|right to work|work authori[sz]ation|salary|compensation|wage|expected pay|pay range|eeo|race|ethnic|gender|sex|sexual|religion|politic|union membership|disability|health condition|medical|veteran|military|criminal|felony|convict|background check|privacy|consent|gdpr|agree|agreement|attest|certif(?:y|ication)|signature|passport|social security|government id|tax id|birth date|date of birth|age|bank account|start date|notice period|työlupa|oleskelulupa|kansalaisuus|palkka|henkilötunnus|sukupuoli|uskonto|rikosrekisteri|suostumus|allekirjoitus|arbetstillstånd|medborgarskap|personnummer|samtycke|underskrift|lön|födelsetid|kön)\b/iu;
  const restrictedIdentifiers =
    /(?:visa|sponsor|salary|compensat|wage|workauth|workpermit|citizen|nationality|gender|sex|race|ethnic|religion|disabil|veteran|passport|birth|dateofbirth|consent|privacy|agreement|legal|attest|signature|criminal|backgroundcheck|immigrat|taxid|nationalid|henkilötunnus|sukupuol|kansalaisuu|oleskelulup|työlup|palkka|arbetstillstånd|medborgarskap|personnummer|samtycke)/i;
  function labelFor(el) {
    const raw = el.labels?.[0]?.innerText || el.getAttribute("aria-label") ||
      (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : "") ||
      el.getAttribute("placeholder") || el.getAttribute("name") || el.id || "";
    return String(raw).trim().slice(0, 150);
  }
  function valid(a) {
    if (!a || !Number.isInteger(a.index) || a.index < 0 || a.index >= all.length ||
        !["text", "textarea"].includes(a.type) || typeof a.value !== "string" ||
        !a.value.trim() || a.value.length > 1500 ||
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(a.value) ||
        typeof a.label !== "string" || a.label.length > 150) return false;
    const el = all[a.index];
    const live = Array.from(document.querySelectorAll("input,textarea,select"));
    if (!el || !el.isConnected || live.length > 250 || live[a.index] !== el) return false;
    const type = el?.tagName === "TEXTAREA" ? "textarea" :
      el?.tagName === "INPUT" ? (el.type || "text").toLowerCase() : "";
    if (type !== a.type || !el.closest("form") || el.disabled || el.readOnly ||
        !(el.required || el.getAttribute("aria-required") === "true") ||
        String(el.value || "").trim() ||
        el.id !== a.expected_id || el.name !== a.expected_name ||
        (el.getAttribute("placeholder") || "") !== a.expected_placeholder ||
        el.maxLength !== a.expected_max_length ||
        labelFor(el) !== a.label ||
        el.closest("[hidden],[aria-hidden='true'],[inert]") ||
        getComputedStyle(el).display === "none" ||
        getComputedStyle(el).visibility === "hidden" ||
        el.getClientRects().length === 0 ||
        (el.maxLength > 0 && a.value.length > el.maxLength)) return false;
    const metadata = [a.label, a.expected_id, a.expected_name, a.expected_placeholder]
      .join(" ").normalize("NFKC")
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .replace(/([A-Z])([A-Z][a-z])/g, "$1 $2")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ").trim().replace(/\s+/g, " ");
    const identifiers = [a.expected_id, a.expected_name, a.expected_placeholder].join("");
    if (sensitive.test(metadata) || restrictedIdentifiers.test(identifiers)) return false;
    // A second live field with the same visible question could silently steal
    // a reviewed answer even when the original index/id/name remain stable.
    const duplicates = live.filter(other =>
      other && other.isConnected && !other.closest("[hidden],[aria-hidden='true'],[inert]") &&
      getComputedStyle(other).display !== "none" &&
      getComputedStyle(other).visibility !== "hidden" &&
      other.getClientRects().length > 0 && labelFor(other) === a.label
    ).length;
    return duplicates === 1;
  }
  const indices = actions.map(x => x.index);
  if (new Set(indices).size !== indices.length || !actions.every(valid)) {
    return stop("At least one reviewed question changed; nothing was filled.");
  }
  let filled = 0;
  for (const action of actions) {
    if (location.href !== inspectedUrl || !valid(action)) {
      return stop("The employer changed the form while it was being filled.", filled);
    }
    const el = all[action.index];
    try {
      const proto = action.type === "textarea"
        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (!setter) return stop("The browser cannot safely fill this question.", filled);
      setter.call(el, action.value);
      el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      if (el.value !== action.value) {
        return stop("The employer did not retain an answer; review manually.", filled);
      }
      filled++;
      // Native input/change events may detach/recreate a React field, or append
      // new required fields. A value on a detached old node is NOT a live fill.
      const current = Array.from(document.querySelectorAll("input,textarea,select"));
      if (!el.isConnected || current.length !== all.length ||
          current[action.index] !== el || el.id !== action.expected_id ||
          el.name !== action.expected_name || labelFor(el) !== action.label) {
        return stop("Employer form rerendered after input; re-inspect manually.", filled);
      }
    } catch {
      return stop("The employer form changed during an answer; review manually.", filled);
    }
  }
  return {
    status: "filled_for_review",
    filled,
    reason: "Answers placed in the visible form. Review them and complete any remaining questions manually. No submission was attempted."
  };
}
