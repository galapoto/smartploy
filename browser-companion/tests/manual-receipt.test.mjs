/* SP47: execute the real popup's registered events, including review checks.
   Only the Chrome boundary and confirmation DOM result are synthetic. No
   employer, API, claim-reservation, upload or final-click call is permitted. */
import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { oneAttemptKey } from "../attempt-lock.mjs";
import { exactReceiptPage } from "../upload.mjs";
import {
  recordVerifiedReview, reviewSessionKey, validateReviewPacket,
} from "../review-bridge.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

const LEVER = "https://jobs.lever.co/synthetic-fi/analyst-123/apply";
const ASHBY = "https://jobs.ashbyhq.com/synthetic-fi/analyst-123/application";
const GREENHOUSE = "https://boards.greenhouse.io/synthetic-fi/jobs/123456";
let moduleNumber = 0;

function packet(applicationUrl) {
  const now = Date.now();
  return {
    schema: "smartploy.browser_handoff.v2",
    workspace_id: "kit-" + "a".repeat(30), revision: 2,
    issued_at: new Date(now - 1000).toISOString(),
    expires_at: new Date(now + 10 * 60_000).toISOString(),
    document_sha256: "b".repeat(64), cv_pdf_sha256: "c".repeat(64),
    cv_pdf_size: 23456, application_url: applicationUrl,
    company: "Synthetic Employer", role_title: "Synthetic Analyst",
    fields: {
      full_name: "Synthetic Applicant", first_name: "Synthetic",
      last_name: "Applicant", email: "applicant@example.invalid",
      phone: "", location: "", linkedin: "", github: "",
      cover_letter: "I personally reviewed this synthetic application text.",
    },
    privacy: {
      approved_contact_only: true, original_cv_included: false,
      employer_submit_allowed_without_new_approval: false,
    },
  };
}

function memoryStorage() {
  const entries = new Map();
  return {
    entries, writes: 0,
    async get(key) { return { [key]: entries.get(key) }; },
    async set(values) {
      this.writes++;
      for (const [key, value] of Object.entries(values)) entries.set(key, value);
    },
  };
}

async function until(predicate) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Popup did not finish the requested action");
    await new Promise(resolve => setTimeout(resolve, 2));
  }
  await new Promise(resolve => setImmediate(resolve));
}

async function popup(t, {
  applicationUrl = LEVER,
  pageUrl = "https://jobs.lever.co/synthetic-fi/analyst-123/thanks",
  review = "current", priorAttempt = false, accept = true,
} = {}) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, value: "", textContent: "", hidden: false, disabled: false,
      checked: false, handlers: new Map(),
      addEventListener(event, callback) { this.handlers.set(event, callback); },
      setAttribute() {}, select() {}, replaceChildren() {},
    });
    return elements.get(id);
  }
  const original = packet(applicationUrl);
  const reviewed = validateReviewPacket(original);
  const session = memoryStorage(), local = memoryStorage();
  if (review !== "missing") {
    await recordVerifiedReview(session, reviewed, {
      review_verified: true, review_state: "pending",
      expires_at: new Date(Date.now() + 4 * 60_000).toISOString(),
      automatic_employer_submit_authorized: false,
      external_actions_performed: false, browser_grant_issued: false,
    });
    if (review === "expired") {
      const key = await reviewSessionKey(reviewed);
      session.entries.get(key).expires_at = Date.now() - 1000;
    }
  }
  if (priorAttempt) local.entries.set(await oneAttemptKey(reviewed), {
    reserved_at: new Date().toISOString(), outcome: "unverified",
  });
  session.writes = 0;
  element("packet").value = JSON.stringify(original);
  element("receiptPanel").hidden = true;
  const state = {
    tab: { id: 17, url: pageUrl }, accept, confirmations: [], scripts: [],
    externalRequests: 0, clipboard: [], error: null, finding: null,
    frameId: 0, beforeReturn: null, returnedScripts: 0,
  };
  const globals = {
    document: { getElementById: element },
    window: { confirm(message) { state.confirmations.push(message); return state.accept; } },
    chrome: {
      tabs: { async query() { return [{ ...state.tab }]; } },
      storage: { session, local },
      scripting: {
        async executeScript(request) {
          state.scripts.push(request);
          // Any call to reserveFinalClickOnSmartPloy, an upload/fill executor,
          // or submitReviewedLeverOnce is an explicit failure in this test.
          assert.equal(request.func.name, "inspectReceipt");
          assert.equal(request.target.tabId, state.tab.id);
          assert.deepEqual(request.args, [applicationUrl]);
          if (state.error) throw state.error;
          const page = new URL(state.tab.url);
          const result = state.finding || {
            confirmed: true, reference: "SYNTHETIC-RECEIPT-123",
            confirmation_page_url: page.origin + page.pathname,
            confirmation_page_sha256: "d".repeat(64),
            explanation: "A reference-bearing confirmation was observed.",
          };
          if (state.beforeReturn) await state.beforeReturn();
          state.returnedScripts++;
          return [{ frameId: state.frameId, result }];
        },
      },
    },
    navigator: {
      clipboard: { async writeText(value) { state.clipboard.push(value); } },
      locks: { async request() { throw new Error("A receipt must never acquire a submit lock"); } },
    },
    fetch: async () => { state.externalRequests++; throw new Error("Receipt must not use network"); },
  };
  const descriptors = new Map();
  for (const [name, value] of Object.entries(globals)) {
    descriptors.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  }
  t.after(() => {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  });
  // A distinct module instance gives each real popup its own internal state.
  await import("../popup.mjs?sp47-test=" + ++moduleNumber);
  return {
    element, original, state, local, session,
    async click(id, done) {
      element("feedback").textContent = "";
      const handler = element(id).handlers.get("click");
      assert.equal(typeof handler, "function", "real popup handler " + id);
      handler();
      await until(done || (() => Boolean(element("feedback").textContent)));
    },
    noEmployerAction() {
      assert.equal(state.externalRequests, 0);
      assert.equal(local.writes, 0, "observation cannot create an attempt marker");
      assert.equal(session.writes, 0, "observation cannot reserve or consume a final claim");
      assert.ok(state.scripts.every(call => call.func.name === "inspectReceipt"));
      assert.equal(element("submit").disabled, true);
    },
  };
}

