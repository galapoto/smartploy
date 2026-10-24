import test from "node:test";
import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { submitReviewedLeverOnce } from "../page-final-submit.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const URL = "https://jobs.lever.co/synthetic/12345678-aaaa-bbbb-cccc-123456789abc/apply";
const pdf = Buffer.from("%PDF-1.4\n%Synthetic-reviewed-pdf%%EOF");
const pdfDigest = createHash("sha256").update(pdf).digest("hex");
const letter = "My confirmed experience and qualifications are relevant to this role. I reviewed this letter.";

function control(props = {}) {
  return {
    type: "text", value: "", required: false, disabled: false, valid: true,
    autocomplete: "", name: "", id: "", labels: [],
    getAttribute: () => "",
    getClientRects: () => [{}],
    closest: (selector) => selector === "form" ? null : null,
    ...props,
    validity: {valid: props.valid !== false},
  };
}

async function withFakeEmployer({
  employerUrl = URL, email = "candidate@example.invalid", fullName = "Synthetic Applicant",
  cvBytes = pdf, requiredMissing = false, challenge = false, duplicateButton = false,
  formValid = true, letterValue = letter, submitThrows = false,
  noLock = false, extraAttachment = false, hiddenExtraAttachment = false,
  mutateDuringCvRead = null,
} = {}) {
  const old = Object.fromEntries(
    ["location","window","document","getComputedStyle"].map(x => [x,globalThis[x]])
  );
  const state = {clicks: 0, marker: false, challenge, duplicateButton};
  const file = {
    size: cvBytes.length, name: "candidate-reviewed.pdf",
    type: "application/pdf",
    async arrayBuffer() {
      // Simulate a reactive employer form changing during asynchronous PDF read.
      if (typeof mutateDuringCvRead === "function") {
        mutateDuringCvRead(inputs, state, file);
      }
      return cvBytes.buffer.slice(cvBytes.byteOffset, cvBytes.byteOffset+cvBytes.byteLength);
    },
  };
  const inputs = [
    control({type:"text", value:fullName, autocomplete:"name",
      labels:[{innerText:"Full name"}]}),
    control({type:"email", value:email, autocomplete:"email",
      labels:[{innerText:"Email"}]}),
    control({type:"textarea",value:letterValue,
      labels:[{innerText:"Cover letter"}]}),
    control({type:"file", files:[file], labels:[{innerText:"CV / Résumé"}]}),
    control({type:"file", files: extraAttachment ? [file] : [],
      labels:[{innerText:"Other supporting document"}]}),
    control({type:"file", files: hiddenExtraAttachment ? [file] : [],
      getClientRects: () => [], labels:[{innerText:"Hidden supporting document"}]}),
    control({type:"checkbox", required:requiredMissing, checked:!requiredMissing,
      labels:[{innerText:"Consent"}]}),
  ];
  const form = {
    closest: () => null, getClientRects: () => [{}],
    querySelectorAll: () => inputs,
    checkValidity: () => formValid,
  };
  const button = {
    innerText: "Submit application",
    disabled: false, getAttribute: () => "",
    getClientRects: () => [{}],
    closest: (selector) => selector === "form" ? form : null,
    click() { state.clicks++; if (submitThrows) throw Error("Browser failed"); },
  };
  globalThis.window = {top: {}, self: null};
  globalThis.window.self = globalThis.window.top;
  globalThis.location = {href:employerUrl};
  globalThis.getComputedStyle = () => ({display:"block",visibility:"visible"});
  globalThis.document = {
    documentElement: {
      hasAttribute: () => noLock ? true : state.marker,
      setAttribute: (k,v) => {state.marker=true;},
    },
    querySelector: () => state.challenge ? {} : null,
    querySelectorAll: () => state.duplicateButton ? [button,button] : [button],
  };
  const binding = {
    application_url: URL, cv_pdf_sha256:pdfDigest, cv_pdf_size:pdf.length,
    email:"candidate@example.invalid", full_name:"Synthetic Applicant",
    cover_letter:letter,
  };
  try {
    const result = await submitReviewedLeverOnce(binding);
    const repeated = result.attempted ? await submitReviewedLeverOnce(binding) : null;
    return {result, repeated, clicks:state.clicks, marker:state.marker};
  } finally {
    for (const [k,v] of Object.entries(old)) {
      if (v === undefined) delete globalThis[k]; else globalThis[k] = v;
    }
  }
}

