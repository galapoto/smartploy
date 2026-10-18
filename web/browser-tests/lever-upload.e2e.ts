/** Local synthetic Lever upload acceptance. Real employer traffic is never sent.
 * Test the exact extension bridge function in Chromium with a mock employer
 * origin and a second file input. The fake PDF is not real applicant content.
 */
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const JOB_URL = "https://jobs.lever.co/synthetic-org/12345678-1234-1234-1234-123456789abc/apply";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");
const MIME = "application/pdf";

async function setup(page: Page) {
  let externalRequests = 0;
  await page.route("**/*", async (route) => {
    if (route.request().url() !== JOB_URL) {
      externalRequests++;
      await route.abort();
      return;
    }
    await route.fulfill({
      status: 200, contentType: "text/html",
      body: `<!doctype html><html><body>
        <form id="application">
          <label for="resume_file">Résumé</label>
          <input id="resume_file" type="file" name="resume" accept="application/pdf">
          <label for="letter_file">Cover letter</label>
          <input id="letter_file" type="file" name="coverLetter">
          <button type="submit">Submit application</button>
        </form>
        <script>
          window.uploadEvents = 0; window.submissions = 0;
          document.getElementById('resume_file').addEventListener('change', () => window.uploadEvents++);
          document.getElementById('application').addEventListener('submit', (e) => {e.preventDefault(); window.submissions++;});
        </script></body></html>`
    });
  });
  await page.goto(JOB_URL);
  // Same function body as the extension's chrome.scripting.executeScript
  // callback; only replace the module export for a synthetic page harness.
  const source = await readFile(new URL("../../browser-companion/page-attachment.mjs", import.meta.url), "utf8");
  await page.addScriptTag({
    content: source.replace(
      "export async function attachReviewedPdf(",
      "window.attachReviewedPdf = async function attachReviewedPdf("
    )
  });
  return () => externalRequests;
}

function request(overrides: Record<string, unknown> = {}) {
  return {
    application_url: JOB_URL,
    inspected_url: JOB_URL,
    index: 0,
    expected_id: "resume_file",
    expected_name: "resume",
    expected_label: "Résumé",
    expected_accept: MIME,
    file_name: "reviewed-cv.pdf",
    size: PDF.length,
    sha256: createHash("sha256").update(PDF).digest("hex"),
    base64: PDF.toString("base64"),
    ...overrides
  };
}

async function attach(page: Page, payload: Record<string, unknown>) {
  return page.evaluate(async (data) =>
    (window as any).attachReviewedPdf(data) as Promise<{status: string; reason: string}>, payload);
}

test("a reviewed PDF is locally attached to the unique résumé input, not submitted", async ({page}) => {
  const external = await setup(page);
// Mirror the real inspectForm label algorithm rather than assuming
  // headless Chromium's innerText is identical to source markup.
  const expected_label = await page.locator("#resume_file").evaluate((el: HTMLInputElement) => {
    const found = el.labels?.[0]?.innerText ||
      el.getAttribute("aria-label") ||
      (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.textContent : "") ||
      el.getAttribute("placeholder") || el.name || el.id || "";
    return String(found).trim().slice(0, 150);
  });
  const reply = await attach(page, request({expected_label}));
  expect(reply.status, `Synthetic bridge rejected: ${reply.reason}`).toBe("attached_locally");
  const state = await page.evaluate(() => {
    const cv = document.querySelector<HTMLInputElement>("#resume_file");
    const other = document.querySelector<HTMLInputElement>("#letter_file");
    return {
      file: cv?.files?.[0]?.name, size: cv?.files?.[0]?.size,
      other: other?.files?.length, changes: (window as any).uploadEvents,
      submissions: (window as any).submissions
    };
  });
  expect(state).toEqual({ file: "reviewed-cv.pdf", size: PDF.length, other: 0, changes: 1, submissions: 0 });
  expect(external()).toBe(0);
});

test("wrong employer/job, stale identity and corrupt digest never attach", async ({page}) => {
  const external = await setup(page);
  const variants = [
    {application_url: JOB_URL.replace("/synthetic-org/", "/other-employer/")},
    {inspected_url: JOB_URL + "?unexpected=1"},
    {expected_id: "other_file"},
    {expected_name: "coverLetter"},
    {index: 1},
    {sha256: "0".repeat(64)},
    {base64: Buffer.from("not a pdf").toString("base64")}
  ];
  for (const change of variants) {
    const reply = await attach(page, request(change));
    expect(reply.status, JSON.stringify(change)).toBe("blocked");
  }
  const files = await page.locator("#resume_file").evaluate((el: HTMLInputElement) => el.files?.length);
  expect(files).toBe(0);
  expect(external()).toBe(0);
});

test("existing employer file and hidden inputs are never overwritten", async ({page}) => {
  await setup(page);
  await page.locator("#resume_file").setInputFiles({
    name:"existing.pdf",mimeType:"application/pdf",buffer:PDF
  });
  expect((await attach(page, request())).status).toBe("blocked");
  await page.locator("#resume_file").setInputFiles([]);
  await page.locator("#resume_file").evaluate((el: HTMLElement) => { el.style.display = "none"; });
  expect((await attach(page, request())).status).toBe("blocked");
});

test("form identity drift after inspection stops attachment", async ({page}) => {
  await setup(page);
  await page.locator("#resume_file").evaluate((el: HTMLInputElement) => { el.name = "other-purpose"; });
  expect((await attach(page, request())).status).toBe("blocked");
  const files = await page.locator("#resume_file").evaluate((el: HTMLInputElement) => el.files?.length);
  expect(files).toBe(0);
});
