/** SP121: actual Chromium executes the existing extension page callbacks.
 * HTTPS employer content is fully intercepted; no employer requests, real CVs
 * or submissions occur.
 */
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const POSTING = "https://careers.example.org/jobs/junior-analyst";
const FORM = POSTING + "/apply";
const TALENT = "https://ats.talentadore.com/apply/junior-analyst/m6rpoy";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");

function fakeForm() {
  return [
    '<!doctype html><html><head><meta charset="utf-8"></head><body>',
    "<h1>Apply for Junior Analyst</h1>",
    '<form id="application">',
    '<label for="full">Full name</label><input name="full_name" id="full">',
    '<label for="email">Email</label><input name="email" id="email" type="email">',
    '<label for="salary">Salary expectation</label><input name="salary" id="salary">',
    '<label for="consent">Privacy consent</label><input name="consent" id="consent" type="checkbox">',
    '<label for="resume">Résumé</label><input name="resume" id="resume" type="file" accept="application/pdf">',
    '<label for="reason">Why this role?</label><textarea id="reason" name="motivation" required></textarea>',
    '<button type="submit">Submit application</button>',
    '</form><script>',
    'window.submitCount = 0; window.fileChanges = 0;',
    'document.querySelector("#application").addEventListener("submit", e => {',
    'e.preventDefault(); window.submitCount++; });',
    'document.querySelector("#resume").addEventListener("change", () => window.fileChanges++);',
    '</script></body></html>',
  ].join("");
}

async function interceptEmployer(page: Page, target = FORM) {
  let unexpected = 0;
  await page.route("**/*", async route => {
    if (route.request().url() === target) {
      await route.fulfill({ status: 200, contentType: "text/html", body: fakeForm() });
    } else {
      unexpected++;
      await route.abort();
    }
  });
  await page.goto(target, { waitUntil: "domcontentloaded" });
  return () => unexpected;
}

async function inject(page: Page, file: string, start: string, end?: string) {
  let code = await readFile(new URL("../../browser-companion/" + file, import.meta.url), "utf8");
  if (end) {
    const from = code.indexOf(start), till = code.indexOf(end, from + 1);
    expect(from).toBeGreaterThanOrEqual(0);
    expect(till).toBeGreaterThan(from);
    code = code.slice(from, till);
  }
  const output = start.includes("fillPlanned")
    ? code.replace("function fillPlanned(", "window.extensionFillPlanned = function fillPlanned(")
    : start.includes("attachReviewedPdf")
      ? code.replace("export async function attachReviewedPdf(",
        "window.extensionAttachPdf = async function attachReviewedPdf(")
      : code.replace("export async function fillReviewedAnswers(",
        "window.extensionFillQuestions = async function fillReviewedAnswers(");
  await page.addScriptTag({ content: output });
}

test("SP121 custom public employer: extension fills reviewed contacts, never salary or consent", async ({page}) => {
  const unexpected = await interceptEmployer(page);
  await inject(page, "popup.mjs",
    "function fillPlanned(actions, exactUrl) {", "\nfunction inspectFinalSubmit(");
  const actions = [
    { index:0, expected_id:"full", expected_name:"full_name",
      expected_type:"text", label:"Full name", value:"Fictional Applicant" },
    { index:1, expected_id:"email", expected_name:"email",
      expected_type:"email", label:"Email", value:"applicant@example.org" }
  ];
  const result = await page.evaluate(([items, posting]) =>
    (window as any).extensionFillPlanned(items, posting),
    [actions, POSTING] as const);
  expect(result).toEqual({filled:2,skipped:0,blocker:""});
  expect(await page.locator("#full").inputValue()).toBe("Fictional Applicant");
  expect(await page.locator("#email").inputValue()).toBe("applicant@example.org");
  expect(await page.locator("#salary").inputValue()).toBe("");
  expect(await page.locator("#consent").isChecked()).toBe(false);
  expect(await page.evaluate(() => (window as any).submitCount)).toBe(0);
  expect(unexpected()).toBe(0);
});