test("SP47 real popup exports a manual Lever observation without an automated attempt", async t => {
  const ui = await popup(t);
  await ui.click("resume");
  const receipt = JSON.parse(ui.element("receiptExport").value);
  assert.equal(receipt.schema, "smartploy.browser_receipt.v1");
  assert.equal(receipt.application_url, LEVER);
  assert.equal(receipt.workspace_id, ui.original.workspace_id);
  assert.equal(receipt.document_sha256, ui.original.document_sha256);
  assert.equal(receipt.reference, "SYNTHETIC-RECEIPT-123");
  assert.equal(receipt.confirmed_visible, true);
  assert.equal(ui.state.confirmations.length, 1);
  assert.match(ui.state.confirmations[0], /personally|manually/i);
  assert.match(ui.state.confirmations[0], /UNVERIFIED/i);
  assert.equal(ui.local.entries.size, 0);
  assert.equal(ui.element("receiptPanel").hidden, false);
  assert.equal("provider_acknowledged" in receipt, false);
  ui.noEmployerAction();
});

for (const [name, applicationUrl, pageUrl] of [
  ["Ashby", ASHBY, ASHBY + "/confirmation"],
  ["Greenhouse legacy-to-modern", GREENHOUSE,
    "https://job-boards.greenhouse.io/synthetic-fi/jobs/123456/confirmation?private=discard#secret"],
]) test("SP47 real popup exports manual " + name + " observation with the original job identity", async t => {
  const ui = await popup(t, { applicationUrl, pageUrl });
  await ui.click("resume");
  const receipt = JSON.parse(ui.element("receiptExport").value);
  assert.equal(receipt.application_url, applicationUrl);
  assert.equal(receipt.document_revision, ui.original.revision);
  assert.equal(receipt.confirmation_page_url, pageUrl.split(/[?#]/)[0]);
  assert.equal(ui.state.confirmations.length, 1);
  assert.equal(ui.local.entries.size, 0);
  ui.noEmployerAction();
});

for (const review of ["missing", "expired"]) {
  test("SP47 manual Lever cannot export with " + review + " signed-in review", async t => {
    const ui = await popup(t, { review });
    ui.element("receiptExport").value = "stale private observation";
    ui.element("receiptPanel").hidden = false;
    await ui.click("resume");
    assert.match(ui.element("feedback").textContent, /Verify.*signed-in|review.*expired/i);
    assert.equal(ui.state.confirmations.length, 0);
    assert.equal(ui.state.scripts.length, 0);
    assert.equal(ui.element("receiptExport").value, "");
    assert.equal(ui.element("receiptPanel").hidden, true);
    assert.equal(ui.local.writes + ui.session.writes, 0);
  });
}

test("SP47 cancellation clears a previous receipt without inspecting or reserving anything", async t => {
  const ui = await popup(t, { accept: false });
  ui.element("receiptExport").value = "stale private observation";
  ui.element("receiptPanel").hidden = false;
  await ui.click("resume", () => ui.state.confirmations.length === 1);
  assert.equal(ui.state.scripts.length, 0);
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  ui.noEmployerAction();
});

test("SP47 a different Lever job cannot be resumed even with an old automated attempt", async t => {
  const ui = await popup(t, {
    pageUrl: "https://jobs.lever.co/synthetic-fi/another-job/thanks",
    priorAttempt: true, review: "missing",
  });
  ui.element("receiptExport").value = "stale private observation";
  await ui.click("resume");
  assert.match(ui.element("feedback").textContent, /exact|original|same.*job/i);
  assert.equal(ui.state.scripts.length, 0);
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.local.entries.size, 1, "previous attempt must remain reserved");
  assert.equal(ui.local.writes + ui.session.writes, 0);
});

test("SP47 old automated Lever attempts retain read-only receipt reconciliation", async t => {
  const ui = await popup(t, { priorAttempt: true, review: "missing" });
  const originalAttempt = [...ui.local.entries];
  await ui.click("resume");
  assert.equal(JSON.parse(ui.element("receiptExport").value).reference,
    "SYNTHETIC-RECEIPT-123");
  assert.equal(ui.state.confirmations.length, 0, "do not mislabel an automated attempt as manual");
  assert.deepEqual([...ui.local.entries], originalAttempt);
  ui.noEmployerAction();
});

test("SP47 missing confirmation or later browser error clears export from the prior inspection", async t => {
  const ui = await popup(t);
  await ui.click("resume");
  assert.ok(ui.element("receiptExport").value);
  ui.state.finding = { confirmed: false, explanation: "No reference-bearing confirmation visible." };
  await ui.click("receipt");
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  ui.element("receiptExport").value = "stale observation";
  ui.element("receiptPanel").hidden = false;
  ui.state.error = new Error("Cannot access contents of this tab");
  await ui.click("receipt");
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  ui.noEmployerAction();
});

test("SP47 edited packet cannot borrow the previously verified manual receipt identity", async t => {
  const ui = await popup(t);
  await ui.click("resume");
  const before = ui.state.scripts.length;
  const changed = { ...ui.original, document_sha256: "e".repeat(64) };
  ui.element("packet").value = JSON.stringify(changed);
  await ui.click("receipt");
  assert.equal(ui.state.scripts.length, before);
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  ui.noEmployerAction();
});

test("SP47 receipt export ignores a subframe's claimed confirmation", async t => {
  const ui = await popup(t);
  ui.state.frameId = 9;
  await ui.click("resume");
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  assert.match(ui.element("feedback").textContent, /Could not inspect/i);
  ui.noEmployerAction();
});

test("SP47 switching employer tab during observation cannot export the previous page", async t => {
  const ui = await popup(t);
  ui.state.beforeReturn = async () => {
    ui.state.tab = { id: 99, url: "https://jobs.lever.co/synthetic-fi/another-job/thanks" };
  };
  await ui.click("resume");
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  assert.match(ui.element("feedback").textContent, /tab changed/i);
  ui.noEmployerAction();
});

test("SP47 switching tab during the final review lookup cannot export stale confirmation", async t => {
  const ui = await popup(t);
  const get = ui.session.get.bind(ui.session);
  let reviews = 0;
  ui.session.get = async key => {
    const stored = await get(key);
    // Resume review, pre-inspection review, then the final awaited review.
    // The switch occurs after the first post-inspection tab check.
    if (++reviews === 3) ui.state.tab = {
      id: 99, url: "https://jobs.lever.co/synthetic-fi/another-job/thanks",
    };
    return stored;
  };
  await ui.click("resume");
  assert.equal(reviews, 3);
  assert.equal(ui.state.scripts.length, 1);
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  assert.match(ui.element("feedback").textContent, /changed/i);
  ui.noEmployerAction();
});

test("SP47 changing the packet while observation is pending prevents stale export", async t => {
  const ui = await popup(t);
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  ui.state.beforeReturn = () => pending;
  ui.element("resume").handlers.get("click")();
  await until(() => ui.state.scripts.length === 1);
  ui.element("packet").value = JSON.stringify({ ...ui.original, revision: 3 });
  ui.element("packet").handlers.get("input")();
  release();
  await until(() => ui.state.returnedScripts === 1 && Boolean(ui.element("feedback").textContent));
  assert.equal(ui.element("receiptExport").value, "");
  assert.equal(ui.element("receiptPanel").hidden, true);
  assert.match(ui.element("feedback").textContent, /changed/i);
  ui.noEmployerAction();
});

test("SP47 observation mode cannot be used to fill, upload, reserve or submit", async t => {
  const ui = await popup(t);
  await ui.click("resume");
  const observations = ui.state.scripts.length;
  for (const action of ["fill", "attach", "reviewQuestions", "fillQuestions", "check", "submit", "reserveFinal"]) {
    ui.element(action).handlers.get("click")();
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(ui.state.scripts.length, observations);
  ui.noEmployerAction();
});

test("SP47 an old form inspection cannot reopen mutations after a newer receipt", async t => {
  const ui = await popup(t, { pageUrl: LEVER });
  const execute = globalThis.chrome.scripting.executeScript;
  let release;
  let formReturned = false;
  const pending = new Promise(resolve => { release = resolve; });
  globalThis.chrome.scripting.executeScript = async request => {
    if (request.func.name !== "inspectForm") return execute(request);
    ui.state.scripts.push(request);
    await pending;
    formReturned = true;
    return [{ frameId: 0, result: {
      url: LEVER, allElementsCount: 1,
      elements: [{ index: 0, type: "file", label: "CV", required: true, hasValue: false }],
    } }];
  };
  ui.element("inspect").handlers.get("click")();
  await until(() => ui.state.scripts.some(call => call.func.name === "inspectForm"));
  ui.state.tab.url = "https://jobs.lever.co/synthetic-fi/analyst-123/thanks";
  await ui.click("resume");
  const receipt = ui.element("receiptExport").value;
  const feedback = ui.element("feedback").textContent;
  assert.ok(receipt);
  release();
  await until(() => formReturned);
  assert.equal(ui.element("receiptExport").value, receipt);
  assert.equal(ui.element("receiptPanel").hidden, false);
  assert.equal(ui.element("feedback").textContent, feedback);
  for (const action of ["fill", "attach", "reviewQuestions", "fillQuestions", "check", "submit", "reserveFinal"]) {
    assert.equal(ui.element(action).disabled, true, action + " remains disabled");
    ui.element(action).handlers.get("click")();
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.deepEqual(ui.state.scripts.map(call => call.func.name), ["inspectForm", "inspectReceipt"]);
  assert.equal(ui.state.externalRequests, 0);
  assert.equal(ui.local.writes + ui.session.writes, 0);
});

test("SP47 exact receipt URL policy recognizes only supported same-job confirmation paths", () => {
  for (const [applicationUrl, activeUrl] of [
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123/thanks/"],
    [LEVER, LEVER + "/confirmation?private=discard#secret"],
    [LEVER.replace("jobs.lever.co", "jobs.eu.lever.co"),
      "https://jobs.eu.lever.co/synthetic-fi/analyst-123/thanks"],
    [ASHBY, ASHBY + "/confirmation/"],
    [ASHBY, "https://jobs.ashbyhq.com/synthetic-fi/analyst-123/"],
    [GREENHOUSE, "https://job-boards.greenhouse.io/synthetic-fi/jobs/123456/confirmation/"],
    [GREENHOUSE.replace("boards.greenhouse.io", "job-boards.greenhouse.io"), GREENHOUSE],
    [GREENHOUSE, GREENHOUSE + "?private=%2Fdiscard#secret"],
    [LEVER, "https://jobs.lever.co:443/synthetic-fi/analyst-123/thanks"],
  ]) assert.equal(exactReceiptPage(activeUrl, applicationUrl), true, activeUrl);
});

test("SP47 exact receipt URL policy refuses normalized traversal and cross-job disguises", () => {
  for (const [applicationUrl, activeUrl] of [
    [LEVER, "https://jobs.lever.co/synthetic-fi/other/thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123-other/thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123/apply-other"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123//thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/other/../analyst-123/thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/other/%2e%2e/analyst-123/thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123/apply/%2Fother"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123\\thanks"],
    [LEVER, "https://jobs.lever.co/synthetic-fi/analyst-123/tha\nnks"],
    [LEVER, " https://jobs.lever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://jobs.lever.co.evil.invalid/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://jobs%2Elever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://ｊｏｂｓ.lever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://user:secret@jobs.lever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://jobs.eu.lever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "http://jobs.lever.co/synthetic-fi/analyst-123/thanks"],
    [LEVER, "https://jobs.lever.co:8443/synthetic-fi/analyst-123/thanks"],
    [ASHBY, "https://jobs.ashbyhq.com/synthetic-fi/other/application/confirmation"],
    [ASHBY, ASHBY + "/../confirmation"],
    [GREENHOUSE, "https://job-boards.greenhouse.io/synthetic-fi/jobs/1234567/confirmation"],
    [GREENHOUSE, "https://job-boards.greenhouse.io/other/jobs/123456/confirmation"],
    [GREENHOUSE, "https://job-boards.greenhouse.io/synthetic-fi/confirmation"],
    [GREENHOUSE, GREENHOUSE + "/confirmation/another"],
    [GREENHOUSE, "https://boards.greenhouse.io.evil.invalid/synthetic-fi/jobs/123456"],
    [LEVER + "?unreviewed=value", LEVER],
    [GREENHOUSE + "#unreviewed", GREENHOUSE],
  ]) assert.equal(exactReceiptPage(activeUrl, applicationUrl), false,
    applicationUrl + " -> " + activeUrl);
});
