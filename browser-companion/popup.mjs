/* SmartPloy owner-operated browser companion popup.
   No background automation, no external API calls, no raw profile persistence.
   The final action is only possible after an exact one-job approval. */
import { PacketError, planFields, validatePacket } from "./logic.mjs";
import { UploadError, chooseResumeField, chooseCoverLetterField, encodePdfBase64, exactLeverForm, exactAssistedForm, exactGreenhouseForm, exactReceiptPage, isLeverFinalProvider, MAX_PDF_BYTES, validatePdf } from "./upload.mjs";
import { attachReviewedPdf } from "./page-attachment.mjs";
import { readOwnReviewedPdf } from "./page-document-fetch.mjs";
import { saveOneObservedReceiptOnSmartPloy } from "./page-receipt-import.mjs";
import { QuestionError, planReviewedQuestions, suggestSavedAnswers, validateReviewedAnswers } from "./questions.mjs";
import { fillReviewedAnswers } from "./page-questions.mjs";
import { AttemptError, oneAttemptKey, withSubmissionLock } from "./attempt-lock.mjs";
import {
  approvedFieldsSha256, approvedSavedAnswersSha256, isSmartPloyTab, recordVerifiedReview,
  requireVerifiedReview, sha256Text, validateReviewPacket,
  recordOneUseFinalAttempt, requireOneUseFinalAttempt, consumeLocalFinalAttempt
} from "./review-bridge.mjs";
import { verifyReviewOnSmartPloy } from "./page-review.mjs";
import { reserveFinalClickOnSmartPloy } from "./page-final-claim.mjs";
import { submitReviewedLeverOnce } from "./page-final-submit.mjs";

const $ = (id) => document.getElementById(id);
let targetTabId = null;
let currentPacket = null;
let currentPlan = null;
let currentQuestionPlan = null;
let inspectedUrl = "";
let preflightPassed = false;
let attemptReserved = false;
let receiptOnly = false;
let receiptCheckSequence = 0;
let startAutoApplyInFlight = false;
let completingOneJob = false;
let oneJobFinalApproval = false;
let oneJobSubmitWasAttempted = false;

function clearReceiptObservation() {
  receiptCheckSequence++;
  $("receiptPanel").hidden = true;
  $("receiptExport").value = "";
}

function enterReceiptMode() {
  receiptOnly = true;
  preflightPassed = false;
  currentPlan = null;
  currentQuestionPlan = null;
  $("approve").checked = false;
  $("plan").hidden = true;
  $("questionPanel").hidden = true;
  for (const id of ["fill", "attach", "reviewQuestions", "fillQuestions",
    "check", "approve", "reserveFinal", "submit"]) $(id).disabled = true;
  $("submit").setAttribute("aria-disabled", "true");
}

function status(message, success = false) {
  $("feedback").className = success ? "success" : "error";
  $("feedback").textContent = message;
}

function normalizeError(error) {
  if (error instanceof PacketError || error instanceof UploadError || error instanceof QuestionError || error instanceof AttemptError) return error.message;
  const value = error instanceof Error ? error.message : "";
  if (/^No tab with id|Cannot access contents|Missing host permission|The extensions gallery/.test(value)) {
    return "Open the employer job page in the active browser tab and try again.";
  }
  return "The browser action could not be completed. Check the employer page. Do not resubmit an uncertain attempt.";
}

