import test from "node:test";
import assert from "node:assert/strict";
import {
  UploadError, MAX_PDF_BYTES, chooseResumeField, exactLeverForm, exactAssistedForm, isLeverFinalProvider,
  encodePdfBase64, validatePdf
} from "../upload.mjs";

const listing = "https://jobs.lever.co/example/12345678-0000-4000-8000-123456789abc";
const form = listing + "/apply";

function field(extra = {}) {
  return {
    index: 1, type: "file", label: "Upload résumé (PDF)", id: "resume_file",
    name: "resume", visible: true, disabled: false, readonly: false,
    multiple: false, hasValue: false, accept: "application/pdf", ...extra
  };
}

function fakePdf() {
  return new TextEncoder().encode("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");
}

test("only exact same Lever job and actual application form may receive PDF", () => {
  assert.equal(exactLeverForm(form, listing), true);
  assert.equal(exactLeverForm(form + "/", form), true);
  for (const [active, target] of [
    [listing, listing],
    ["https://evil.example.com/example/12345678-0000-4000-8000-123456789abc/apply", listing],
    ["http://jobs.lever.co/example/12345678-0000-4000-8000-123456789abc/apply", listing],
    ["https://jobs.lever.co/other/12345678-0000-4000-8000-123456789abc/apply", listing],
    ["https://jobs.lever.co/example/12345678-0000-4000-8000-123456789abc-evil/apply", listing],
    ["https://jobs.eu.lever.co/example/12345678-0000-4000-8000-123456789abc/apply", listing],
    ["https://jobs.lever.co/example/12345678-0000-4000-8000-123456789abc/other", listing],
    ["https://user:secret@jobs.lever.co/example/12345678-0000-4000-8000-123456789abc/apply", listing],
  ]) assert.equal(exactLeverForm(active, target), false, active);
});

test("one visible empty résumé field is selected; cover letter cannot be mistaken for CV", () => {
  const got = chooseResumeField([
    { index: 0, type: "file", label: "Cover letter" },
    field(),
    { index: 2, type: "text", label: "Email" }
  ]);
  assert.deepEqual(got, {
    index: 1, expected_id: "resume_file", expected_name: "resume",
    expected_label: "Upload résumé (PDF)", expected_accept: "application/pdf"
  });
  for (const alt of ["CV", "Ansioluettelo", "Meritförteckning", "Curriculum Vitae", "resumeFile"]) {
    assert.equal(chooseResumeField([field({label: alt})]).index, 1, alt);
  }
});

test("ambiguous, hidden, prefilled, multiple and unsupported upload fields fail closed", () => {
  const cases = [
    [], [field(), field({index: 2, name: "anotherResume"})],
    [field({visible:false})], [field({disabled:true})],
    [field({readonly:true})], [field({hasValue:true})],
    [field({multiple:true})], [field({accept:"image/jpeg"})],
    [field({label:"Cover letter or CV"})],
    [field({index:251})],
    Array.from({length:251},()=>({type:"text"}))
  ];
  for (const input of cases) {
    assert.throws(() => chooseResumeField(input), UploadError, JSON.stringify(input).slice(0,90));
  }
});

test("only bounded PDF bytes with correct filename, mime, header and trailer pass", () => {
  const bytes = fakePdf();
  assert.equal(validatePdf("reviewed-cv.pdf", "application/pdf", bytes).size, bytes.length);
  assert.equal(validatePdf("cv.PDF", "", bytes).filename, "cv.PDF");
  const invalid = [
    ["cv.docx", "application/pdf", bytes],
    ["../cv.pdf", "application/pdf", bytes],
    ["cv.pdf", "image/png", bytes],
    ["cv.pdf", "", new TextEncoder().encode("hello world\n%%EOF\n")],
    ["cv.pdf", "", new TextEncoder().encode("%PDF-1.4\nmissing trailer")],
    ["cv.pdf", "", new Uint8Array(MAX_PDF_BYTES+1)],
    ["cv.pdf", "", new Uint8Array(2)]
  ];
  for (const args of invalid) {
    assert.throws(() => validatePdf(...args), UploadError);
  }
});

test("encoding preserves the PDF exactly and never uploads or stores it", () => {
  const bytes = fakePdf();
  const encoded = encodePdfBase64(bytes);
  assert.deepEqual(Buffer.from(encoded, "base64"), Buffer.from(bytes));
  assert.throws(() => encodePdfBase64(new Uint8Array(MAX_PDF_BYTES+1)), UploadError);
});

const ashbyPosting = "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst";
const ashbyApplication = ashbyPosting + "/application";

test("SP41 reviewed Ashby PDF attachment is scoped to exact same hosted /application route", () => {
  assert.equal(exactAssistedForm(ashbyApplication, ashbyPosting), true);
  assert.equal(exactAssistedForm(ashbyApplication + "/", ashbyApplication), true);
  assert.equal(exactAssistedForm(ashbyPosting, ashbyPosting), false);
  assert.equal(exactAssistedForm(form, listing), true); // original Lever behavior unchanged.
  for (const bad of [
    ashbyPosting + "/other",
    "https://jobs.ashbyhq.com/another/role/application",
    "https://jobs.ashbyhq.com/synthetic-fi/another-role/application",
    "https://jobs.ashbyhq.com.evil.invalid/synthetic-fi/junior-data-analyst/application",
    "http://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application",
    ashbyApplication + "?redirect=bad",
    ashbyApplication + "#bad",
  ]) {
    assert.equal(exactAssistedForm(bad, ashbyPosting), false, bad);
  }
  assert.equal(isLeverFinalProvider(ashbyApplication), false);
  assert.equal(isLeverFinalProvider(ashbyPosting), false);
  assert.equal(isLeverFinalProvider(form), true);
  assert.equal(isLeverFinalProvider(listing), true);
});
