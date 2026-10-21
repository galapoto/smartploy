/** SP15d: exercise actual first-party injected function in synthetic Chromium.
 * No real applicant, SmartPloy server or employer is contacted.
 */
import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

const SITE = "https://smartploy.obumai.com/";
const API = SITE + "api/v1/application-workspaces/kit-" + "a".repeat(30) +
  "/verify-reviewed-packet";
const origin = "https://smartploy.obumai.com";
const documentSha="b".repeat(64),pdfSha="c".repeat(64);
const payload={
  workspace_id:"kit-"+"a".repeat(30),expected_revision:2,
  expected_document_sha256:documentSha,expected_cv_pdf_sha256:pdfSha,
  expected_fields_sha256:"135df071b9de4a37fd07681b9a61b09c8e2bfe6bbba4df84108c69168176403c",
  expected_application_url_sha256:"5e7b33db375658c5dd70e418de459e97f7c050c5f6d86045a86345be15c01227",
  expected_cv_pdf_size:87522,
};
const approved={
  review_verified:true,review_state:"pending",
  expires_at:"2099-01-01T00:00:00Z",
  automatic_employer_submit_authorized:false,
  external_actions_performed:false,browser_grant_issued:false
};

async function inject(page:Page) {
  const source=await readFile(
    new URL("../../browser-companion/page-review.mjs",import.meta.url),"utf8"
  );
  await page.addScriptTag({
    content:source.replace("export async function verifyReviewOnSmartPloy(",
      "window.verifyReviewOnSmartPloy = async function verifyReviewOnSmartPloy(")
  });
}
async function act(page:Page, value:Record<string,unknown>=payload) {
  return page.evaluate(async (input)=>
    (window as any).verifyReviewOnSmartPloy(input) as Promise<{
      review_verified:boolean;reason?:string;expires_at?:string;
      automatic_employer_submit_authorized?:boolean
    }>,value);
}

test("real site-origin browser function verifies exact reviewed packet without leaking session",async({page})=>{
  let requests:string[]=[],body:any=null,accountHeader="",crossSite=0;
  await page.route("**/*",async route=>{
    const req=route.request(), url=req.url();
    requests.push(url);
    if(url===SITE){
      await route.fulfill({status:200,contentType:"text/html",body:
        "<!doctype html><title>SmartPloy signed-in application review</title>"});
    }else if(url===origin+"/api/v1/session"){
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({authenticated:true,auth_source:"oidc",
          user_id:"usr-"+"a".repeat(32),email:"PRIVATE@example.invalid"})});
    }else if(url===API){
      accountHeader=req.headers()["x-smartploy-expected-user-id"];
      body=req.postDataJSON();
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify(approved)});
    }else{crossSite++;await route.abort();}
  });
  await page.goto(SITE);await inject(page);
  const output=await act(page);
  expect(output).toEqual(approved);
  expect(accountHeader).toBe("usr-"+"a".repeat(32));
  expect(body).toEqual({
    expected_revision:2,expected_document_sha256:documentSha,
    expected_cv_pdf_sha256:pdfSha,
    expected_fields_sha256:payload.expected_fields_sha256,
    expected_application_url_sha256:payload.expected_application_url_sha256,
    expected_cv_pdf_size:payload.expected_cv_pdf_size
  });
  expect(requests).toEqual([SITE,origin+"/api/v1/session",API]);
  expect(crossSite).toBe(0);
  expect(JSON.stringify(output)).not.toContain("usr-");
  expect(JSON.stringify(output)).not.toContain("PRIVATE");
});

test("signed-out or switched-account validation failure denies without any employer request",async({page})=>{
  let login=true,apiCount=0,outside=0;
  await page.route("**/*",async route=>{
    const req=route.request(),url=req.url();
    if(url===SITE)await route.fulfill({status:200,contentType:"text/html",body:"<html></html>"});
    else if(url===origin+"/api/v1/session"){
      await route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify(login?{authenticated:true,auth_source:"oidc",
          user_id:"usr-"+"b".repeat(32)}:
          {authenticated:false,auth_source:"anonymous"})});
    }else if(url===API){
      apiCount++;
      await route.fulfill({status:409,contentType:"application/json",
        body:JSON.stringify({error:{code:"account_precondition_failed"}})});
    }else{outside++;await route.abort();}
  });
  await page.goto(SITE);await inject(page);
  const failed=await act(page);
  expect(failed).toEqual({review_verified:false,reason:"review_stale_or_missing"});
  expect(apiCount).toBe(1);
  login=false;
  expect(await act(page)).toEqual({review_verified:false,reason:"sign_in_required"});
  expect(apiCount).toBe(1);
  expect(outside).toBe(0);
});

test("no website spoofing: employer origin cannot call SmartPloy review bridge",async({page})=>{
  const JOB="https://jobs.lever.co/fictional/99999999-1111-4111-8111-111111111111/apply";
  let outward=0;
  await page.route("**/*",async route=>{
    if(route.request().url()===JOB){
      await route.fulfill({status:200,contentType:"text/html",
        body:"<!doctype html><form><button type=submit>Submit application</button></form>"});
    }else {outward++;await route.abort();}
  });
  await page.goto(JOB);await inject(page);
  expect(await act(page)).toEqual({review_verified:false,reason:"wrong_origin"});
  expect(outward).toBe(0);
  expect(await page.locator("button").count()).toBe(1);
});

test("unrecognized workspace, forged document revision or hash stops before HTTP",async({page})=>{
  let apiCount=0;
  await page.route("**/*",async route=>{
    if(route.request().url()===SITE)
      await route.fulfill({status:200,contentType:"text/html",body:"<html></html>"});
    else{apiCount++;await route.abort();}
  });
  await page.goto(SITE);await inject(page);
  for(const patch of [
    {workspace_id:"../other-user"},{expected_revision:0},
    {expected_document_sha256:"x"},{expected_cv_pdf_sha256:"bad"},
    {expected_fields_sha256:"corrupt"},{expected_application_url_sha256:"short"},
    {expected_cv_pdf_size:0}
  ])expect(await act(page,{...payload,...patch}))
    .toEqual({review_verified:false,reason:"invalid_binding"});
  expect(apiCount).toBe(0);
});
