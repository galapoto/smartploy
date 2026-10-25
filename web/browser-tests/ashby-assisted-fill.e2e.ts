/** SP41: exercise the REAL companion form executor against an isolated
 * synthetic Ashby job with no external employer request and no final submit. */
import {readFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {expect,test,type Page} from "@playwright/test";

const JOB="https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application";
const PDF=Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");

async function setup(page:Page) {
  let outside=0;
  await page.route("**/*",async route=>{
    if (route.request().url() !== JOB) {
      outside++;
      await route.abort();
      return;
    }
    await route.fulfill({status:200,contentType:"text/html",body:`
      <!doctype html><html><body><form id="apply" action="/synthetic" method="post">
      <label for="name">Full name</label>
      <input id="name" name="candidateName" type="text">
      <label for="email">Email</label>
      <input id="email" name="contactEmail" type="email" required>
      <label for="cv">CV / Résumé</label>
      <input id="cv" name="resume" type="file" accept="application/pdf">
      <label for="visa">Work authorization</label>
      <input id="visa" name="visaStatus" type="text">
      <label for="why">Why are you interested in this role?</label>
      <textarea id="why" name="questions[motivation]" required></textarea>
      <button type="submit">Submit application</button></form>
      <script>
        window.employerSubmissions=0;window.attachmentChanges=0;
        document.querySelector("form").addEventListener("submit",event=>{
          event.preventDefault();window.employerSubmissions++;
        });
        document.querySelector("#cv").addEventListener("change",()=>{
          window.attachmentChanges++;
        });
      </script></body></html>`});
  });
  await page.goto(JOB);
  const popup=await readFile(
    new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8"
  );
  const first=popup.indexOf("function fillPlanned(actions, exactUrl) {");
  const last=popup.indexOf("\nfunction inspectFinalSubmit(",first);
  if (first<0 || last<=first) throw Error("Existing reviewed contact executor not found");
  await page.addScriptTag({content:popup.slice(first,last)+"\nwindow.fillPlanned=fillPlanned;"});
  const questions=(await readFile(
    new URL("../../browser-companion/page-questions.mjs",import.meta.url),"utf8"
  )).replace("export function fillReviewedAnswers","function fillReviewedAnswers");
  await page.addScriptTag({content:questions+"\nwindow.fillReviewedAnswers=fillReviewedAnswers;"});
  const attachment=(await readFile(
    new URL("../../browser-companion/page-attachment.mjs",import.meta.url),"utf8"
  )).replace("export async function attachReviewedPdf","async function attachReviewedPdf");
  await page.addScriptTag({content:attachment+"\nwindow.attachReviewedPdf=attachReviewedPdf;"});
  return ()=>outside;
}

const nameField = {
  index:0,key:"full_name",value:"Reviewed Test Candidate",
  label:"Full name",expected_id:"name",expected_name:"candidateName",
  expected_type:"text"
};
const emailField = {
  index:1,key:"email",value:"reviewed@example.invalid",
  label:"Email",expected_id:"email",expected_name:"contactEmail",
  expected_type:"email"
};
const question = {
  index:4,type:"textarea",value:"I reviewed this precise example.",
  label:"Why are you interested in this role?",
  expected_id:"why",expected_name:"questions[motivation]",
  expected_placeholder:"",expected_max_length:-1
};
const pdfPayload = {
  application_url:JOB,inspected_url:JOB,index:2,
  expected_id:"cv",expected_name:"resume",expected_label:"CV / Résumé",
  expected_accept:"application/pdf",file_name:"synthetic-reviewed.pdf",
  size:PDF.length,sha256:createHash("sha256").update(PDF).digest("hex"),
  base64:PDF.toString("base64")
};

test("real reviewed contact and ordinary-question executors fill Ashby without submitting",async ({page})=>{
  const outside=await setup(page);
  const contacts=await page.evaluate(
    ({actions,url})=>(window as any).fillPlanned(actions,url),
    {actions:[nameField,emailField],url:JOB}
  );
  expect(contacts).toEqual({filled:2,skipped:0,blocker:""});
  expect(await page.locator("#name").inputValue()).toBe("Reviewed Test Candidate");
  expect(await page.locator("#email").inputValue()).toBe("reviewed@example.invalid");
  const q=await page.evaluate(
    ({actions,url})=>(window as any).fillReviewedAnswers(actions,url,url),
    {actions:[question],url:JOB}
  );
  expect(q.status).toBe("filled_for_review");
  expect(q.filled).toBe(1);
  expect(await page.locator("#why").inputValue()).toBe(question.value);
  expect(await page.locator("#visa").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).employerSubmissions)).toBe(0);
  expect(outside()).toBe(0);
});

test("real Ashby reviewed-PDF adapter attaches only the exact fingerprint without submitting",async ({page})=>{
  const outside=await setup(page);
  const out=await page.evaluate(
    args=>(window as any).attachReviewedPdf(args),pdfPayload
  );
  expect(out.status).toBe("attached_locally");
  expect(await page.locator("#cv").evaluate(
    el=>(el as HTMLInputElement).files?.[0]?.name
  )).toBe("synthetic-reviewed.pdf");
  expect(await page.evaluate(()=>(window as any).attachmentChanges)).toBe(1);
  expect(await page.evaluate(()=>(window as any).employerSubmissions)).toBe(0);
  expect(outside()).toBe(0);
});

test("cross-job Ashby PDF, changed labels and hidden legal metadata cannot be auto-filled",async ({page})=>{
  const outside=await setup(page);
  const offsite=await page.evaluate(
    args=>(window as any).attachReviewedPdf(args),
    {...pdfPayload,application_url:
      "https://jobs.ashbyhq.com/other-board/other-job/application"}
  );
  expect(offsite.status).toBe("blocked");
  const altered=await page.evaluate(
    args=>(window as any).attachReviewedPdf(args),
    {...pdfPayload,sha256:"0".repeat(64)}
  );
  expect(altered.status).toBe("blocked");
  const legal=await page.evaluate(
    ({actions,url})=>(window as any).fillPlanned(actions,url),
    {actions:[{...nameField,index:3,label:"Work authorization",
      expected_id:"visa",expected_name:"visaStatus",value:"yes"}],url:JOB}
  );
  expect(legal.filled).toBe(0);
  expect(legal.blocker).toMatch(/identity|metadata/i);
  expect(await page.locator("#visa").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).employerSubmissions)).toBe(0);
  expect(outside()).toBe(0);
});

test("Ashby dynamic form re-render stops the original contact executor without retry",async ({page})=>{
  await setup(page);
  await page.locator("#name").evaluate(el=>{
    el.addEventListener("input",()=>{
      const required=document.createElement("input");
      required.name="new_required_question";required.required=true;
      el.closest("form")?.append(required);
    },{once:true});
  });
  const result=await page.evaluate(
    ({actions,url})=>(window as any).fillPlanned(actions,url),
    {actions:[nameField,emailField],url:JOB}
  );
  expect(result.filled).toBe(1);
  expect(result.blocker).toMatch(/changed after contact field input/i);
  expect(await page.locator("#email").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).employerSubmissions)).toBe(0);
});
