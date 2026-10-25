/* SmartPloy owner-operated browser companion popup.
   No background automation, no external API calls, no raw profile persistence.
   The final action is only possible after an exact one-job approval. */
import { PacketError, planFields, validatePacket } from "./logic.mjs";
import { UploadError, chooseResumeField, encodePdfBase64, exactLeverForm, exactAssistedForm, isLeverFinalProvider, MAX_PDF_BYTES, validatePdf } from "./upload.mjs";
import { attachReviewedPdf } from "./page-attachment.mjs";
import { QuestionError, planReviewedQuestions, validateReviewedAnswers } from "./questions.mjs";
import { fillReviewedAnswers } from "./page-questions.mjs";
import { AttemptError, oneAttemptKey, withSubmissionLock } from "./attempt-lock.mjs";
import {
  approvedFieldsSha256, isSmartPloyTab, recordVerifiedReview,
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
function fillPlanned(actions, exactUrl) {
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
  if (!sameJob(location.href, exactUrl)) {
    return { filled: 0, skipped: actions.length, blocker: "Employer page changed since packet approval." };
  }
  if (!Array.isArray(actions) || actions.length > 120) {
    return { filled: 0, skipped: 0, blocker: "Too many fields to fill safely." };
  }
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  let filled = 0, skipped = 0;
  if (all.length > 250) {
    return {filled:0,skipped:actions.length,blocker:"Employer form is too large; inspect manually."};
  }
  const seen = new Set();
  for (const action of actions) {
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
      if (el.value !== action.value) { skipped++; continue; }
      filled++;
      const after = Array.from(document.querySelectorAll("input,textarea,select"));
      if (!el.isConnected || after.length !== all.length ||
          after[action.index] !== el || labelFor(el) !== action.label ||
          unsafeMetadata(el) || (el.id || "") !== action.expected_id ||
          (el.name || "") !== action.expected_name) {
        return {filled,skipped,blocker:"Employer form changed after contact field input. Review manually without retry."};
      }
    } catch {
      return {filled,skipped,blocker:"Contact field fill outcome is uncertain. Review manually without retry."};
    }
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

async function inspectReceipt(expectedOrigin, expectedAccount) {
  const here = new URL(location.href);
  if (
    here.origin !== expectedOrigin ||
    !here.pathname.startsWith("/" + expectedAccount + "/")
  ) {
    return { confirmed: false, explanation: "The browser is not at the original employer origin." };
  }
  const text = String(document.body?.innerText || "").slice(0, 20000)
    .replace(/\s+/g, " ");
  const proof = /(?:application (?:has been )?(?:submitted|received)|submission (?:is )?confirmed|thank you for (?:your )?(?:application|applying)|we have received your application)/i.test(text);
  const reference = text.match(/(?:reference|confirmation|application|submission)\s*(?:id|number|no\.?|#)?\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]{3,63})/i)?.[1] || "";
  const stillSubmit = Array.from(document.querySelectorAll("button,input[type=submit]")).some((el) =>
    /^(submit application|send application)$/i.test(String(el.innerText || el.value || "").trim()) &&
    el.getClientRects().length > 0 && !el.disabled
  );
  const confirmed = proof && Boolean(reference) && !stillSubmit;
  const hashBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  const pageHash = Array.from(new Uint8Array(hashBytes))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
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

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new PacketError("Open the employer job page first.");
  return tab;
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
    const [reply] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, world: "ISOLATED",
      func: verifyReviewOnSmartPloy,
      args: [{
        workspace_id: packet.workspace_id,
        expected_revision: packet.revision,
        expected_document_sha256: packet.document_sha256,
        expected_cv_pdf_sha256: packet.cv_pdf_sha256,
        expected_fields_sha256: await approvedFieldsSha256(packet.fields),
        expected_application_url_sha256: await sha256Text(packet.application_url),
        expected_cv_pdf_size: packet.cv_pdf_size
      }]
    });
    if (reply?.frameId !== 0 || !reply?.result?.review_verified) {
      throw new PacketError(
        "SmartPloy could not verify the signed-in exact CV/job review. " +
        "Record it in My applications and try again."
      );
    }
    const saved = await recordVerifiedReview(chrome.storage.session, packet, reply.result);
    $("reviewInfo").textContent =
      "Signed-in review verified until " + new Date(saved.expires_at).toLocaleTimeString() +
      (isLeverFinalProvider(packet.application_url)
        ? ". Open the exact employer form. A one-use final click requires separate employer permission."
        : ". Open the exact Ashby form. Final submission must be done by you.");
    status("Only a short-lived review fingerprint is in extension memory. No login token or CV was saved.", true);
  } catch (error) {
    $("reviewInfo").textContent = "Review not verified. Assisted form filling remains disabled.";
    status(normalizeError(error));
  }
}

async function onReserveFinalAttempt() {
  $("finalClaimInfo").textContent = "";
  try {
    const packet = validateReviewPacket($("packet").value);
    if (!isLeverFinalProvider(packet.application_url)) {
      throw new PacketError("Ashby is assisted-fill ONLY. Submit manually on the employer's form; no browser final claim is available.");
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
  try {
    const tab = await activeTab();
    const pkt = validatePacket($("packet").value, tab.url);
    await requireVerifiedReview(chrome.storage?.session, pkt);
    if (!exactAssistedForm(tab.url, pkt.application_url)) {
      throw new PacketError("Open the exact approved employer application form, not its job description.");
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: inspectForm
    });
    if (!result?.result || result.result.url !== tab.url || result.result.allElementsCount > 250) {
      throw new PacketError("The employer form is dynamic or too large. Please fill it manually.");
    }
    const candidate = planFields(result.result.elements, pkt);
    if (!candidate.actions.length && !candidate.skippedUploads.length) {
      throw new PacketError("No supported empty fields or file inputs were found. Fill this application manually.");
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
    $("plan").hidden = false;
    $("submission").hidden = candidate.actions.length > 0;
    const leverSubmit = isLeverFinalProvider(pkt.application_url);
    $("reserveFinal").disabled = !leverSubmit;
    $("check").disabled = !leverSubmit;
    $("approve").disabled = !leverSubmit;
    $("resume").disabled = !leverSubmit;
    $("receipt").disabled = !leverSubmit;
    $("finalClaimInfo").textContent = leverSubmit ? "" :
      "Ashby: reviewed contacts, questions and PDF attachment only. " +
      "Finish and submit personally on the employer site; no automatic final click.";
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
  } catch (error) { status(normalizeError(error)); }
}

async function onFill() {
  if (!currentPacket || !currentPlan) return;
  if (!window.confirm(
    "Fill only the displayed approved fields on the selected employer page? " +
    "No documents will be uploaded and no application will be submitted."
  )) return;
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
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
  } catch (error) { status(normalizeError(error)); }
}

async function onAttach() {
  if (!currentPacket || targetTabId === null || attemptReserved) return;
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
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new PacketError("Open and reinspect the exact reviewed employer form before attaching.");
    }
    const attemptKey = await oneAttemptKey(currentPacket);
    if ((await chrome.storage.local.get(attemptKey))[attemptKey]) {
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
  if (!currentPacket || targetTabId === null || attemptReserved) return;
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
    if (tab.id !== targetTabId || tab.url !== inspectedUrl ||
        !exactAssistedForm(tab.url, currentPacket.application_url)) {
      throw new QuestionError("Open and reinspect the matching employer application before reviewing questions.");
    }
    const key = await oneAttemptKey(currentPacket);
    if ((await chrome.storage.local.get(key))[key]) {
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
    currentQuestionPlan = { ...plan, url: tab.url };
    $("questionInfo").textContent =
      plan.questions.length + " eligible required text questions; " +
      plan.humanOnly.length + " require manual handling. " +
      (plan.humanOnly.length ? "Manual: " + plan.humanOnly.slice(0, 6).join("; ") : "");
    const list = $("questionList");
    for (const [index, item] of plan.questions.entries()) {
      const fieldId = "approvedAnswer" + index;
      const wrapper = document.createElement("div");
      wrapper.className = "question-item";
      const label = document.createElement("label");
      label.textContent = item.label + " (review required)";
      label.setAttribute("for", fieldId);
      const input = document.createElement("textarea");
      input.id = fieldId;
      input.rows = 3;
      input.maxLength = item.max_answer_length;
      input.placeholder = "Type or paste a truthful answer you have reviewed.";
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
  } catch (error) { status(normalizeError(error)); }
}

async function onFillQuestions() {
  if (!currentPacket || !currentQuestionPlan || attemptReserved ||
      $("questionPanel").hidden) return;
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
    )) return;
    const again = await activeTab();
    validatePacket(currentPacketToJSON(), again.url);
    await requireVerifiedReview(chrome.storage?.session, currentPacket);
    const key = await oneAttemptKey(currentPacket);
    if (again.id !== targetTabId || again.url !== tab.url ||
        (await chrome.storage.local.get(key))[key]) {
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
  } catch (error) { status(normalizeError(error)); }
}

async function onPreflight() {
  if (!currentPacket || targetTabId === null) return;
  preflightPassed = false;
  $("submit").disabled = true;
  if (!isLeverFinalProvider(currentPacket.application_url)) {
    $("preflight").textContent = "Ashby automatic final submission is unavailable. Review all fields and submit yourself on the employer site.";
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
  if (!currentPacket || !preflightPassed || !$("approve").checked ||
      attemptReserved || targetTabId === null ||
      !isLeverFinalProvider(currentPacket.application_url)) return;
  if (!window.confirm(
    "FINAL CONFIRMATION: CLICK THE EMPLOYER'S SUBMIT BUTTON ONCE?\n\n" +
    currentPacket.company + " — " + currentPacket.role_title + "\n\n" +
    "The reviewed applicant details and CV may be sent to this employer. " +
    "The attempt was already reserved across devices and can never be retried " +
    "automatically. A click is NOT proof the employer accepted the application. Proceed?"
  )) return;
  $("submit").disabled = true;
  $("submit").setAttribute("aria-disabled", "true");
  preflightPassed = false;
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
          email: packet.fields.email,
          full_name: packet.fields.full_name,
          cover_letter: packet.fields.cover_letter,
        }],
      });
      const finding = result?.result;
      if (!finding) throw new PacketError(
        "Employer outcome unknown. Attempt reserved; do not retry."
      );
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

