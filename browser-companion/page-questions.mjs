/* Serialized by Chrome only after user authorizes the selected answers.
   No upload, network fetch, navigation, submit or approval control selection.
   Source page can react to input/change; owner is warned before action. */
export async function fillReviewedAnswers(actions, approvedUrl, inspectedUrl) {
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
  const talentAdore = here.hostname === "ats.talentadore.com" &&
    intended.hostname === "ats.talentadore.com" &&
    /^\/apply\/[A-Za-z0-9_-]{1,120}\/[A-Za-z0-9_-]{5,30}\/?$/u.test(intended.pathname) &&
    here.pathname.replace(/\/+$/, "") === intended.pathname.replace(/\/+$/, "") &&
    !here.search && !intended.search && !here.hash && !intended.hash;
  // Standalone injected function: same safe public-origin rule as upload.mjs.
  const strict = ["jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com",
    ...ghHosts, "ats.talentadore.com"];
  const approvedHost = intended.hostname;
  // Mirror SmartPloy's original exact-job path guard; same host is not enough.
  const sameReviewedJobPath = (actual, approved) => {
    if (actual.search !== approved.search) return false;
    const source = approved.pathname.replace(/\/+$/, "") || "/";
    const live = actual.pathname.replace(/\/+$/, "") || "/";
    if (live === source) return true;
    if (source === "/") return false;
    if (["/apply", "/application"].some(suffix =>
        live === source + suffix || live.startsWith(source + suffix + "/"))) return true;
    return /\/(?:apply|application)$/.test(source) && live.startsWith(source + "/");
  };
  const generic = !strict.includes(approvedHost) &&
    here.origin === intended.origin && here.hostname === approvedHost &&
    typeof approvedUrl === "string" && approvedUrl.length <= 1500 &&
    !/[\\\u0000-\u0020\u007f]/u.test(approvedUrl) &&
    !/[\\\u0000-\u0020\u007f]/u.test(location.href) &&
    /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$/i.test(approvedHost) &&
    !/(?:^|\.)(?:localhost|local|internal|test|invalid|example|onion|lan|home|intranet)$/i.test(approvedHost) &&
    (intended.pathname !== "/" || intended.search.length > 0) &&
    here.search.length <= 800 && intended.search.length <= 800 &&
    sameReviewedJobPath(here, intended) &&
    !here.hash && !intended.hash;
  if (here.protocol !== "https:" || intended.protocol !== "https:" ||
      (here.origin !== intended.origin && !greenhouse) ||
      here.username || here.password || intended.username || intended.password ||
      here.port || intended.port || !(lever || ashby || greenhouse || talentAdore || generic) ||
      (typeof window !== "undefined" && window.top !== window.self) ||
      location.href !== inspectedUrl) {
    return stop("The employer or application form changed.");
  }
  if (!Array.isArray(actions) || !actions.length || actions.length > 12) {
    return stop("The selected answer list is invalid.");
  }
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  if (all.length > 250) return stop("The employer form is too large.");
  const sensitive = /\b(?:visa|citizenship|citizen|nationality|sponsor|sponsorship|work permit|right to work|work authori[sz]ation|authori[sz]ed to work|legally eligible to work|eligible to work|employment eligibility|salary|compensation|wage|expected pay|pay range|eeo|race|ethnic|gender|sex|sexual|religion|politic|union membership|disability|health condition|medical|veteran|military|criminal|felony|convict|background check|privacy|consent|gdpr|agree|agreement|attest|certif(?:y|ication)|signature|passport|social security|government id|tax id|birth date|date of birth|age|bank account|start date|notice period|työlupa|oleskelulupa|kansalaisuus|palkka|henkilötunnus|sukupuoli|uskonto|rikosrekisteri|suostumus|allekirjoitus|arbetstillstånd|medborgarskap|personnummer|samtycke|underskrift|lön|födelsetid|kön)\b/iu;
  const restrictedIdentifiers =
    /(?:visa|sponsor|salary|compensat|wage|workauth|workpermit|workeligib|legallyeligible|authorizedtowork|authorisedtowork|citizen|nationality|gender|sex|race|ethnic|religion|disabil|veteran|passport|birth|dateofbirth|consent|privacy|agreement|legal|attest|signature|criminal|backgroundcheck|immigrat|taxid|nationalid|henkilötunnus|sukupuol|kansalaisuu|oleskelulup|työlup|palkka|arbetstillstånd|medborgarskap|personnummer|samtycke)/i;
  function labelFor(el) {
    const raw = el.labels?.[0]?.innerText || el.getAttribute("aria-label") ||
      (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : "") ||
      el.getAttribute("placeholder") || el.getAttribute("name") || el.id || "";
    return String(raw).trim().slice(0, 150);
  }
  // Adapted from ObumAI's approved Playwright radio.check path, but without
  // forced clicks, checkbox toggling, inferred booleans or final submission.
  // Require one exact, fully observed FIELDSET/LEGEND group on the SAME form.
  function reviewedRadioChoice(a, shouldBeEmpty = true) {
    if (!a || a.type !== "radio_group" ||
        !Number.isInteger(a.index) || a.index < 0 || a.index >= all.length ||
        typeof a.value !== "string" || !a.value.length || a.value.length > 150 ||
        !Array.isArray(a.options) || a.options.length < 2 || a.options.length > 12 ||
        typeof a.expected_name !== "string" || !a.expected_name ||
        typeof a.label !== "string" || !a.label ||
        a.expected_placeholder !== "" || a.expected_max_length !== -1) return null;
    const first = all[a.index], form = first?.closest("form");
    const fieldset = first?.closest("fieldset");
    const legend = fieldset?.querySelector("legend");
    if (!form || !fieldset || !legend ||
        fieldset.firstElementChild !== legend ||
        String(legend.innerText || "").trim() !== a.label ||
        first?.type !== "radio" || first?.name !== a.expected_name ||
        first?.id !== a.expected_id) return null;
    const current = Array.from(document.querySelectorAll("input,textarea,select"));
    if (current.length !== all.length || current[a.index] !== first) return null;
    const nodes = Array.from(form.querySelectorAll("input[type='radio']"))
      .filter(node => node.name === a.expected_name);
    if (nodes.length !== a.options.length ||
        !nodes.some(node => node.required ||
          node.getAttribute("aria-required") === "true")) return null;
    const inspected = [a.label, a.expected_name, a.expected_id,
      ...a.options.map(option => String(option?.label || ""))].join(" ")
      .normalize("NFKC").replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
    if (sensitive.test(inspected) || restrictedIdentifiers.test(
      [a.expected_name, a.expected_id,
        ...a.options.map(option => String(option?.id || ""))].join(""))) return null;
    const values = new Set(), labels = new Set();
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i], approved = a.options[i];
      if (!approved || !Number.isInteger(approved.index) ||
          !Number.isInteger(a.options[i].index) ||
          !approved.value || !approved.label ||
          typeof approved.id !== "string" ||
          approved.index !== all.indexOf(node) ||
          current[approved.index] !== node || !node.isConnected ||
          node.closest("fieldset") !== fieldset || node.disabled ||
          node.readOnly || node.id !== approved.id ||
          node.value !== approved.value ||
          labelFor(node) !== approved.label ||
          node.closest("[hidden],[aria-hidden='true'],[inert]") ||
          getComputedStyle(node).display === "none" ||
          getComputedStyle(node).visibility === "hidden" ||
          node.getClientRects().length === 0 ||
          values.has(approved.value) || labels.has(approved.label.normalize("NFKC").toLowerCase())) return null;
      values.add(approved.value);
      labels.add(approved.label.normalize("NFKC").toLowerCase());
    }
    if (shouldBeEmpty && nodes.some(node => node.checked)) return null;
    const selected = nodes.filter(node => node.value === a.value);
    if (selected.length !== 1) return null;
    if (!shouldBeEmpty &&
        (nodes.filter(node => node.checked).length !== 1 || !selected[0].checked)) return null;
    return selected[0];
  }
  function valid(a) {
    if (!a || !Number.isInteger(a.index) || a.index < 0 || a.index >= all.length ||
        !["text", "textarea", "select", "radio_group"].includes(a.type) || typeof a.value !== "string" ||
        !a.value.trim() || a.value.length > 1500 ||
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(a.value) ||
        typeof a.label !== "string" || a.label.length > 150) return false;
    const el = all[a.index];
    const live = Array.from(document.querySelectorAll("input,textarea,select"));
    if (!el || !el.isConnected || live.length > 250 || live[a.index] !== el) return false;
    if (a.type === "radio_group") return !!reviewedRadioChoice(a, true);
    const type = el?.tagName === "TEXTAREA" ? "textarea" :
      el?.tagName === "INPUT" ? (el.type || "text").toLowerCase() :
      el?.tagName === "SELECT" ? "select" : "";
    if (type !== a.type || !el.closest("form") || el.disabled || el.readOnly ||
        !(el.required || el.getAttribute("aria-required") === "true") ||
        String(el.value || "").trim() ||
        el.id !== a.expected_id || el.name !== a.expected_name ||
        (el.getAttribute("placeholder") || "") !== a.expected_placeholder ||
        (Number.isInteger(el.maxLength) ? el.maxLength : -1) !== a.expected_max_length ||
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
    // A select option is allowed only when the applicant explicitly chose its
    // exact current employer-provided value. No fuzzy aliases or implicit yes.
    if (a.type === "select") {
      if (!Array.isArray(a.options) || a.options.length < 1 ||
          a.options.length > 24 || !a.options.every(o =>
            o && typeof o.value === "string" && o.value.length > 0 &&
            typeof o.label === "string" && o.label.length > 0)) return false;
      const approved = a.options.filter(o => o.value === a.value);
      if (approved.length !== 1) return false;
      const actual = Array.from(el.options).filter(o =>
        !o.disabled && o.value === a.value &&
        String(o.label || o.textContent || "").trim() === approved[0].label
      );
      if (actual.length !== 1) return false;
    }
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
      if (action.type === "radio_group") {
        const selected = reviewedRadioChoice(action, true);
        if (!selected) return stop("Employer radio choices changed; review manually.", filled);
        const checkSetter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype, "checked")?.set;
        if (!checkSetter) return stop("The radio input cannot be safely selected.", filled);
        checkSetter.call(selected, true);
        selected.dispatchEvent(new Event("input", {bubbles:true, composed:true}));
        selected.dispatchEvent(new Event("change", {bubbles:true, composed:true}));
        await new Promise(resolve => setTimeout(resolve, 150));
        if (location.href !== inspectedUrl ||
            reviewedRadioChoice(action, false) !== selected) {
          return stop("Employer radio selection was not retained; review manually.", filled);
        }
        filled++;
        continue;
      }
      const proto = action.type === "textarea" ? HTMLTextAreaElement.prototype :
        action.type === "select" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (!setter) return stop("The browser cannot safely fill this question.", filled);
      setter.call(el, action.value);
      el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      // First-party reuse: mirror the already implemented Playwright _fill_one
      // settle-and-observe policy. React/ATS handlers may clear a value just
      // AFTER an apparently successful DOM setter. Never retry a write.
      await new Promise(resolve => setTimeout(resolve, 150));
      if (location.href !== inspectedUrl) {
        return stop("Employer navigated during fill; review manually.", filled);
      }
      const current = Array.from(document.querySelectorAll("input,textarea,select"));
      if (!el.isConnected || current.length !== all.length ||
          current[action.index] !== el || el.id !== action.expected_id ||
          el.name !== action.expected_name || labelFor(el) !== action.label ||
          el.disabled || el.readOnly) {
        return stop("Employer form rerendered after input; re-inspect manually.", filled);
      }
      if (el.value !== action.value ||
          (action.type === "select" && (el.selectedOptions.length !== 1 ||
            el.selectedOptions[0].disabled ||
            !action.options.some(approved => approved.value === el.selectedOptions[0].value &&
              approved.label === String(el.selectedOptions[0].label ||
                el.selectedOptions[0].textContent || "").trim())))) {
        return stop("Employer did not retain the reviewed answer; finish manually.", filled);
      }
      filled++;
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