function isVisible(element) {
  if (!element || element.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
  const style = getComputedStyle(element);
  return (
    style.display !== "none" && style.visibility !== "hidden" &&
    element.getClientRects().length > 0
  );
}

/* Serialized into the employer tab by chrome.scripting.executeScript. */
function inspectForm() {
  function visible(el) {
    if (el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" &&
      el.getClientRects().length > 0;
  }
  function label(el) {
    const a = el.labels?.[0]?.innerText ||
      el.getAttribute("aria-label") ||
      (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : "") ||
      el.getAttribute("placeholder") || el.getAttribute("name") || el.id || "";
    return String(a).trim().slice(0, 150);
  }
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  const elements = all.slice(0, 250).map((el, index) => {
    const type = el.tagName === "TEXTAREA" ? "textarea" :
      el.tagName === "SELECT" ? "select" : (el.type || "text").toLowerCase();
    const hasValue = type === "file" ? Boolean(el.files?.length) :
      ["checkbox", "radio"].includes(type) ? Boolean(el.checked) :
      Boolean(String(el.value || "").trim());
    return {
      index, id: String(el.id || "").slice(0, 150),
      name: String(el.name || "").slice(0, 150),
      type, label: label(el),
      autocomplete: String(el.getAttribute("autocomplete") || "").slice(0, 100),
      placeholder: String(el.getAttribute("placeholder") || "").slice(0, 140),
      required: Boolean(el.required || el.getAttribute("aria-required") === "true"),
      visible: visible(el), disabled: el.disabled === true, readonly: el.readOnly === true,
      hasValue, maxLength: Number(el.maxLength) || -1,
      accept: type === "file" ? String(el.accept || "").slice(0, 200) : "",
      multiple: type === "file" && el.multiple === true
    };
  });
  return {
    url: location.href,
    elements,
    allElementsCount: all.length
  };
}

/* Strictly fill only elements originally inspected and matching the same job.
   Use page-native value setters so React-controlled forms observe edits. */
async function fillPlanned(actions, exactUrl) {
  function visible(el) {
    if (!el || !el.isConnected ||
        el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" &&
      el.getClientRects().length > 0;
  }
  function labelFor(el) {
    return String(el.labels?.[0]?.innerText ||
      el.getAttribute("aria-label") ||
      (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : "") ||
      el.getAttribute("placeholder") || el.getAttribute("name") || el.id || "")
      .trim().slice(0,150);
  }
  function unsafeMetadata(el) {
    const fields = [labelFor(el), el.getAttribute("name"),
      el.id, el.getAttribute("placeholder"), el.getAttribute("autocomplete")];
    const material = fields.map(x => String(x || "")).join(" ")
      .normalize("NFKC").replace(/([a-z0-9])([A-Z])/g,"$1 $2")
      .replace(/([A-Z])([A-Z][a-z])/g,"$1 $2")
      .toLowerCase().replace(/[^\p{L}\p{N}]+/gu," ");
    if (/\b(?:visa|sponsorship|sponsor|immigration|work authorization|work permit|salary|compensation|wage|expected pay|eeo|race|ethnic|gender|sex|sexual|religion|disability|veteran|military|medical|health|criminal|background check|citizenship|nationality|passport|birth|date of birth|age|social security|ssn|gdpr|privacy|consent|agreement|attest|signature|certification|legal|bank account|tax id|company|employer|organization|organisation|referee|recommender|palkka|työlupa|oleskelulupa|kansalaisuus|sukupuoli|uskonto|syntymä|henkilötunnus|suostumus|tietosuoja|arbetstillstånd|medborgarskap|personnummer|samtycke|lön)\b/iu.test(material)) return true;
    const identifiers = [el.name,el.id,el.getAttribute("placeholder")].join("");
    return /(?:visa|sponsor|salary|compensat|wage|workauth|workpermit|citizen|nationality|gender|sex|race|ethnic|religion|disabil|veteran|passport|birth|dateofbirth|consent|privacy|agreement|legal|attest|signature|criminal|backgroundcheck|immigrat|taxid|nationalid|gdpr|henkilötunnus|sukupuol|kansalaisuu|oleskelulup|työlup|palkka|arbetstillstånd|medborgarskap|personnummer|samtycke)/i.test(identifiers);
  }
  function sameJob(a, b) {
    try {
      const x = new URL(a), y = new URL(b);
      const prefix = y.pathname.replace(/\/+$/, "");
      // Executed inside the employer tab via chrome.scripting: standalone,
      // no imports or popup closure. Reuse the same exact hosted-job policy.
      const ghHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io"];
      if (x.protocol === "https:" && y.protocol === "https:" &&
          ghHosts.includes(x.hostname) && ghHosts.includes(y.hostname) &&
          /^\/[A-Za-z0-9_-]{1,100}\/jobs\/[0-9]{1,20}\/?$/.test(y.pathname) &&
          x.pathname.replace(/\/+$/, "") === y.pathname.replace(/\/+$/, "") &&
          !x.search && !y.search && !x.hash && !y.hash &&
          !x.username && !x.password && !y.username && !y.password &&
          !x.port && !y.port) return true;
      if (x.origin !== y.origin || x.protocol !== "https:" ||
          x.username || x.password || y.username || y.password) return false;
      // Ashby forms are accepted ONLY for the exact reviewed job's
      // /application route; never a sibling or arbitrary job subpath.
      if (y.hostname === "jobs.ashbyhq.com") {
        const posting = prefix.replace(/\/application$/, "");
        return !x.search && !y.search && !x.hash && !y.hash &&
          /^\/[A-Za-z0-9_-]{1,100}\/[A-Za-z0-9_-]{1,160}$/.test(posting) &&
          [posting + "/application", posting + "/application/"].includes(x.pathname);
      }
      return x.pathname === prefix || x.pathname === prefix + "/" ||
        x.pathname.startsWith(prefix + "/");
    } catch { return false; }
  }
  if (!Array.isArray(actions) || actions.length > 120) {
    return { filled: 0, skipped: 0, blocker: "Too many fields to fill safely." };
  }
  const originalUrl = location.href;
  if (!sameJob(originalUrl, exactUrl)) {
    return { filled: 0, skipped: actions.length, blocker: "Employer page changed since packet approval." };
  }
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  let filled = 0, skipped = 0;
  if (all.length > 250) {
    return {filled:0,skipped:actions.length,blocker:"Employer form is too large; inspect manually."};
  }
  const seen = new Set();
  const verified = [];
  // A later field can trigger React to clear an earlier, already checked one.
  // Each candidate success must remain valid throughout the entire batch.
  function persistedCount() {
    const rows = Array.from(document.querySelectorAll("input,textarea,select"));
    if (location.href !== originalUrl || !sameJob(location.href, exactUrl) ||
        rows.length !== all.length) return 0;
    return verified.filter(({ element, action }) => {
      const kind = element.tagName === "TEXTAREA" ? "textarea" :
        element.tagName === "SELECT" ? "select" :
        (element.type || "text").toLowerCase();
      return element.isConnected && rows[action.index] === element &&
        visible(element) && !element.disabled && !element.readOnly &&
        kind === action.expected_type &&
        (element.id || "") === action.expected_id &&
        (element.name || "") === action.expected_name &&
        labelFor(element) === action.label && !unsafeMetadata(element) &&
        element.value === action.value;
    }).length;
  }
  for (const action of actions) {
    if (verified.length && persistedCount() !== verified.length) {
      return {filled:persistedCount(),skipped,
        blocker:"A previously filled employer field changed. Review manually without retry."};
    }
    if (!action || !Number.isInteger(action.index) || action.index < 0 ||
        action.index >= all.length || seen.has(action.index)) {
      return {filled,skipped,blocker:"Employer form or approved field indices changed. Reinspect manually."};
    }
    seen.add(action.index);
    const current = Array.from(document.querySelectorAll("input,textarea,select"));
    const el = all[action.index];
    if (current.length !== all.length || current[action.index] !== el) {
      return {filled,skipped,blocker:"Employer form shifted after inspection. Reinspect manually."};
    }
    const type = el.tagName === "TEXTAREA" ? "textarea" :
      el.tagName === "SELECT" ? "select" : (el.type || "text").toLowerCase();
    if ((el.id || "") !== action.expected_id ||
        (el.name || "") !== action.expected_name ||
        type !== action.expected_type || labelFor(el) !== action.label ||
        unsafeMetadata(el) || !visible(el)) {
      return {filled,skipped,blocker:"Approved contact field identity, label or safety metadata changed. Reinspect manually."};
    }
    if (current.filter(other => visible(other) && labelFor(other) === action.label).length !== 1) {
      return {filled,skipped,blocker:"Duplicate visible contact labels require manual review."};
    }
    if (
      el.disabled || el.readOnly ||
      !["text", "email", "tel", "url", "search", "textarea"].includes(type) ||
      String(el.value || "").trim() ||
      typeof action.value !== "string" || action.value.length > 10000 ||
      (el.maxLength > 0 && action.value.length > el.maxLength)
    ) { skipped++; continue; }
    try {
      const prototype = type === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (!setter) { skipped++; continue; }
      setter.call(el, action.value);
      el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      // Reuse PR #317's verified-settled-value invariant in the deployed
      // extension. React employer forms can erase an input AFTER dispatch.
      // Never count a write until the page has had time to react.
      await new Promise(resolve => setTimeout(resolve, 150));
      const after = Array.from(document.querySelectorAll("input,textarea,select"));
      if (location.href !== originalUrl || !sameJob(location.href, exactUrl) ||
          !el.isConnected || after.length !== all.length ||
          after[action.index] !== el || !visible(el) ||
          el.disabled || el.readOnly || labelFor(el) !== action.label ||
          unsafeMetadata(el) || (el.id || "") !== action.expected_id ||
          (el.name || "") !== action.expected_name ||
          el.value !== action.value) {
        return {filled,skipped,blocker:"Employer form changed or cleared a reviewed value. Check it manually without retry."};
      }
      verified.push({element:el,action});
      filled = persistedCount();
      if (filled !== verified.length) {
        return {filled,skipped,blocker:"An earlier reviewed employer field changed. Check manually without retry."};
      }
    } catch {
      return {filled,skipped,blocker:"Contact field fill outcome is uncertain. Review manually without retry."};
    }
  }
  filled = persistedCount();
  if (filled !== verified.length) {
    return {filled,skipped,blocker:"A reviewed employer value changed after filling. Check manually without retry."};
  }
  return { filled, skipped, blocker: "" };
}

function inspectFinalSubmit(exactUrl) {
  function visible(el) {
    if (el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" &&
      el.getClientRects().length > 0;
  }
  const blockers = [];
  const here = new URL(location.href);
  const intended = new URL(exactUrl);
  const matchesJob = here.origin === intended.origin && (
    here.pathname === intended.pathname ||
    here.pathname === intended.pathname.replace(/\/+$/, "") + "/" ||
    here.pathname.startsWith(intended.pathname.replace(/\/+$/, "") + "/")
  );
  if (!matchesJob) blockers.push("Employer page does not match the approved job.");
  const approvedLeverHost = ["jobs.lever.co", "jobs.eu.lever.co"].includes(here.hostname);
  if (!approvedLeverHost) blockers.push("Automated submit is only available on verified Lever job forms.");
  if (!here.pathname.endsWith("/apply") && !here.pathname.endsWith("/apply/")) {
    blockers.push("Navigate to the employer's application form, not just the job description.");
  }

  const allButtons = Array.from(document.querySelectorAll('button,input[type="submit"]'));
  const finalButtons = allButtons.filter((el) => {
    const content = String(el.innerText || el.value || el.getAttribute("aria-label") || "")
      .replace(/\s+/g, " ").trim().toLowerCase();
    return visible(el) && !el.disabled &&
      (content === "submit application" || content === "send application" ||
       content === "lähetä hakemus" || content === "skicka ansökan");
  });
  if (finalButtons.length !== 1) blockers.push("A unique, enabled final application button was not found.");
  const final = finalButtons[0];
  if (final && !final.closest("form")) blockers.push("The final application button is not inside a standard employer form.");

  const inputs = Array.from(document.querySelectorAll("input,textarea,select"))
    .filter((el) => visible(el) && !el.disabled);
  const emptyRequired = [];
  const fileInputs = [];
  for (const el of inputs) {
    const required = el.required === true || el.getAttribute("aria-required") === "true";
    const type = String(el.type || "").toLowerCase();
    const value = type === "file" ? Boolean(el.files?.length) :
      ["checkbox", "radio"].includes(type) ? Boolean(el.checked) :
      Boolean(String(el.value || "").trim());
    const label = String(el.labels?.[0]?.innerText || el.getAttribute("aria-label") ||
      el.name || el.id || "Required field").slice(0, 100);
    if (type === "file") fileInputs.push({ label, hasFile: value });
    if (required && !value) emptyRequired.push(label);
    if (el.validity && !el.validity.valid && !emptyRequired.includes(label)) {
      emptyRequired.push(label);
    }
  }
  if (!fileInputs.some((row) => row.hasFile &&
      /(^|[^a-z])(cv|resume|r[ée]sum[ée]|ansioluettelo|meritförteckning)([^a-z]|$)/i.test(row.label))) {
    blockers.push("A CV/résumé must be attached in its own labeled upload field.");
  }
  if (emptyRequired.length) blockers.push("Required fields still need review: " + emptyRequired.slice(0, 15).join(", "));
  if (document.querySelector(
    'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.g-recaptcha,[data-sitekey],.cf-turnstile'
  )) blockers.push("Security challenge requires direct human completion.");
  if (!document.querySelector("form")) blockers.push("Standard application form not present.");
  return { ready: blockers.length === 0, blockers, finalButtonCount: finalButtons.length,
    filledUploads: fileInputs.filter((x) => x.hasFile).length };
}

/* Single click after preflight, exact user approval and pre-allocated attempt.
   Do not navigate, set bypass flags, or retry. */
/* SP15b: no privileged employer final click is registered until the
   owner-scoped PostgreSQL claim is atomically redeemed by this companion.
   A local Web Lock alone cannot protect against a second browser/device. */

async function inspectReceipt(expectedApplicationUrl) {
  // chrome.scripting serializes this function without module imports. Keep
  // this isolated-world URL predicate in parity with upload.mjs and Python;
  // the popup checks the SAME scope before dispatching this read-only scan.
  function exactReceiptPage(activeUrl, packetUrl) {
    try {
      for (const raw of [activeUrl, packetUrl]) {
        if (typeof raw !== "string" || raw.length < 14 || raw.length > 1500 ||
            /[\\\u0000-\u0020\u007f]/.test(raw)) return false;
        const address = raw.match(/^[A-Za-z][A-Za-z0-9+.-]*:\/\/([^/?#]*)([^?#]*)/);
          const path = address?.[2];
          if (!address || /[%\u0080-\uffff]/.test(address[1])) return false;
        if (path === undefined || path.includes("%") || path.includes("//") ||
            path.split("/").some(part => part === "." || part === "..")) return false;
      }
      const here = new URL(activeUrl);
      const intended = new URL(packetUrl);
      if (here.protocol !== "https:" || intended.protocol !== "https:" ||
          here.username || here.password || intended.username || intended.password ||
          here.port || intended.port || intended.search || intended.hash) return false;
      const greenhouseHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io"];
      const greenhouse = greenhouseHosts.includes(intended.hostname) &&
        greenhouseHosts.includes(here.hostname);
      if (!greenhouse && here.origin !== intended.origin) return false;
      let posting, suffix;
      if (["jobs.lever.co", "jobs.eu.lever.co"].includes(intended.hostname)) {
        if (!/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+(?:\/apply\/?)?$/.test(intended.pathname)) return false;
        posting = intended.pathname.replace(/\/apply\/?$/, "");
        suffix = /^\/(?:apply(?:\/[A-Za-z0-9_-]+)*|thanks|confirmation)\/?$/;
      } else if (intended.hostname === "jobs.ashbyhq.com") {
        if (!/^\/[A-Za-z0-9_-]{1,100}\/[A-Za-z0-9_-]{1,160}(?:\/application\/?)?$/.test(intended.pathname)) return false;
        posting = intended.pathname.replace(/\/application\/?$/, "");
        suffix = /^\/application(?:\/[A-Za-z0-9_-]+)*\/?$/;
      } else if (greenhouse) {
        if (!/^\/[A-Za-z0-9_-]{1,100}\/jobs\/[0-9]{1,20}\/?$/.test(intended.pathname)) return false;
        posting = intended.pathname.replace(/\/$/, "");
        suffix = /^\/confirmation\/?$/;
      } else return false;
      return here.pathname === posting || here.pathname === posting + "/" ||
        (here.pathname.startsWith(posting + "/") &&
          suffix.test(here.pathname.slice(posting.length)));
    } catch {
      return false;
    }
  }
  if (!exactReceiptPage(location.href, expectedApplicationUrl)) {
    return { confirmed: false, explanation: "The browser is not at the exact reviewed employer job." };
  }
  const here = new URL(location.href);
  const text = String(document.body?.innerText || "").slice(0, 20000)
    .replace(/\s+/g, " ");
  const proof = /(?:application (?:has been )?(?:submitted|received)|submission (?:is )?confirmed|thank you for (?:your )?(?:application|applying)|we have received your application)/i.test(text);
  const reference = text.match(/(?:reference|confirmation|application|submission)\s*(?:id|number|no\.?|#)?\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]{3,63})/i)?.[1] || "";
  const hasLiveSubmit = () => Array.from(document.querySelectorAll("button,input[type=submit]")).some((el) =>
    (el.type === "submit" && el.form ||
      /^(submit|send|apply|apply now|submit application|send application|lähetä hakemus|skicka ansökan)$/i
        .test(String(el.innerText || el.value || "").trim())) &&
    el.getClientRects().length > 0 && !el.disabled
  );
  const confirmed = proof && Boolean(reference) && !hasLiveSubmit();
  const hashBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  const pageHash = Array.from(new Uint8Array(hashBytes))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  // The employer may redirect or rerender while async digest runs. Never
  // package a confirmation that was no longer visible at return time.
  if (location.href !== here.href || hasLiveSubmit() ||
      String(document.body?.innerText || "").slice(0, 20000).replace(/\s+/g, " ") !== text) {
    return {confirmed:false,explanation:"Employer confirmation changed; inspect it personally."};
  }
  return {
    confirmed,
    reference: confirmed ? reference : "",
    confirmation_page_url: here.origin + here.pathname,
    confirmation_page_sha256: pageHash,
    explanation: confirmed ?
      "The visible employer page contains a confirmation phrase and application reference. Save that reference in SmartPloy." :
      "No sufficient confirmation evidence found. The outcome remains unverified. Do not retry automatically."
  };
}

/* Ashby has NO automated final-click attempt protocol. Do not call the
   original Lever-only oneAttemptKey on these reviewed form-help packets. */
async function hasPriorLeverAttempt(packet) {
  if (!isLeverFinalProvider(packet.application_url)) return false;
  const key = await oneAttemptKey(packet);
  return Boolean((await chrome.storage.local.get(key))[key]);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new PacketError("Open the employer job page first.");
  return tab;
}

/** A local approval cannot remain valid after its account profile changed.
 * Recheck every external data transfer against the current signed-in owner,
 * exact job/revision, BOTH PDF digests and the latest approved Q/A set.
 * No private answers, PDF, cookie or login token is stored here.
 */
async function requireFreshOwnerReview(packet) {
  const approvedHash = await approvedSavedAnswersSha256(packet.saved_answers || []);
  if (!packet.letter_pdf_sha256 || !packet.letter_pdf_size ||
      packet.saved_answers_sha256 !== approvedHash) {
    throw new PacketError("Saved profile or letter changed; review a fresh application packet.");
  }
  const owned = (await chrome.tabs.query({
    url:["https://smartploy.komplyint.fi/*","https://smartploy.obumai.com/*"]
  })).filter(item=>item?.id && item?.url && isSmartPloyTab(item.url));
  if (owned.length !== 1) {
    throw new PacketError("Keep one signed-in SmartPloy tab open to check the current profile and documents.");
  }
  const [reply] = await chrome.scripting.executeScript({
    target:{tabId:owned[0].id},world:"ISOLATED",
    func: verifyReviewOnSmartPloy,args:[{
      workspace_id:packet.workspace_id,
      expected_revision:packet.revision,
      expected_document_sha256:packet.document_sha256,
      expected_cv_pdf_sha256:packet.cv_pdf_sha256,
      expected_cv_pdf_size:packet.cv_pdf_size,
      expected_fields_sha256:await approvedFieldsSha256(packet.fields),
      expected_application_url_sha256:await sha256Text(packet.application_url),
      expected_letter_pdf_sha256:packet.letter_pdf_sha256,
      expected_letter_pdf_size:packet.letter_pdf_size,
      expected_saved_answers_sha256:approvedHash
    }]
  });
  if (reply?.frameId !== 0 || !reply?.result?.review_verified ||
      reply.result.bound_profile_and_letter !== true) {
    throw new PacketError("The approved profile or CV/letter is stale. Return to SmartPloy and review it again.");
  }
  return reply.result;
}

/** One exact reviewed form binding for both harmless preflight and final click.
 * Only the independent server claim and a human confirmation can enable the
 * final click; passing dry_run=true never grants a submission capability.
 */
function finalEmployerBinding(packet, dryRun = false) {
  return {
    application_url:packet.application_url,
    cv_pdf_sha256:packet.cv_pdf_sha256,
    cv_pdf_size:packet.cv_pdf_size,
    letter_pdf_sha256:packet.letter_pdf_sha256,
    letter_pdf_size:packet.letter_pdf_size,
    email:packet.fields.email,
    full_name:packet.fields.full_name,
    cover_letter:packet.fields.cover_letter,
    ...(dryRun ? {dry_run:true} : {})
  };
}

/** Secret-free immutable server intent, including the latest reviewed profile.
 * No employer interaction is performed while this value is generated.
 */
async function finalOneJobClaimBinding(packet) {
  const memoryHash=await approvedSavedAnswersSha256(packet.saved_answers || []);
  if (memoryHash !== packet.saved_answers_sha256 ||
      !packet.letter_pdf_sha256 || !packet.letter_pdf_size) {
    throw new PacketError("The saved profile or cover letter changed. Create a fresh packet.");
  }
  return {
    workspace_id:packet.workspace_id,expected_revision:packet.revision,
    expected_document_sha256:packet.document_sha256,
    expected_cv_pdf_sha256:packet.cv_pdf_sha256,
    expected_cv_pdf_size:packet.cv_pdf_size,
    expected_fields_sha256:await approvedFieldsSha256(packet.fields),
    expected_application_url_sha256:await sha256Text(packet.application_url),
    expected_saved_answers_sha256:memoryHash,
    expected_letter_pdf_sha256:packet.letter_pdf_sha256,
    expected_letter_pdf_size:packet.letter_pdf_size,
    confirm_one_job_final_click:true,
    acknowledge_external_employer_transfer:true,
    acknowledge_no_automatic_retry:true
  };
}

async function signedInAppTab() {
  const items=(await chrome.tabs.query({
    url:["https://smartploy.komplyint.fi/*","https://smartploy.obumai.com/*"]
  })).filter(tab=>tab?.id && tab?.url && isSmartPloyTab(tab.url));
  if (items.length !== 1)
    throw new PacketError(
      "Keep exactly one signed-in SmartPloy tab open for this application."
    );
  return items[0];
}

async function onVerifySmartPloyReview() {
  $("reviewInfo").textContent = "";
  try {
    const packet = validateReviewPacket($("packet").value);
    const tab = await activeTab();
    if (!isSmartPloyTab(tab.url)) {
      throw new PacketError(
        "Open smartploy.komplyint.fi while signed in, then click Verify review. " +
        "After verification, return to the employer form and paste this same packet."
      );
    }
    if (!chrome.storage?.session) {
      throw new PacketError("Ephemeral extension storage unavailable. No review can be verified.");
    }
    const refreshed=await requireFreshOwnerReview(packet);
    const saved = await recordVerifiedReview(chrome.storage.session, packet, refreshed);
    $("reviewInfo").textContent =
      "Signed-in review verified until " + new Date(saved.expires_at).toLocaleTimeString() +
      (isLeverFinalProvider(packet.application_url)
        ? ". Open the exact employer form. A one-use final click requires separate employer permission."
        : ". Open the exact reviewed employer form. Final submission must be done by you.");
    status("Only a short-lived review fingerprint is in extension memory. No login token or CV was saved.", true);
  } catch (error) {
    $("reviewInfo").textContent = "Review not verified. Assisted form filling remains disabled.";
    status(normalizeError(error));
  }
}

async function onReserveFinalAttempt() {
  if (receiptOnly) return;
  $("finalClaimInfo").textContent = "";
  try {
    const packet = validateReviewPacket($("packet").value);
    if (!isLeverFinalProvider(packet.application_url)) {
      throw new PacketError("This provider supports reviewed form assistance only. Submit manually on the employer's form; no browser final claim is available.");
    }
    const tab = await activeTab();
    if (!isSmartPloyTab(tab.url)) {
      throw new PacketError(
        "Open your signed-in smartploy.komplyint.fi tab and return to the companion."
      );
    }
    await requireVerifiedReview(chrome.storage?.session, packet);
    const key = await oneAttemptKey(packet);
    if (!chrome.storage?.local || (await chrome.storage.local.get(key))[key]) {
      throw new PacketError("An employer attempt is already recorded locally. Do not retry.");
    }
    // The employer form must already have been inspected/reviewed. We return
    // to SmartPloy for the one-use server claim to keep HttpOnly sessions
    // isolated from all employer pages.
    if (!window.confirm(
      "RESERVE ONE IRREVERSIBLE EMPLOYER SUBMISSION ATTEMPT?\n\n" +
      packet.company + " — " + packet.role_title + "\n" +
      packet.application_url + "\n\n" +
      "I personally reviewed the complete employer form, CV, all answers " +
      "and consent statements. The server reserves this job across devices " +
      "NOW, even if the browser click later fails. No automatic retry. " +
      "Only an independently permitted employer may receive the application. Proceed?"
    )) return;
    // Consent does NOT freeze the CV/letter/profile. Recheck after it before
    // server consumes the irreversible cross-device employer attempt.
    await requireVerifiedReview(chrome.storage?.session,packet);
    await requireFreshOwnerReview(packet);
    const [response] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, world: "ISOLATED",
      func: reserveFinalClickOnSmartPloy,
      args: [{
        workspace_id: packet.workspace_id,
        expected_revision: packet.revision,
        expected_document_sha256: packet.document_sha256,
        expected_cv_pdf_sha256: packet.cv_pdf_sha256,
        expected_fields_sha256: await approvedFieldsSha256(packet.fields),
        expected_application_url_sha256: await sha256Text(packet.application_url),
        expected_cv_pdf_size: packet.cv_pdf_size,
        expected_saved_answers_sha256: await approvedSavedAnswersSha256(packet.saved_answers || []),
        expected_letter_pdf_sha256: packet.letter_pdf_sha256,
        expected_letter_pdf_size: packet.letter_pdf_size,
        confirm_one_job_final_click: true,
        acknowledge_external_employer_transfer: true,
        acknowledge_no_automatic_retry: true,
      }],
    });
    const verdict = response?.result;
    if (response?.frameId !== 0 || verdict?.claim_reserved !== true) {
      throw new PacketError(
        "No confirmed server authorization (" + (verdict?.reason || "unknown") +
        "). Check My applications > attempt status before another action. Do not retry."
      );
    }
    const marker = await recordOneUseFinalAttempt(
      chrome.storage.session, packet, verdict,
    );
    $("finalClaimInfo").textContent =
      "Server attempt reserved until " +
      new Date(marker.expires_at).toLocaleTimeString() +
      ". Return to the SAME employer form, reopen this companion, " +
      "check all required fields and click the one-use Submit button.";
    status("One server attempt reserved. Nothing has been sent to the employer yet.", true);
  } catch (error) {
    status(normalizeError(error));
    $("finalClaimInfo").textContent =
      "No final-click permission confirmed. A server claim may already be " +
      "consumed. Check My applications before any repeat.";
  }
}

async function onInspect() {
  clearReceiptObservation();
  const inspectSequence = receiptCheckSequence;
  const packetText = $("packet").value;
  try {
    const tab = await activeTab();
    const pkt = validatePacket(packetText, tab.url);
    await requireVerifiedReview(chrome.storage?.session, pkt);
    // Read-only inspection keeps the existing owner/session marker; current
    // account facts are rechecked before EVERY employer-side mutation.
    if (!exactAssistedForm(tab.url, pkt.application_url)) {
      throw new PacketError("Open the exact approved employer application form, not its job description.");
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: inspectForm
    });
    // An earlier form scan must not reopen editing after the user switches
    // to confirmation inspection, changes packets or starts a newer scan.
    if (inspectSequence !== receiptCheckSequence || packetText !== $("packet").value) return;
    const again = await activeTab();
    if (inspectSequence !== receiptCheckSequence || packetText !== $("packet").value) return;
    if (again.id !== tab.id || again.url !== tab.url) {
      throw new PacketError("The employer tab changed. Inspect the current application again.");
    }
    if (!result?.result || result.result.url !== tab.url || result.result.allElementsCount > 250) {
      throw new PacketError("The employer form is dynamic or too large. Please fill it manually.");
    }
    const candidate = planFields(result.result.elements, pkt);
    // Contact details may already be filled. A question-only application must
    // still reach its review screen, without inventing any contact action.
    const questions = planReviewedQuestions(result.result.elements);
    if (!candidate.actions.length && !candidate.skippedUploads.length &&
        !questions.questions.length && !questions.humanOnly.length) {
      throw new PacketError("No supported fields, uploads or questions were found. Review this application manually.");
    }
    targetTabId = tab.id;
    currentPacket = pkt;
    inspectedUrl = tab.url;
    currentPlan = candidate;
    currentQuestionPlan = null;
    $("questionList").replaceChildren();
    $("questionPanel").hidden = true;
    $("questionInfo").textContent = "";
    $("fillQuestions").disabled = false;
    preflightPassed = false;
    attemptReserved = false;
    receiptOnly = false;
    $("fill").disabled = false;
    $("reviewQuestions").disabled = false;
    $("plan").hidden = false;
    $("submission").hidden = candidate.actions.length > 0;
    const leverSubmit = isLeverFinalProvider(pkt.application_url);
    $("reserveFinal").disabled = !leverSubmit;
    $("check").disabled = !leverSubmit;
    $("approve").disabled = !leverSubmit;
    const providerName = new URL(pkt.application_url).hostname === "jobs.ashbyhq.com"
      ? "Ashby" : "Greenhouse";
    $("resume").disabled = false;
    $("receipt").disabled = false;
    $("finalClaimInfo").textContent = leverSubmit ? "" :
      providerName + ": reviewed contacts, ordinary questions and CV PDF assistance only. " +
      "Submit personally on the employer website; no automatic final click. " +
      "You may import a same-job, reference-bearing manual confirmation. " +
      "Otherwise use I applied on employer site to track your own report.";
    $("uploadInfo").textContent = "";
    $("cvFile").value = "";
    $("attach").disabled = false;
    $("approve").checked = false;
    $("submit").disabled = true;
    $("job").textContent = pkt.role_title + " — " + pkt.company;
    $("summary").textContent =
      candidate.actions.length + " approved contact/cover-letter fields can be filled. " +
      candidate.skippedUploads.length + " file inputs need review. Only a unique visible CV PDF field can use the approved attachment step.";
    $("required").textContent =
      candidate.unresolvedRequired.length ?
        "Review these required fields yourself: " + candidate.unresolvedRequired.slice(0, 12).join("; ") : "";
    const list = $("actions");
    list.replaceChildren();
    for (const action of candidate.actions) {
      const li = document.createElement("li");
      li.textContent = action.label + " — " + action.key.replaceAll("_", " ");
      list.append(li);
    }
    status("Review the proposed fields and continue. No employer data was changed.", true);
  } catch (error) {
    if (inspectSequence === receiptCheckSequence) status(normalizeError(error));
  }
}

async function onFill() {
  if (receiptOnly || !currentPacket || !currentPlan) return false;
  if (!window.confirm(
    "Fill only the displayed approved fields on the selected employer page? " +
    "No documents will be uploaded and no application will be submitted."
  )) return false;
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
    await requireFreshOwnerReview(currentPacket);
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new PacketError("Reinspect after changing employer tab, URL, or application form.");
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillPlanned,
      args: [currentPlan.actions, currentPacket.application_url]
    });
    if (!result?.result) throw new PacketError("Employer form did not return fill verification");
    if (result.result.blocker) throw new PacketError(result.result.blocker);
    $("submission").hidden = false;
    currentQuestionPlan = null;
    $("questionPanel").hidden = true;
    $("questionList").replaceChildren();
    preflightPassed = false;
    status(
      "Filled " + result.result.filled + " fields (" + result.result.skipped +
      " skipped). Review every value. Select a reviewed PDF for explicit attachment or attach manually.", true
    );
    // A no-blocker result is a completed attempt even when browser autofill
    // already supplied every value and the executor wrote zero fields. Keep
    // later question inspection available; this never authorizes final send.
    return true;
  } catch (error) { status(normalizeError(error)); return false; }
}

/** Fetch generated PDFs from this applicant's still-signed-in SmartPloy tab
 * and attach them to exact approved employer fields without making the user
 * download/re-upload files. A single explicit employer-transfer approval is
 * still required because attaching may trigger immediate employer upload.
 * Documents live only inside this invocation, never extension storage.
 */
async function autoAttachSavedDocuments() {
  if (!currentPacket || targetTabId === null || receiptOnly || attemptReserved) {
    return {attached:0,reason:"No current reviewed application."};
  }
  const packet = currentPacket;
  if (!packet.letter_pdf_sha256 || !packet.letter_pdf_size) {
    return {attached:0,reason:"Prepare a fresh application packet for automatic CV and letter attachment."};
  }
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(),tab.url);
    await requireVerifiedReview(chrome.storage?.session,packet);
    await requireFreshOwnerReview(packet);
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url,packet.application_url) ||
        await hasPriorLeverAttempt(packet)) {
      throw new PacketError("Employer page, application or prior attempt changed.");
    }
    const [form] = await chrome.scripting.executeScript({
      target:{tabId:tab.id},func:inspectForm
    });
    if (!form?.result || form.result.url !== tab.url ||
        form.result.allElementsCount > 250) {
      throw new UploadError("The employer form changed during attachment inspection.");
    }
    const cvTarget = chooseResumeField(form.result.elements);
    let letterTarget = null;
    let letterNote = "";
    try {
      letterTarget = chooseCoverLetterField(form.result.elements);
    } catch (error) {
      if (error instanceof UploadError &&
          error.message.startsWith("No separate cover-letter PDF input")) {
        letterNote = "No separate cover-letter upload field; the reviewed letter is filled as text where supported.";
      } else throw error;
    }
    if (!letterTarget && isLeverFinalProvider(packet.application_url)) {
      return {attached:0,ready:false,
        reason:"This Lever form has no separate cover-letter PDF upload. " +
          "The one-job two-PDF AutoApply contract cannot submit without " +
          "both attachments. Select a supported posting or complete this one manually."};
    }
    const docs = [{
      kind:"cv",target:cvTarget,sha256:packet.cv_pdf_sha256,size:packet.cv_pdf_size
    }];
    if (letterTarget) docs.push({
      kind:"letter",target:letterTarget,
      sha256:packet.letter_pdf_sha256,size:packet.letter_pdf_size
    });
    const ownedTabs = (await chrome.tabs.query({
      url:["https://smartploy.komplyint.fi/*","https://smartploy.obumai.com/*"]
    })).filter(item=>item?.id && isSmartPloyTab(item.url));
    if (ownedTabs.length !== 1) {
      throw new UploadError(
        "Keep exactly one signed-in SmartPloy tab open so " +
        "SmartPloy can retrieve your existing CV and letter automatically."
      );
    }
    const prepared = [];
    for (const doc of docs) {
      const [reply] = await chrome.scripting.executeScript({
        target:{tabId:ownedTabs[0].id},
        func:readOwnReviewedPdf,
        args:[{
          workspace_id:packet.workspace_id,kind:doc.kind,
          sha256:doc.sha256,size:doc.size
        }]
      });
      if (!reply?.result?.ready ||
          reply.result.sha256 !== doc.sha256 ||
          reply.result.size !== doc.size) {
        throw new UploadError(reply?.result?.reason ||
          "The reviewed PDF could not be verified against this application.");
      }
      prepared.push({...doc,...reply.result});
    }
    const domain = new URL(packet.application_url).hostname;
    if (!window.confirm(
      "ATTACH REVIEWED APPLICATION DOCUMENTS?\n\n" +
      packet.company + " — " + packet.role_title + "\n" +
      "Employer: " + domain + "\n" +
      prepared.map(x=>x.kind==="cv" ? "CV PDF" : "Cover-letter PDF").join(" + ") +
      "\n\nThese documents came from your CURRENT signed-in SmartPloy " +
      "application, and the employer website may upload each immediately. " +
      "This does NOT submit the application. Approve attachment?"
    )) return {attached:0,reason:"Document transfer not approved; attach manually."};
    let attached=0;
    for (const doc of prepared) {
      const again=await activeTab();
      validatePacket(currentPacketToJSON(),again.url);
      await requireVerifiedReview(chrome.storage?.session,packet);
      await requireFreshOwnerReview(packet);
      if (packet !== currentPacket || again.id !== tab.id ||
          again.url !== tab.url || await hasPriorLeverAttempt(packet)) {
        throw new UploadError("Selected job or tab changed; stop attachment.");
      }
      const [result] = await chrome.scripting.executeScript({
        target:{tabId:tab.id},func:attachReviewedPdf,
        args:[{
          application_url:packet.application_url,inspected_url:tab.url,
          ...doc.target,kind:doc.kind,
          file_name:doc.filename,size:doc.size,
          sha256:doc.sha256,base64:doc.base64
        }]
      });
      if (result?.result?.status !== "attached_locally") {
        return {attached,reason:result?.result?.reason ||
          "Attachment outcome uncertain. Inspect employer upload indicator; do not retry blindly."};
      }
      attached++;
    }
    return {attached,ready:attached===prepared.length,
      reason:attached+" reviewed PDF attachment(s) placed locally. " +
      (letterNote || "Check both employer upload indicators before finishing.")};
  } catch(error) {
    return {attached:0,reason:normalizeError(error)};
  }
}