test("exact approved Lever form and matching CV permits ONE click only", async () => {
  const r = await withFakeEmployer();
  assert.equal(r.result.attempted,true);
  assert.equal(r.result.provider_acknowledged,false);
  assert.equal(r.result.automatic_retry_authorized,false);
  assert.equal(r.clicks,1);
  assert.equal(r.marker,true);
  assert.equal(r.repeated.attempted,false);
  assert.equal(r.repeated.reason,"employer_form_already_attempted");
});

test("untrusted URL, incomplete employer form, duplicate control or challenge never click",async()=>{
  const scenarios = [
    [{employerUrl:"https://malicious.example.invalid/apply"},"wrong_employer_job"],
    [{employerUrl:"http://jobs.lever.co/synthetic/12345678-aaaa-bbbb-cccc-123456789abc/apply"},"wrong_employer_job"],
    [{employerUrl:URL+"?next=https://evil.invalid"},"wrong_employer_job"],
    [{employerUrl:"https://jobs.lever.co/synthetic/anotherid/apply"},"wrong_employer_job"],
    [{duplicateButton:true},"nonunique_final_submit_control"],
    [{challenge:true},"security_challenge_requires_human"],
    [{requiredMissing:true},"required_employer_field_unresolved"],
    [{formValid:false},"employer_form_invalid"],
    [{noLock:true},"employer_form_already_attempted"],
  ];
  for(const [config,reason] of scenarios){
    const r=await withFakeEmployer(config);
    assert.equal(r.result.attempted,false,JSON.stringify(config));
    assert.equal(r.result.reason,reason,JSON.stringify(config));
    assert.equal(r.clicks,0,JSON.stringify(config));
  }
});

test("changed approved email, name, letter or PDF forbids employer submit",async()=>{
  for(const c of [
    {email:"other@example.invalid"},
    {fullName:"Other Applicant"},
    {letterValue:"Altered employer letter"},
    {cvBytes:Buffer.from("%PDF-1.4\n%Changed PDF%%EOF")},
  ]) {
    const r=await withFakeEmployer(c);
    assert.equal(r.result.attempted,false,JSON.stringify(c));
    assert.equal(r.clicks,0,JSON.stringify(c));
  }
});

test("browser click exception yields unknown outcome; never a second click",async()=>{
  const r=await withFakeEmployer({submitThrows:true});
  assert.equal(r.result.attempted,false);
  assert.equal(r.result.reason,"outcome_uncertain_do_not_retry");
  assert.equal(r.clicks,1);
  assert.equal(r.marker,true);
});

test("unreviewed second file attachment prevents the final employer click", async () => {
  const r = await withFakeEmployer({extraAttachment:true});
  assert.equal(r.result.attempted,false);
  assert.equal(r.result.reason,"unreviewed_extra_attachment_present");
  assert.equal(r.clicks,0);
  assert.equal(r.marker,false);
});

test("hidden populated employer file input is rejected before final click", async () => {
  const r = await withFakeEmployer({hiddenExtraAttachment:true});
  assert.equal(r.result.attempted,false);
  assert.equal(r.result.reason,"unreviewed_extra_attachment_present");
  assert.equal(r.clicks,0);
  assert.equal(r.marker,false);
});

test("changes during async CV hashing cannot bypass final-click review", async () => {
  const mutations = [
    ["email", (inputs) => { inputs[1].value = "changed@example.invalid"; }],
    ["name", (inputs) => { inputs[0].value = "Other Applicant"; }],
    ["cover letter", (inputs) => { inputs[2].value = "Changed letter after review"; }],
    ["visible extra attachment", (inputs, state, file) => { inputs[4].files = [file]; }],
    ["hidden extra attachment", (inputs, state, file) => { inputs[5].files = [file]; }],
    ["replaced CV input", (inputs, state, file) => {
      inputs[3].files = [{...file}];
    }],
    ["required consent unchecked", (inputs) => {
      inputs[6].required = true;
      inputs[6].checked = false;
    }],
    ["new employer field", (inputs) => {
      inputs.push(control({type:"text", value:"new data"}));
    }],
    ["late CAPTCHA", (inputs, state) => { state.challenge = true; }],
    ["late duplicate submit", (inputs, state) => { state.duplicateButton = true; }],
  ];
  for (const [label, mutateDuringCvRead] of mutations) {
    const r = await withFakeEmployer({mutateDuringCvRead});
    assert.equal(r.result.attempted, false, label);
    assert.equal(r.result.reason, "employer_form_changed", label);
    assert.equal(r.clicks, 0, label);
    assert.equal(r.marker, false, label);
  }
});
