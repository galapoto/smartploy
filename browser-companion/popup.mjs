/* SmartPloy owner-operated browser companion popup.
   No background automation, no external API calls, no raw profile persistence.
   The final action is only possible after an exact one-job approval. */
import { PacketError, planFields, validatePacket } from "./logic.mjs";

const $ = (id) => document.getElementById(id);
let targetTabId = null;
let currentPacket = null;
let currentPlan = null;
let inspectedUrl = "";
let preflightPassed = false;
let attemptReserved = false;

function status(message, success = false) {
  $("feedback").className = success ? "success" : "error";
  $("feedback").textContent = message;
}

function normalizeError(error) {
  if (error instanceof PacketError) return error.message;
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
      hasValue, maxLength: Number(el.maxLength) || -1
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
    if (el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" &&
      el.getClientRects().length > 0;
  }
  function sameJob(a, b) {
    try {
      const x = new URL(a), y = new URL(b);
      const prefix = y.pathname.replace(/\/+$/, "");
      return x.origin === y.origin && (
        x.pathname === prefix || x.pathname === prefix + "/" ||
        x.pathname.startsWith(prefix + "/")
      );
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
  for (const action of actions) {
    if (!Number.isInteger(action.index) || action.index < 0 || action.index >= all.length) {
      skipped++; continue;
    }
    const el = all[action.index];
    const type = el.tagName === "TEXTAREA" ? "textarea" :
      el.tagName === "SELECT" ? "select" : (el.type || "text").toLowerCase();
    if (
      (el.id || "") !== action.expected_id ||
      (el.name || "") !== action.expected_name ||
      type !== action.expected_type ||
      !visible(el) || el.disabled || el.readOnly ||
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
    } catch {
      skipped++;
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
  if (!fileInputs.some((row) => row.hasFile)) {
    blockers.push("Attach the CV or résumé document on the employer's site before submission.");
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
function submitOnce(exactUrl) {
  const here = new URL(location.href);
  const expected = new URL(exactUrl);
  const path = expected.pathname.replace(/\/+$/, "");
  if (here.origin !== expected.origin || !here.pathname.startsWith(path) ||
      !["jobs.lever.co", "jobs.eu.lever.co"].includes(here.hostname) ||
      !/\/apply\/?$/.test(here.pathname)) {
    return { status: "blocked", reason: "Employer form changed. Submission was not attempted." };
  }
  const all = Array.from(document.querySelectorAll('button,input[type="submit"]'));
  const live = all.filter((el) => {
    const a = String(el.innerText || el.value || el.getAttribute("aria-label") || "")
      .replace(/\s+/g, " ").trim().toLowerCase();
    return ["submit application", "send application", "lähetä hakemus", "skicka ansökan"].includes(a) &&
      !el.disabled && el.getClientRects().length > 0 && el.closest("form");
  });
  if (live.length !== 1) return { status: "blocked", reason: "Final button is missing or ambiguous." };
  const required = Array.from(document.querySelectorAll("input[required],textarea[required],select[required]"));
  for (const el of required) {
    if (el.disabled || el.closest("[hidden],[inert]")) continue;
    const type = String(el.type || "").toLowerCase();
    const present = type === "file" ? Boolean(el.files?.length) :
      ["checkbox", "radio"].includes(type) ? Boolean(el.checked) : Boolean(String(el.value || "").trim());
    if (!present || (el.validity && !el.validity.valid)) {
      return { status: "blocked", reason: "An employer-required field remains incomplete." };
    }
  }
  if (!Array.from(document.querySelectorAll('input[type="file"]')).some((el) => Boolean(el.files?.length))) {
    return { status: "blocked", reason: "Attach your CV manually before submitting." };
  }
  try {
    live[0].click();
    return { status: "attempted_unverified", reason: "One final-submit click was sent. Employer acceptance is not yet confirmed." };
  } catch {
    return { status: "ambiguous", reason: "Browser click outcome is uncertain. Do not retry before checking the employer." };
  }
}

async function inspectReceipt(expectedOrigin) {
  const here = new URL(location.href);
  if (here.origin !== expectedOrigin) {
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

async function onInspect() {
  try {
    const tab = await activeTab();
    const pkt = validatePacket($("packet").value, tab.url);
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: inspectForm
    });
    if (!result?.result || result.result.url !== tab.url || result.result.allElementsCount > 250) {
      throw new PacketError("The employer form is dynamic or too large. Please fill it manually.");
    }
    const candidate = planFields(result.result.elements, pkt);
    if (!candidate.actions.length) {
      throw new PacketError("No supported empty fields were found. Fill this application manually.");
    }
    targetTabId = tab.id;
    currentPacket = pkt;
    inspectedUrl = tab.url;
    currentPlan = candidate;
    preflightPassed = false;
    attemptReserved = false;
    $("plan").hidden = false;
    $("submission").hidden = true;
    $("approve").checked = false;
    $("submit").disabled = true;
    $("job").textContent = pkt.role_title + " — " + pkt.company;
    $("summary").textContent =
      candidate.actions.length + " approved contact/cover-letter fields can be filled. " +
      candidate.skippedUploads.length + " file inputs must be handled manually.";
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
    status("Review the proposed fields, then click Fill. No employer data was changed.", true);
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
    if (tab.id !== targetTabId || tab.url !== inspectedUrl) {
      throw new PacketError("Reinspect after changing employer tab or URL.");
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillPlanned,
      args: [currentPlan.actions, currentPacket.application_url]
    });
    if (!result?.result) throw new PacketError("Employer form did not return fill verification");
    if (result.result.blocker) throw new PacketError(result.result.blocker);
    $("submission").hidden = false;
    preflightPassed = false;
    status(
      "Filled " + result.result.filled + " fields (" + result.result.skipped +
      " skipped). Review every value and manually attach CV before submission.", true
    );
  } catch (error) { status(normalizeError(error)); }
}

function currentPacketToJSON() {
  // Use the canonical original content for full schema/time verification.
  return $("packet").value;
}

async function onPreflight() {
  if (!currentPacket || targetTabId === null) return;
  preflightPassed = false;
  $("submit").disabled = true;
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
    preflightPassed = Boolean(decision.ready) && !attemptReserved;
    $("preflight").textContent = decision.ready ?
      "Required fields and résumé attachment appear complete. Carefully check consent statements, questions and uploaded document before choosing Submit." :
      "Not ready: " + (decision.blockers || []).join("; ");
    $("submit").disabled = !preflightPassed || !$("approve").checked;
    status(decision.ready ?
      "Preflight passed. No final action has happened. Separate approval is still required." :
      "Preflight blocked. Complete the form or submit manually.", Boolean(decision.ready));
  } catch (error) { status(normalizeError(error)); }
}

async function oneAttemptKey(packet) {
  const material = [
    packet.application_url, packet.workspace_id, packet.revision, packet.document_sha256
  ].join("\0");
  const data = new TextEncoder().encode(material);
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  return "smartploy.submit." + [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function onSubmit() {
  if (!currentPacket || !preflightPassed || !($("approve").checked) || attemptReserved) return;
  try {
    const tab = await activeTab();
    validatePacket(currentPacketToJSON(), tab.url);
    if (tab.id !== targetTabId) throw new PacketError("The employer tab changed. Inspect again.");
    if (!window.confirm(
      "FINAL APPROVAL: Click the employer's 'Submit application' button ONCE for " +
      currentPacket.role_title + " at " + currentPacket.company + "?\n\n" +
      "This may send personal information and your uploaded CV to the employer. " +
      "You will not be able to undo that submission. SmartPloy will not retry automatically."
    )) return;
    const fresh = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: inspectFinalSubmit,
      args: [currentPacket.application_url]
    });
    if (!fresh?.[0]?.result?.ready) {
      throw new PacketError("Employer form readiness changed. Check required fields again.");
    }
    const key = await oneAttemptKey(currentPacket);
    const existing = await chrome.storage.local.get(key);
    if (existing[key]) {
      throw new PacketError("This job/application was already attempted by the companion. Check the employer for a receipt; no retry.");
    }
    // Reserve BEFORE the consequential click. A browser crash will leave the
    // attempt ambiguous, never silently click a second time.
    await chrome.storage.local.set({[key]: {
      attempted_at: new Date().toISOString(),
      state: "reserved_unverified"
    }});
    attemptReserved = true;
    preflightPassed = false;
    $("submit").disabled = true;
    const [result] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: submitOnce,
      args: [currentPacket.application_url]
    });
    const verdict = result?.result;
    status(verdict?.reason || "Submission outcome is uncertain; do not repeat the click.",
      verdict?.status === "attempted_unverified");
    $("preflight").textContent =
      "Submission attempt reserved. Check the employer website for an application receipt or reference.";
  } catch (error) {
    status(normalizeError(error));
  }
}

async function onReceipt() {
  if (!currentPacket || targetTabId === null) return;
  try {
    const tab = await activeTab();
    if (tab.id !== targetTabId) throw new PacketError("Return to the employer page where you applied.");
    const expectedOrigin = new URL(currentPacket.application_url).origin;
    const [result] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: inspectReceipt, args: [expectedOrigin]
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

$("inspect").addEventListener("click", () => void onInspect());
$("fill").addEventListener("click", () => void onFill());
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
  $("submit").disabled = !$("approve").checked || !preflightPassed || attemptReserved;
});
$("packet").addEventListener("input", () => {
  currentPacket = null; currentPlan = null; targetTabId = null;
  preflightPassed = false; attemptReserved = false;
  $("plan").hidden = true; $("submission").hidden = true; $("receiptPanel").hidden = true;
  $("receiptExport").value = "";
  $("approve").checked = false; $("submit").disabled = true;
  $("feedback").textContent = "";
});