/** One applicant-approved AutoApply preparation action:
 * exact employer → saved contact facts → current reviewed CV/letter PDF
 * attachments → unchanged profile answers → new-question handoff.
 * Never infer sensitive answers or auto-submit without separate rights.
 */
async function onStartAutoApply() {
  if (startAutoApplyInFlight) return;
  startAutoApplyInFlight = true;
  $("startAutoApply").disabled = true;
  // Failed scans cannot reuse approval or indices from an earlier form.
  currentPlan = null;
  currentQuestionPlan = null;
  currentPacket = null;
  targetTabId = null;
  inspectedUrl = "";
  try {
    await onInspect();
    if (!currentPacket || !currentPlan || targetTabId === null ||
        receiptOnly || attemptReserved) return;
    // On a question-only or upload-only form there are zero contacts to
    // mutate. Skip the unnecessary fill prompt, then review real questions.
    const filled = currentPlan.actions.length === 0 ? true : await onFill();
    if (!filled) return;
    const attachment = await autoAttachSavedDocuments();
    $("uploadInfo").textContent = attachment.reason;
    if (!attachment.ready) {
      status("The current CV and any dedicated cover-letter PDF must be attached " +
        "to the correct employer inputs before application automation can continue. " +
        (attachment.reason || "Review attachment status and resume manually."));
      return;
    }
    const reviewed=await onReviewQuestions();
    if (!reviewed || currentPacket === null || receiptOnly) return;
    // NEW/CHANGED ordinary questions or sensitive/consent controls require
    // applicant input and an explicit Finish click afterwards.
    if (reviewed.needsReview.length || reviewed.humanOnly.length) {
      status("AutoApply prepared your documents and existing profile answers. " +
        "Review these new or sensitive employer requirements, fill them truthfully, " +
        "then use Finish this one application. No final attempt was reserved.");
      return;
    }
    if (reviewed.questions.length) {
      const completed=await onFillQuestions();
      if (!completed) return;
    }
    // A complete supported Lever form can finish in this SAME Start call:
    // exact dry-run, fresh approval, one-use claim, single final click, receipt.
    if (isLeverFinalProvider(currentPacket.application_url)) {
      await onCompleteOneJob();
    } else {
      status("Reviewed CV, letter and known answers are prepared. " +
        "This employer uses a provider without independently authorized " +
        "automatic final submission; review and submit personally.");
    }
  } catch (error) {
    status(normalizeError(error));
  } finally {
    startAutoApplyInFlight = false;
    $("startAutoApply").disabled = false;
  }
}