async function onResumeReceipt() {
  try {
    const tab = await activeTab();
    // The confirmation page can differ from the original job path after
    // submission. Validate full packet signature/expiry against its OWN
    // canonical job URL, then separately require matching employer+account.
    const original = JSON.parse($("packet").value);
    const pkt = validatePacket(original, original.application_url);
    if (!isLeverFinalProvider(pkt.application_url)) {
      throw new PacketError("Only approved Lever one-use attempts have browser-managed receipts. Ashby submissions are user-reported.");
    }
    const initial = new URL(pkt.application_url);
    const here = new URL(tab.url);
    const account = initial.pathname.split("/")[1];
    if (here.origin !== initial.origin || !here.pathname.startsWith("/" + account + "/")) {
      throw new PacketError("This confirmation is not on the original Lever employer account.");
    }
    const key = await oneAttemptKey(pkt);
    const stored = await chrome.storage.local.get(key);
    if (!stored[key]) {
      throw new PacketError("No matching one-time submission attempt was recorded. You may still report a manual submission.");
    }
    currentPacket = pkt;
    targetTabId = tab.id;
    inspectedUrl = tab.url;
    currentPlan = null;
    attemptReserved = true;
    preflightPassed = false;
    $("submission").hidden = false;
    $("approve").checked = false;
    $("submit").disabled = true;
    await onReceipt();
  } catch (error) { status(normalizeError(error)); }
}

