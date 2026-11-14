/** ONE synthetic Lever application from profile fields and both PDFs to a
 * reference-bearing receipt, exercising the actual Chrome page functions.
 * HTTPS employer/app network is stubbed by Playwright; NO actual employer
 * receives an application and NO user data enters this test.
 */
import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";
import {planFields} from "../../browser-companion/logic.mjs";
import {planReviewedQuestions,suggestSavedAnswers,validateReviewedAnswers}
  from "../../browser-companion/questions.mjs";
import {chooseResumeField,chooseCoverLetterField,exactReceiptPage}
  from "../../browser-companion/upload.mjs";

const JOB="https://jobs.lever.co/synthetic-org/job123/apply";
const SITE="https://smartploy.komplyint.fi/";
const WORKSPACE="kit-"+"a".repeat(30);
const CV=Buffer.from("%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n%%EOF\n");
const LETTER=Buffer.from("%PDF-1.4\n1 0 obj<< /Type /Pages >>endobj\n%%EOF\n");
const sha=(v:Buffer)=>createHash("sha256").update(v).digest("hex");
const NAME="Synthetic Applicant";
const EMAIL="synthetic@example.invalid";
const LETTER_TEXT="Dear hiring team, my reviewed Python and SQL project experience matches this analyst role. Kind regards, Synthetic Applicant.";
const ANSWER="The employer's careers page";

async function injectModule(page:Page,path:string,exportSignature:string,globalName:string) {
  const src=await readFile(new URL(path,import.meta.url),"utf8");
  expect(src.includes(exportSignature)).toBe(true);
  await page.addScriptTag({
    content:src.replace(exportSignature,
      "window."+globalName+" = "+exportSignature.replace(/^export /,""))
  });
}

async function injectPopupFunction(page:Page,source:string,start:string,end:string,fn:string) {
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  expect(a).toBeGreaterThan(0);
  expect(b).toBeGreaterThan(a);
  const segment=source.slice(a,b);
  await page.addScriptTag({content:segment.replace(start,"window."+fn+" = "+start)});
}