async function onAttach() {
  if (receiptOnly || !currentPacket || targetTabId === null || attemptReserved) return;
  preflightPassed = false;
  $("submit").disabled = true;
  $("approve").checked = false;
  const file = $("cvFile").files?.[0];
  if (!file) { status("Select a reviewed SmartPloy CV PDF first."); return; }
  try {
    if (file.size > MAX_PDF_BYTES || file.size < 12) {
      throw new UploadError("The selected PDF must be 2 MiB or smaller.");
    }
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
    await requireFreshOwnerReview(currentPacket);
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new PacketError("Open and reinspect the exact reviewed employer form before attaching.");
    }
    if (await hasPriorLeverAttempt(currentPacket)) {
      throw new PacketError("An application attempt was already reserved. Do not alter or resend this form.");
    }
    const [inspection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: inspectForm
    });
    if (!inspection?.result || inspection.result.url !== tab.url ||
        inspection.result.allElementsCount > 250) {
      throw new PacketError("The employer form changed; attach the file manually.");
    }
    // Reuse SmartPloy's owner-scoped browser packet and active-tab browser
    // instead of starting another browser runner or storing private CV data.
    const target = chooseResumeField(inspection.result.elements);
    const bytes = new Uint8Array(await file.arrayBuffer());
    validatePdf(file.name, file.type, bytes);
    const digestBytes = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const digest = Array.from(digestBytes, b => b.toString(16).padStart(2, "0")).join("");
    if (digest !== currentPacket.cv_pdf_sha256 || bytes.length !== currentPacket.cv_pdf_size) {
      throw new UploadError(
        "This PDF differs from the approved SmartPloy CV export. Download the exact saved CV again."
      );
    }
    if ($("cvFile").files?.[0] !== file) {
      throw new PacketError("The selected PDF changed during local validation.");
    }
    // Transfer can trigger employer-site JS/XHR immediately. Consent to the
    // exact file, employer and target is required BEFORE any bytes are sent.
    if (!window.confirm(
      "SEND REVIEWED PDF TO EMPLOYER?\n\n" +
      currentPacket.company + " — " + currentPacket.role_title + "\n" +
      "File: " + file.name + " (" + file.size + " bytes)\n" +
      "SHA-256: " + digest + "\n\n" +
      "The employer website may transmit this file as soon as it is attached. " +
      "Check it contains only the intended CV. " +
      "This does NOT submit the application. Proceed?"
    )) return;
    const rechecked = await activeTab();
    validatePacket(currentPacketToJSON(), rechecked.url);
    if (rechecked.id !== targetTabId || rechecked.url !== tab.url ||
        $("cvFile").files?.[0] !== file) {
      throw new PacketError("The employer tab or selected PDF changed. Reinspect.");
    }
    // The applicant may have edited/revoked the profile or letter while the
    // confirm dialog was open. No employer upload without a fresh server check.
    await requireVerifiedReview(chrome.storage?.session,currentPacket);
    await requireFreshOwnerReview(currentPacket);
    const [reply] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: attachReviewedPdf,
      args: [{
        application_url: currentPacket.application_url,
        inspected_url: tab.url,
        ...target,
        file_name: file.name, size: bytes.length,
        sha256: digest, base64: encodePdfBase64(bytes)
      }]
    });
    const finding = reply?.result;
    // Never persist PDF data, hashes or filenames in chrome.storage.
    $("cvFile").value = "";
    $("uploadInfo").textContent = finding?.status === "attached_locally" ?
      "The PDF is present in the résumé field. Check the employer upload indicator. " +
      "This is NOT a verified server-side attachment or submitted application." :
      "Attachment not confirmed. Inspect the employer page before proceeding.";
    status(finding?.reason || "Attachment outcome is uncertain. Check the employer form.",
      finding?.status === "attached_locally");
    if (finding?.status !== "attached_locally") $("attach").disabled = true;
  } catch (error) {
    status(normalizeError(error));
  }
}