async function onReceipt() {
  if (!currentPacket || targetTabId === null) return;
  if (!isLeverFinalProvider(currentPacket.application_url)) {
    status("Ashby browser receipts are not supported. After submitting manually, report the result in SmartPloy.");
    return;
  }
  try {
    const tab = await activeTab();
    if (tab.id !== targetTabId) throw new PacketError("Return to the employer page where you applied.");
    const original = new URL(currentPacket.application_url);
    const account = original.pathname.split("/")[1];
    const [result] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: inspectReceipt, args: [original.origin, account]
    });
    const finding = result?.result;
    if (!finding) throw new PacketError("Could not inspect the visible employer confirmation.");
    if (finding.confirmed) {
      const key = await oneAttemptKey(currentPacket);
      const prior = await chrome.storage.local.get(key);
      if (!prior[key]) {
        throw new PacketError(
          "No matching companion submission attempt was recorded. Do not treat this as verified; you may still report it manually."
        );
      }
      const receipt = {
        schema: "smartploy.browser_receipt.v1",
        workspace_id: currentPacket.workspace_id,
        document_revision: currentPacket.revision,
        document_sha256: currentPacket.document_sha256,
        application_url: currentPacket.application_url,
        confirmation_page_url: finding.confirmation_page_url,
        reference: finding.reference,
        confirmation_page_sha256: finding.confirmation_page_sha256,
        observed_at: new Date().toISOString(),
        confirmed_visible: true,
      };
      $("receiptExport").value = JSON.stringify(receipt);
      $("receiptPanel").hidden = false;
    } else {
      $("receiptPanel").hidden = true;
      $("receiptExport").value = "";
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
  $("submit").disabled = !preflightPassed || !$("approve").checked || attemptReserved;
  $("submit").setAttribute("aria-disabled", String($("submit").disabled));
});
$("packet").addEventListener("input", () => {
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