test("ONE job: saved profile→field fill→two PDF attachments→answers→reviewed one-click→real DOM receipt→account record",async({page,context})=>{
  let employerOutbound=0,submitClicks=0,serverClaims=0,serverReceipts=0;
  await page.route("**/*",async route=>{
    if(route.request().url()!==JOB){
      employerOutbound++;await route.abort();return;
    }
    await route.fulfill({status:200,contentType:"text/html",body:`<!doctype html>
      <html><body><form id="application" method="post">
        <label for="applicant_name">Full name</label>
        <input id="applicant_name" name="fullName" autocomplete="name" required/>
        <label for="applicant_email">Email</label>
        <input id="applicant_email" name="email" type="email" autocomplete="email" required/>
        <label for="resume_file">CV / Résumé</label>
        <input id="resume_file" name="resume" type="file" accept="application/pdf" required/>
        <label for="cover_letter_file">Cover letter</label>
        <input id="cover_letter_file" name="coverLetter" type="file" accept="application/pdf" required/>
        <label for="referral">How did you hear about us?</label>
        <textarea id="referral" name="referral" required></textarea>
        <button type="submit">Submit application</button>
      </form>
      <script>
        window.employerSubmitClicks=0;
        document.getElementById("application").addEventListener("submit",e=>{
          e.preventDefault(); window.employerSubmitClicks++;
          history.replaceState(null,"","/synthetic-org/job123/thanks");
          document.body.innerHTML="<h1>Thank you for your application</h1>"+
            "<p>Application received. Reference: SYN-REF-2026</p>";
        });
      </script></body></html>`});
  });
  const smartPage=await context.newPage();
  await smartPage.route("**/*",async route=>{
    const request=route.request(),url=request.url();
    if(url===SITE){
      await route.fulfill({status:200,contentType:"text/html",
        body:"<!doctype html><title>Signed-in synthetic SmartPloy</title>"});
    }else if(url===SITE+"api/v1/session"){
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({authenticated:true,auth_source:"oidc",
          user_id:"usr-"+"b".repeat(32)})});
    }else if(url===SITE+"api/v1/application-workspaces/"+WORKSPACE+
      "/browser-final-attempt"){
      serverClaims++;
      const req=request.postDataJSON();
      expect(req.expected_cv_pdf_sha256).toBe(sha(CV));
      expect(req.expected_letter_pdf_sha256).toBe(sha(LETTER));
      expect(req.expected_saved_answers_sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(req.confirm_one_job_final_click).toBe(true);
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({
          claim_reserved:true,claim_id:"employer-claim-"+"c".repeat(32),
          expires_at:"2099-01-01T00:00:00Z",one_job_browser_click_permitted:true,
          external_actions_performed:false,provider_acknowledged:false,
          automatic_retry_authorized:false
        })});
    }else if(url===SITE+"api/v1/application-workspaces/"+WORKSPACE+
      "/browser-receipt"){
      serverReceipts++;
      const data=request.postDataJSON();
      expect(data.confirm_user_observed).toBe(true);
      expect(data.receipt.reference).toBe("SYN-REF-2026");
      expect(data.receipt.confirmed_visible).toBe(true);
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({receipt:{workspace_id:WORKSPACE},
          external_confirmation_verified:false})});
    }else{
      await route.abort();
    }
  });
  await Promise.all([page.goto(JOB),smartPage.goto(SITE)]);
  const popupSrc=await readFile(new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8");
  await injectPopupFunction(page,popupSrc,"function inspectForm() {",
    "\n/* Strictly fill only", "inspectForm");
  await injectPopupFunction(page,popupSrc,"async function fillPlanned(",
    "\nfunction inspectFinalSubmit(", "fillPlanned");
  await injectPopupFunction(page,popupSrc,"async function inspectReceipt(",
    "\n/* Ashby", "inspectReceipt");
  await injectModule(page,"../../browser-companion/page-attachment.mjs",
    "export async function attachReviewedPdf(", "attachReviewedPdf");
  await injectModule(page,"../../browser-companion/page-questions.mjs",
    "export function fillReviewedAnswers(", "fillReviewedAnswers");
  await injectModule(page,"../../browser-companion/page-final-submit.mjs",
    "export async function submitReviewedLeverOnce(", "submitReviewedLeverOnce");
  await injectModule(smartPage,"../../browser-companion/page-final-claim.mjs",
    "export async function reserveFinalClickOnSmartPloy(", "reserveFinalClickOnSmartPloy");
  await injectModule(smartPage,"../../browser-companion/page-receipt-import.mjs",
    "export async function saveOneObservedReceiptOnSmartPloy(", "saveOneObservedReceiptOnSmartPloy");

  const inspected=await page.evaluate(()=> (window as any).inspectForm());
  expect(inspected.url).toBe(JOB);
  const profile={application_url:JOB,fields:{
    full_name:NAME,email:EMAIL,cover_letter:LETTER_TEXT
  }};
  const contactPlan=planFields(inspected.elements,profile as any);
  expect(contactPlan.actions.length).toBe(2);
  const filled=await page.evaluate(async ({actions,url})=>
    (window as any).fillPlanned(actions,url),
    {actions:contactPlan.actions,url:JOB});
  expect(filled.blocker).toBe("");
  expect(filled.filled).toBe(2);

  for(const doc of [
    {kind:"cv",target:chooseResumeField(inspected.elements),bytes:CV,
      filename:"SmartPloy-CV.pdf"},
    {kind:"letter",target:chooseCoverLetterField(inspected.elements),bytes:LETTER,
      filename:"SmartPloy-Cover-Letter.pdf"},
  ]){
    const payload={
      application_url:JOB,inspected_url:JOB,...doc.target,kind:doc.kind,
      file_name:doc.filename,size:doc.bytes.length,
      sha256:sha(doc.bytes),base64:doc.bytes.toString("base64")
    };
    const response=await page.evaluate(async v=>
      (window as any).attachReviewedPdf(v),payload);
    expect(response.status,response.reason).toBe("attached_locally");
  }
  const latest=await page.evaluate(()=> (window as any).inspectForm());
  const questions=planReviewedQuestions(latest.elements);
  const memory=suggestSavedAnswers(questions,[{
    question:"How did you hear about us?",answer:ANSWER
  }]);
  expect(memory.values).toEqual([ANSWER]);
  expect(memory.needsReview).toEqual([]);
  const actions=validateReviewedAnswers(questions,memory.values);
  const qFilled=await page.evaluate(async ({actions,url})=>
    (window as any).fillReviewedAnswers(actions,url,url),
    {actions,url:JOB});
  expect(qFilled.status,qFilled.reason).toBe("filled_for_review");

  const reviewed={
    application_url:JOB,cv_pdf_sha256:sha(CV),cv_pdf_size:CV.length,
    letter_pdf_sha256:sha(LETTER),letter_pdf_size:LETTER.length,
    email:EMAIL,full_name:NAME,cover_letter:LETTER_TEXT
  };
  const dry=await page.evaluate(async v=>
    (window as any).submitReviewedLeverOnce({...v,dry_run:true}),reviewed);
  expect(dry.preflight_ready,dry.reason).toBe(true);
  expect(await page.evaluate(()=> (window as any).employerSubmitClicks)).toBe(0);
  const claim=await smartPage.evaluate(async (v)=>
    (window as any).reserveFinalClickOnSmartPloy(v),{
      workspace_id:WORKSPACE,expected_revision:2,
      expected_document_sha256:"d".repeat(64),
      expected_cv_pdf_sha256:sha(CV),expected_cv_pdf_size:CV.length,
      expected_letter_pdf_sha256:sha(LETTER),expected_letter_pdf_size:LETTER.length,
      expected_saved_answers_sha256:"a".repeat(64),
      expected_fields_sha256:"b".repeat(64),
      expected_application_url_sha256:createHash("sha256").update(JOB).digest("hex"),
      confirm_one_job_final_click:true,
      acknowledge_external_employer_transfer:true,
      acknowledge_no_automatic_retry:true
    });
  expect(claim.claim_reserved,claim.reason).toBe(true);
  expect(serverClaims).toBe(1);

  // Test harness simulates the extension's separately tested local durable
  // no-retry lock. Actual employer final logic is executed on this DOM.
  const clicked=await page.evaluate(async v=>
    (window as any).submitReviewedLeverOnce(v),reviewed);
  expect(clicked.attempted,clicked.reason).toBe(true);
  expect(clicked.provider_acknowledged).toBe(false);
  expect(await page.evaluate(()=> (window as any).employerSubmitClicks)).toBe(1);
  expect(exactReceiptPage(page.url(),JOB)).toBe(true);
  const receipt=await page.evaluate(async url=>
    (window as any).inspectReceipt(url),JOB);
  expect(receipt.confirmed,receipt.explanation).toBe(true);
  expect(receipt.reference).toBe("SYN-REF-2026");
  const saved=await smartPage.evaluate(async (data)=>
    (window as any).saveOneObservedReceiptOnSmartPloy(data),{
      workspace_id:WORKSPACE,confirm_user_observed:true,
      receipt:{
        schema:"smartploy.browser_receipt.v1",
        workspace_id:WORKSPACE,document_revision:2,
        document_sha256:"d".repeat(64),
        application_url:JOB,
        confirmation_page_url:receipt.confirmation_page_url,
        reference:receipt.reference,
        confirmation_page_sha256:receipt.confirmation_page_sha256,
        observed_at:new Date().toISOString(),confirmed_visible:true
      }
    });
  expect(saved.saved,saved.reason).toBe(true);
  expect(saved.external_confirmation_verified).toBe(false);
  expect(serverReceipts).toBe(1);
  expect(employerOutbound).toBe(0);
  const retry=await page.evaluate(async v=>
    (window as any).submitReviewedLeverOnce(v),reviewed);
  expect(retry.attempted).toBe(false);
  submitClicks=await page.evaluate(()=> (window as any).employerSubmitClicks);
  expect(submitClicks).toBe(1);
});