function currentPacketToJSON() {
  // Use the canonical original content for full schema/time verification.
  return $("packet").value;
}


/* Review and fill required employer-specific TEXT questions only.
   This does not produce or infer answers: the applicant types or pastes a
   checked answer (including any reviewed ObumAI draft) and approves transfer.
   Legal, visa, salary, EEO, consent and unsupported controls stay human-only. */
async function onReviewQuestions() {
  if (receiptOnly || !currentPacket || targetTabId === null || attemptReserved) return;
  currentQuestionPlan = null;
  $("questionPanel").hidden = true;
  $("questionList").replaceChildren();
  $("questionInfo").textContent = "";
  preflightPassed = false;
  $("submit").disabled = true;
  $("approve").checked = false;
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
    await requireFreshOwnerReview(currentPacket);
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new QuestionError("Open and reinspect the matching employer application before reviewing questions.");
    }
    if (await hasPriorLeverAttempt(currentPacket)) {
      throw new QuestionError("A submission was already attempted; do not change or repeat this form.");
    }
    const [reply] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: inspectForm
    });
    if (!reply?.result || reply.result.url !== tab.url ||
        reply.result.allElementsCount > 250) {
      throw new QuestionError("The employer form changed or is too large.");
    }
    const plan = planReviewedQuestions(reply.result.elements);
    const memory = suggestSavedAnswers(plan, currentPacket.saved_answers);
    currentQuestionPlan = { ...plan, url: tab.url,
      needsReview: memory.needsReview };
    $("questionInfo").textContent =
      plan.questions.length + " eligible required text questions; " +
      memory.reused + " answered from your approved saved profile; " +
      memory.needsReview.length + " NEW/CHANGED questions need an answer; " +
      plan.humanOnly.length + " require manual handling. " +
      (memory.needsReview.length ? "Check: " + memory.needsReview.slice(0, 6).join("; ") + ". " : "") +
      (plan.humanOnly.length ? "Manual: " + plan.humanOnly.slice(0, 6).join("; ") : "");
    const list = $("questionList");
    for (const [index, item] of plan.questions.entries()) {
      const fieldId = "approvedAnswer" + index;
      const wrapper = document.createElement("div");
      wrapper.className = "question-item";
      const label = document.createElement("label");
      label.textContent = item.label + (memory.values[index] ?
        " (saved profile answer · verify unchanged)" :
        " (new or changed · answer and save to your SmartPloy profile for next time)");
      label.setAttribute("for", fieldId);
      const input = document.createElement("textarea");
      input.id = fieldId;
      input.rows = 3;
      input.maxLength = item.max_answer_length;
      input.value = memory.values[index] || "";
      input.placeholder = "New/changed question. Type an accurate answer and save it once in My CV & documents.";
      input.autocomplete = "off";
      input.spellcheck = false;
      wrapper.append(label, input);
      list.append(wrapper);
    }
    $("questionPanel").hidden = plan.questions.length === 0;
    $("fillQuestions").disabled = plan.questions.length === 0;
    status(plan.questions.length ?
      "Review every proposed answer for accuracy, then approve a one-time fill. Sensitive questions remain manual." :
      "No safely eligible unanswered text questions. Answer employer-specific requirements manually.", true);
    return {...plan,needsReview:memory.needsReview};
  } catch (error) { status(normalizeError(error)); return null; }
}