test("SP121 custom public employer: digest-checked PDF attachment is local, not final submit", async ({page}) => {
  const unexpected = await interceptEmployer(page);
  await inject(page, "page-attachment.mjs", "export async function attachReviewedPdf(");
  const label = await page.locator("#resume").evaluate((el: HTMLInputElement) =>
    el.labels?.[0]?.innerText || el.name);
  const payload = {
    application_url:POSTING, inspected_url:FORM, index:4,
    expected_id:"resume", expected_name:"resume",
    expected_label:label, expected_accept:"application/pdf",
    file_name:"fictional-reviewed-cv.pdf", size:PDF.length,
    sha256:createHash("sha256").update(PDF).digest("hex"),
    base64:PDF.toString("base64"),
  };
  const tampered = await page.evaluate(p =>
    (window as any).extensionAttachPdf({...p,
      application_url:"https://careers.attacker.org/jobs/junior-analyst"}),payload);
  expect(tampered.status).toBe("blocked");
  const correct = await page.evaluate(p => (window as any).extensionAttachPdf(p),payload);
  expect(correct.status, correct.reason).toBe("attached_locally");
  expect((await page.locator("#resume").evaluate((el:HTMLInputElement) =>
    el.files?.[0]?.name))).toBe("fictional-reviewed-cv.pdf");
  expect(await page.evaluate(() => (window as any).fileChanges)).toBe(1);
  expect(await page.evaluate(() => (window as any).submitCount)).toBe(0);
  expect(unexpected()).toBe(0);
});

test("SP121 custom public employer: reviewed ordinary question is filled without consent", async ({page}) => {
  const unexpected = await interceptEmployer(page);
  await inject(page,"page-questions.mjs","export async function fillReviewedAnswers(");
  const actions = [{
    index:5, type:"textarea", value:"I have reviewed this fictional answer.",
    label:"Why this role?", expected_id:"reason", expected_name:"motivation",
    expected_placeholder:"", expected_max_length:-1
  }];
  const result = await page.evaluate(([items, source, inspected]) =>
    (window as any).extensionFillQuestions(items, source, inspected),
    [actions, POSTING, FORM] as const);
  expect(result.status).toBe("filled_for_review");
  expect(result.filled).toBe(1);
  expect(await page.locator("#reason").inputValue()).toBe(actions[0].value);
  expect(await page.locator("#consent").isChecked()).toBe(false);
  expect(await page.evaluate(() => (window as any).submitCount)).toBe(0);
  expect(unexpected()).toBe(0);
});

test("V4 same employer hostname is insufficient for any different job action", async ({page}) => {
  const unexpected = await interceptEmployer(page);
  const wrongJob = "https://careers.example.org/jobs/senior-engineer";
  await inject(page, "popup.mjs",
    "function fillPlanned(actions, exactUrl) {", "\nfunction inspectFinalSubmit(");
  await inject(page, "page-questions.mjs",
    "export async function fillReviewedAnswers(");
  await inject(page, "page-attachment.mjs",
    "export async function attachReviewedPdf(");
  const contacts = await page.evaluate(url =>
    (window as any).extensionFillPlanned([{
      index:0, expected_id:"full", expected_name:"full_name",
      expected_type:"text", label:"Full name", value:"Fictional Applicant"
    }], url), wrongJob);
  expect(contacts.filled).toBe(0);
  expect(contacts.blocker).toMatch(/changed since packet approval/);
  const question = await page.evaluate(({url,inspected}) =>
    (window as any).extensionFillQuestions([{
      index:5, type:"textarea", value:"Truthful synthetic answer",
      label:"Why this role?", expected_id:"reason", expected_name:"motivation",
      expected_placeholder:"", expected_max_length:-1
    }], url, inspected), {url:wrongJob,inspected:FORM});
  expect(question.status).toBe("blocked");
  expect(question.filled).toBe(0);
  const attachment = await page.evaluate(({url,inspected}) =>
    (window as any).extensionAttachPdf({
      application_url:url,inspected_url:inspected
    }), {url:wrongJob,inspected:FORM});
  expect(attachment.status).toBe("blocked");
  expect(await page.locator("#full").inputValue()).toBe("");
  expect(await page.locator("#reason").inputValue()).toBe("");
  expect(await page.locator("#resume").evaluate(
    (el:HTMLInputElement) => el.files?.length || 0)).toBe(0);
  expect(await page.evaluate(() => (window as any).submitCount)).toBe(0);
  expect(unexpected()).toBe(0);
});

test("SP121 TalentAdore: existing extension PDF callback accepts exact hosted posting", async ({page}) => {
  const unexpected = await interceptEmployer(page, TALENT);
  await inject(page,"page-attachment.mjs","export async function attachReviewedPdf(");
  const label = await page.locator("#resume").evaluate((el: HTMLInputElement) =>
    el.labels?.[0]?.innerText || el.name);
  const payload = {
    application_url:TALENT,inspected_url:TALENT,index:4,expected_id:"resume",
    expected_name:"resume",expected_label:label,expected_accept:"application/pdf",
    file_name:"fictional-reviewed-cv.pdf",size:PDF.length,
    sha256:createHash("sha256").update(PDF).digest("hex"),base64:PDF.toString("base64")
  };
  const result = await page.evaluate(p => (window as any).extensionAttachPdf(p),payload);
  expect(result.status, result.reason).toBe("attached_locally");
  expect(await page.evaluate(() => (window as any).submitCount)).toBe(0);
  expect(unexpected()).toBe(0);
});