async function onFillQuestions() {
  if (receiptOnly || !currentPacket || !currentQuestionPlan || attemptReserved ||
      $("questionPanel").hidden) return false;
  preflightPassed = false;
  $("submit").disabled = true;
  $("approve").checked = false;
  try {
    const values = currentQuestionPlan.questions.map((_, i) =>
      $("approvedAnswer" + i)?.value || "");
    const actions = validateReviewedAnswers(currentQuestionPlan, values);
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        currentQuestionPlan.url !== tab.url ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new QuestionError("The employer page changed. Reinspect the questions.");
    }
    if (!window.confirm(
      "FILL " + actions.length + " REVIEWED EMPLOYER ANSWERS?\n\n" +
      "You confirm the facts, claims, examples and employment details are truthful. " +
      "The employer site may transmit answer values when input/change events fire. " +
      "This will not click Submit, agree to terms, answer protected questions, " +
      "or retry after an uncertain outcome."
    )) return false;
    const again = await activeTab();
    validatePacket(currentPacketToJSON(), again.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
    await requireFreshOwnerReview(currentPacket);
    if (again.id !== targetTabId || again.url !== tab.url ||
        await hasPriorLeverAttempt(currentPacket)) {
      throw new QuestionError("Application state changed; do not retry until reinspection.");
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: fillReviewedAnswers,
      args: [actions, currentPacket.application_url, tab.url]
    });
    const finding = result?.result;
    // Remove plaintext immediately; no answers enter extension storage.
    currentQuestionPlan = null;
    $("questionList").replaceChildren();
    $("questionPanel").hidden = true;
    $("fillQuestions").disabled = true;
    $("questionInfo").textContent =
      "Review all answered questions in the employer form. Unknown or legally significant fields still need manual completion.";
    status(finding?.reason || "Answer result is uncertain. Inspect the employer form.",
      finding?.status === "filled_for_review");
    return finding?.status === "filled_for_review";
  } catch (error) { status(normalizeError(error)); return false; }
}

async function onPreflight() {
  if (receiptOnly || !currentPacket || targetTabId === null) return;
  preflightPassed = false;
  $("submit").disabled = true;
  if (!isLeverFinalProvider(currentPacket.application_url)) {
    $("preflight").textContent = "Automatic final submission is unavailable for this provider. Review all fields and submit yourself on the employer site.";
    status("Assisted form preparation only. No employer submit action authorized.");
    return;
  }
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    if (tab.id !== targetTabId) throw new PacketError("Return to the same employer browser tab.");
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: inspectFinalSubmit,
      args: [currentPacket.application_url]
    });
    if (!result?.result) throw new PacketError("Employer final-submit check did not complete.");
    const decision = result.result;
    // A locally complete employer form is not authorization. The first-party
    // server must already have burned ONE cross-device claim for the exact CV.
    let grantReady = false;
    if (decision.ready && !attemptReserved) {
      try {
        await requireOneUseFinalAttempt(chrome.storage?.session, currentPacket);
        const key = await oneAttemptKey(currentPacket);
        grantReady = !(await chrome.storage.local.get(key))[key];
      } catch {
        grantReady = false;
      }
    }
    preflightPassed = Boolean(decision.ready && grantReady);
    $("preflight").textContent = !decision.ready ?
      "Not ready: " + (decision.blockers || []).join("; ") :
      grantReady ?
      "One-use employer claim is recorded. Confirm the exact CV PDF, " +
      "all answers, legal statements and consent on the employer form." :
      "Employer form looks ready, but no valid one-use server claim exists. " +
      "Return to your signed-in SmartPloy tab and reserve the final action. " +
      "Then return here and recheck this form.";
    $("submit").disabled = !preflightPassed || !$("approve").checked;
    $("submit").setAttribute("aria-disabled", String($("submit").disabled));
    status(preflightPassed ?
      "Server-reserved employer attempt ready for your final click. Nothing sent yet." :
      "No one-use final-click authorization. Submit manually if needed.",
      preflightPassed);
  } catch (error) { status(normalizeError(error)); }
}

async function onSubmit() {
  // The single Start/Finish journey obtains the SAME explicit fresh consent
  // immediately before its server claim. Manual Submit keeps its checkbox
  // and separate modal. Neither mode can avoid the one-use server lock.
  const reviewedOneJobApproval=oneJobFinalApproval;
  oneJobFinalApproval=false;
  if (receiptOnly || !currentPacket || !preflightPassed ||
      (!$("approve").checked && !reviewedOneJobApproval) ||
      attemptReserved || targetTabId === null ||
      !isLeverFinalProvider(currentPacket.application_url)) return;
  if (!reviewedOneJobApproval && !window.confirm(
    "FINAL CONFIRMATION: CLICK THE EMPLOYER'S SUBMIT BUTTON ONCE?\n\n" +
    currentPacket.company + " — " + currentPacket.role_title + "\n\n" +
    "The reviewed applicant details and CV may be sent to this employer. " +
    "The attempt was already reserved across devices and can never be retried " +
    "automatically. A click is NOT proof the employer accepted the application. Proceed?"
  )) return;
  $("submit").disabled = true;
  $("submit").setAttribute("aria-disabled", "true");
  preflightPassed = false;
  oneJobSubmitWasAttempted = false;
  try {
    const packet = validateReviewPacket(currentPacketToJSON());
    const key = await oneAttemptKey(packet);
    const tab = await activeTab();
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactLeverForm(tab.url, packet.application_url)) {
      throw new PacketError("Employer tab or job changed. Do not risk a second attempt.");
    }
    if (!chrome.storage?.local || !chrome.storage?.session) {
      throw new PacketError("Durable local attempt protection unavailable.");
    }
    await withSubmissionLock(key, navigator.locks, async () => {
      await requireOneUseFinalAttempt(chrome.storage.session, packet);
      if ((await chrome.storage.local.get(key))[key]) {
        throw new PacketError("This employer attempt was already used. Do not retry.");
      }
      const stamp = {
        marker: "one_employer_submit_attempt_reserved_v1",
        recorded_at: new Date().toISOString(),
      };
      // Persist irreversible no-retry record BEFORE any employer-page action.
      // Never save CV, personal name/email, employer URL or a bearer token.
      await chrome.storage.local.set({[key]: stamp});
      if ((await chrome.storage.local.get(key))[key]?.marker !== stamp.marker) {
        throw new PacketError(
          "Local no-retry record could not be verified. Do not submit."
        );
      }
      attemptReserved = true;
      await consumeLocalFinalAttempt(chrome.storage.session, packet);
      const [result] = await chrome.scripting.executeScript({
        target: {tabId: tab.id}, world: "ISOLATED",
        func: submitReviewedLeverOnce,
        args: [{
          application_url: packet.application_url,
          cv_pdf_sha256: packet.cv_pdf_sha256,
          cv_pdf_size: packet.cv_pdf_size,
          letter_pdf_sha256: packet.letter_pdf_sha256,
          letter_pdf_size: packet.letter_pdf_size,
          email: packet.fields.email,
          full_name: packet.fields.full_name,
          cover_letter: packet.fields.cover_letter,
        }],
      });
      const finding = result?.result;
      if (!finding) throw new PacketError(
        "Employer outcome unknown. Attempt reserved; do not retry."
      );
      oneJobSubmitWasAttempted = finding.attempted === true;
      status(finding.attempted ?
        "One permitted employer final click was attempted. Check the " +
        "employer confirmation and save its reference. SmartPloy has NOT " +
        "verified provider acceptance." :
        "The final click was blocked (" + (finding.reason || "unknown") +
        "). The server attempt remains consumed; reconcile manually. " +
        "No automatic retry.", finding.attempted === true);
    });
  } catch (error) {
    status(normalizeError(error) +
      " If a server or local attempt was reserved, DO NOT retry.");
  }
}

/** ONE supported Lever job: exact reviewed profile and both current PDF
 * attachments -> dry-run all form controls -> user's one fresh final consent ->
 * first-party two-person-permitted sticky claim -> original one-use submit ->
 * exact same-job reference-bearing browser observation -> signed-in persistence.
 *
 * No permission shortcut, no background runner and never a blind second click.
 * If the employer does not issue a reference, report UNCERTAIN, not applied.
 */
async function onCompleteOneJob() {
  if (completingOneJob || receiptOnly || !currentPacket ||
      targetTabId === null || attemptReserved) return false;
  completingOneJob=true;
  $("finishOneJob").disabled=true;
  const packet=currentPacket;
  const fingerprint=$("packet").value;
  try {
    if (!isLeverFinalProvider(packet.application_url)) {
      status("One-job automatic final submit is currently supported only for authorized Lever applications. Review and submit other ATS forms personally.");
      return false;
    }
    const employer=await activeTab();
    validatePacket(fingerprint,employer.url);
    await requireVerifiedReview(chrome.storage?.session,packet);
    if (employer.id !== targetTabId || employer.url !== inspectedUrl ||
        !exactLeverForm(employer.url,packet.application_url) ||
        await hasPriorLeverAttempt(packet)) {
      throw new PacketError("The employer job/form changed or has an earlier attempt.");
    }
    // The exact final executor, not a weaker approximation, inspects every
    // input, submitted destination, both PDF bytes/digests, and CAPTCHA.
    const dry=async()=>{
      const [reply]=await chrome.scripting.executeScript({
        target:{tabId:employer.id},world:"ISOLATED",
        func:submitReviewedLeverOnce,
        args:[finalEmployerBinding(packet,true)]
      });
      return reply?.frameId === 0 && reply?.result?.preflight_ready === true ?
        {ready:true} :
        {ready:false,reason:reply?.result?.reason || "Employer form not ready"};
    };
    let readiness=await dry();
    if (!readiness.ready) {
      status("This exact employer form still needs attention: "+readiness.reason+
        ". Complete only the missing fields and use Finish this application.");
      return false;
    }
    if (!window.confirm(
      "COMPLETE THIS ONE REVIEWED JOB APPLICATION?\n\n" +
      packet.company + " — " + packet.role_title + "\n" +
      packet.application_url + "\n\n" +
      "SmartPloy has checked the matching profile, CV and cover-letter PDFs, " +
      "required fields, employer form and exact job. I personally confirm " +
      "that every claim, legal consent and answer is accurate and authorize " +
      "ONE irreversible final submit click. Employer permission must also " +
      "pass the independent server gate. A reserved attempt cannot be retried. " +
      "Proceed?"
    )) return false;
    const rechecked=await activeTab();
    if (rechecked.id !== employer.id || rechecked.url !== employer.url ||
        fingerprint !== $("packet").value || packet !== currentPacket) {
      throw new PacketError("Selected job or reviewed packet changed during final consent.");
    }
    await requireVerifiedReview(chrome.storage?.session,packet);
    await requireFreshOwnerReview(packet);
    readiness=await dry();
    if (!readiness.ready) {
      status("Form changed before the one-use server claim: "+readiness.reason);
      return false;
    }
    const firstParty=await signedInAppTab();
    const [response]=await chrome.scripting.executeScript({
      target:{tabId:firstParty.id},world:"ISOLATED",
      func:reserveFinalClickOnSmartPloy,
      args:[await finalOneJobClaimBinding(packet)]
    });
    const verdict=response?.result;
    if (response?.frameId !== 0 || verdict?.claim_reserved !== true) {
      status("Cannot complete this job: independent employer authorization " +
        "or current applicant review was not confirmed (" +
        (verdict?.reason || "unknown") + "). No submit attempted. " +
        "Check attempt status before any repeat.");
      return false;
    }
    // The server has NOW burned the one-use, cross-device attempt. Any
    // failure from this point is an UNKNOWN/NOT SENT outcome, never retry.
    await recordOneUseFinalAttempt(chrome.storage.session,packet,verdict);
    if (fingerprint !== $("packet").value || packet !== currentPacket ||
        (await activeTab()).id !== employer.id) {
      throw new PacketError("Application changed after server claim; no retry.");
    }
    preflightPassed=true;
    oneJobFinalApproval=true; // exactly the modal consent above, same call
    await onSubmit();         // original local WebLock + one-use server claim
    if (!oneJobSubmitWasAttempted) {
      status("One-use employer attempt was consumed, but the final click was " +
        "not confirmed. Inspect employer and SmartPloy attempt status. Never retry.");
      return false;
    }
    status("One final employer click made. Checking the exact job for an actual confirmation reference; no automatic retry.",true);
    // A real employer redirect can take a few seconds. Never infer success
    // from a click, a URL change alone or a generic thank-you page.
    let observed=false;
    for (let attempt=0;attempt<24;attempt++) {
      const open=await activeTab();
      if (open.id !== employer.id) break;
      if (exactReceiptPage(open.url,packet.application_url)) {
        await onReceipt();
        observed=Boolean($("receiptExport").value);
        break;
      }
      await new Promise(resolve=>setTimeout(resolve,450));
    }
    if (!observed) {
      status("The employer was clicked once, but NO verified same-job reference " +
        "was observed. Check its confirmation page or email and use Check " +
        "confirmation. Do not submit again.");
      return false;
    }
    const evidence=JSON.parse($("receiptExport").value);
    if (!window.confirm(
      "RECORD THE EMPLOYER CONFIRMATION?\n\n" +
      packet.company + " — " + packet.role_title + "\n" +
      "Visible employer reference: " + evidence.reference + "\n\n" +
      "I have personally inspected the matching employer confirmation page " +
      "and confirm this exact reference is visible. Save the browser-observed " +
      "receipt to my signed-in SmartPloy application? " +
      "This does NOT claim an independently verified provider acknowledgment."
    )) {
      status("Reference-bearing employer confirmation observed, but not " +
        "saved to SmartPloy. You can copy the observation below.");
      return false;
    }
    const appTab=await signedInAppTab();
    const [result]=await chrome.scripting.executeScript({
      target:{tabId:appTab.id},world:"ISOLATED",
      func:saveOneObservedReceiptOnSmartPloy,
      args:[{workspace_id:packet.workspace_id,receipt:evidence,
        confirm_user_observed:true}]
    });
    if (result?.frameId !== 0 || result?.result?.saved !== true) {
      status("Employer confirmation observed, but account recording " +
        "was not confirmed ("+(result?.result?.reason || "unknown")+
        "). Check the current application receipt before taking any action; never resubmit.");
      return false;
    }
    status("ONE JOB COMPLETE: exact employer confirmation reference " +
      evidence.reference + " was observed and recorded in SmartPloy. " +
      "External provider API acknowledgment remains unverified.",true);
    return true;
  } catch(error) {
    status("One-job AutoApply outcome incomplete or uncertain: "+
      normalizeError(error)+". Do not retry a reserved attempt.");
    return false;
  } finally {
    completingOneJob=false;
    oneJobFinalApproval=false;
    $("finishOneJob").disabled=false;
  }
}

async function onResumeReceipt() {
  clearReceiptObservation();
  const resumeSequence = receiptCheckSequence;
  enterReceiptMode();
  try {
    const tab = await activeTab();
    const packetText = $("packet").value;
    const pkt = validateReviewPacket(packetText);
    if (!exactReceiptPage(tab.url, pkt.application_url)) {
      throw new PacketError("Open the exact reviewed job's confirmation, not another posting or a general thank-you page.");
    }
    // Manual observation never reserves, consumes or invents a final claim.
    // Existing one-attempt Lever recovery remains available after that click.
    const priorAttempt = await hasPriorLeverAttempt(pkt);
    if (!priorAttempt) await requireVerifiedReview(chrome.storage?.session, pkt);
    if (resumeSequence !== receiptCheckSequence || packetText !== $("packet").value) {
      throw new PacketError("The reviewed packet changed. Inspect the matching application again.");
    }
    currentPacket = pkt;
    targetTabId = tab.id;
    inspectedUrl = tab.url;
    attemptReserved = priorAttempt;
    $("submission").hidden = false;
    $("receipt").disabled = false;
    await onReceipt();
  } catch (error) { status(normalizeError(error)); }
}

async function onReceipt() {
  clearReceiptObservation();
  enterReceiptMode();
  const packet = currentPacket;
  const packetText = $("packet").value;
  const checkSequence = receiptCheckSequence;
  if (!packet || targetTabId === null) return;
  try {
    const tab = await activeTab();
    if (tab.id !== targetTabId || !exactReceiptPage(tab.url, packet.application_url)) {
      throw new PacketError("Return to the confirmation for this exact employer job.");
    }
    const current = validateReviewPacket(packetText);
    if (JSON.stringify(current) !== JSON.stringify(packet)) {
      throw new PacketError("The reviewed application packet changed; do not import a receipt.");
    }
    const priorAttempt = await hasPriorLeverAttempt(packet);
    if (!priorAttempt) {
      await requireVerifiedReview(chrome.storage?.session, packet);
      const host = new URL(packet.application_url).hostname;
      const provider = isLeverFinalProvider(packet.application_url) ? "LEVER" :
        host === "jobs.ashbyhq.com" ? "ASHBY" : "GREENHOUSE";
      if (!window.confirm(
        "OBSERVE MANUAL " + provider + " APPLICATION CONFIRMATION?\n\n" +
        "You confirm you personally clicked the employer's Submit button " +
        "and can see a reference-bearing confirmation for this exact job. " +
        "SmartPloy will only save an UNVERIFIED browser observation, not " +
        "assert the employer accepted the application. No submission or retry is performed."
      )) return;
    }
    const [result] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, world: "ISOLATED", func: inspectReceipt,
      args: [packet.application_url]
    });
    const finding = result?.result;
    if (result?.frameId !== 0 || !finding) {
      throw new PacketError("Could not inspect the visible employer confirmation.");
    }
    const again = await activeTab();
    if (checkSequence !== receiptCheckSequence || currentPacket !== packet ||
        packetText !== $("packet").value || again.id !== tab.id || again.url !== tab.url) {
      throw new PacketError("The application or employer tab changed; inspect the matching confirmation again.");
    }
    // Neither expiry during the scan nor a changed contact/CV packet may
    // carry an old signed-in review into a new manual observation.
    validateReviewPacket(packetText);
    if (!priorAttempt) await requireVerifiedReview(chrome.storage?.session, packet);
    const finalTab = await activeTab();
    if (checkSequence !== receiptCheckSequence || currentPacket !== packet ||
        packetText !== $("packet").value || finalTab.id !== tab.id || finalTab.url !== tab.url) {
      throw new PacketError("The reviewed application or employer tab changed during confirmation inspection.");
    }
    if (finding.confirmed) {
      if (!exactReceiptPage(finding.confirmation_page_url, packet.application_url)) {
        throw new PacketError("The observed confirmation belongs to another employer job.");
      }
      const receipt = {
        schema: "smartploy.browser_receipt.v1",
        workspace_id: packet.workspace_id,
        document_revision: packet.revision,
        document_sha256: packet.document_sha256,
        application_url: packet.application_url,
        confirmation_page_url: finding.confirmation_page_url,
        reference: finding.reference,
        confirmation_page_sha256: finding.confirmation_page_sha256,
        observed_at: new Date().toISOString(),
        confirmed_visible: true,
      };
      $("receiptExport").value = JSON.stringify(receipt);
      $("receiptPanel").hidden = false;
    }
    status(
      finding.explanation + (finding.reference ? " Reference: " + finding.reference : ""),
      finding.confirmed
    );
  } catch (error) { status(normalizeError(error)); }
}

$("verifyReview").addEventListener("click", () => void onVerifySmartPloyReview());
$("reserveFinal").addEventListener("click", () => void onReserveFinalAttempt());
$("inspect").addEventListener("click", () => void onInspect());
$("startAutoApply").addEventListener("click", () => void onStartAutoApply());
$("finishOneJob").addEventListener("click", () => void onCompleteOneJob());
$("resume").addEventListener("click", () => void onResumeReceipt());
$("fill").addEventListener("click", () => void onFill());
$("attach").addEventListener("click", () => void onAttach());
$("reviewQuestions").addEventListener("click", () => void onReviewQuestions());
$("fillQuestions").addEventListener("click", () => void onFillQuestions());
$("check").addEventListener("click", () => void onPreflight());
$("submit").addEventListener("click", () => void onSubmit());
$("receipt").addEventListener("click", () => void onReceipt());
$("copyReceipt").addEventListener("click", async () => {
  const value = $("receiptExport").value;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    status("Observed receipt copied. Return to the matching SmartPloy application and select Import observed receipt.", true);
  } catch {
    $("receiptExport").select();
    status("Clipboard access unavailable. Select and copy the receipt text yourself.");
  }
});
$("approve").addEventListener("change", () => {
  $("submit").disabled = receiptOnly || !preflightPassed || !$("approve").checked || attemptReserved;
  $("submit").setAttribute("aria-disabled", String($("submit").disabled));
});
$("packet").addEventListener("input", () => {
  clearReceiptObservation();
  receiptOnly = false;
  currentPacket = null; currentPlan = null; currentQuestionPlan = null; targetTabId = null;
  preflightPassed = false; attemptReserved = false;
  $("plan").hidden = true; $("submission").hidden = true; $("receiptPanel").hidden = true;
  $("cvFile").value = ""; $("uploadInfo").textContent = ""; $("attach").disabled = false;
  $("reserveFinal").disabled = false; $("check").disabled = false;
  $("approve").disabled = false; $("resume").disabled = false;
  $("receipt").disabled = false;
  $("questionList").replaceChildren(); $("questionPanel").hidden = true;
  $("questionInfo").textContent = ""; $("fillQuestions").disabled = true;
  $("receiptExport").value = "";
  $("reviewInfo").textContent = "";
  $("approve").checked = false; $("submit").disabled = true;
  $("feedback").textContent = "";
});
