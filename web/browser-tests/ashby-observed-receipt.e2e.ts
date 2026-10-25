/** SP42 — browser-origin observation, never provider-issued employer ACK.
 * Run the REAL serialized companion inspector against isolated synthetic
 * employer confirmation pages. No network traffic reaches an employer. */
import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";

const origin = "https://jobs.ashbyhq.com";
const posting = "/synthetic-fi/junior-data-analyst";
const confirmation = origin + posting + "/application/confirmation";
const reference = "ASHBY-RECEIPT-4567";
const originalLever = "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc/apply";

async function setup(page:Page,url=confirmation,{
  phrase="Thank you for your application. Confirmation ID: "+reference,
  submit=false,
}={}){
  let attemptedTraffic=0;
  const requested=new URL(url);
  requested.hash=""; // URL fragments are never included in HTTP requests.
  await page.route("**/*",async route=>{
    if (route.request().url() !== requested.href) {
      attemptedTraffic++;
      await route.abort();
      return;
    }
    await route.fulfill({status:200,contentType:"text/html",body:
      `<!DOCTYPE html><html><body><main><h1>Application</h1><p>`+phrase+
      `</p>`+(submit?`<button>Submit application</button>`:``)+
      `</main></body></html>`});
  });
  await page.goto(url);
  const source=await readFile(
    new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8"
  );
  const start=source.indexOf("async function inspectReceipt(");
  const stop=source.indexOf("\n/* Ashby has NO",start);
  if(start<0 || stop<=start)throw Error("Original receipt inspector is missing");
  await page.addScriptTag({content:source.slice(start,stop)+
    "\nwindow.inspectReceipt=inspectReceipt;"});
  return ()=>attemptedTraffic;
}
async function observe(page:Page,jobPath=posting,account="synthetic-fi"){
  return page.evaluate(
    ({expectedOrigin,expectedAccount,expectedPosting})=>
      (window as any).inspectReceipt(expectedOrigin,expectedAccount,expectedPosting),
    {expectedOrigin:origin,expectedAccount:account,expectedPosting:jobPath}
  );
}

test("SP42 actual Ashby confirmation inspector exports only job URL, reference and hash",async ({page})=>{
  const traffic=await setup(page,confirmation+"?private=do-not-copy#anything");
  const finding=await observe(page);
  expect(finding.confirmed).toBe(true);
  expect(finding.reference).toBe(reference);
  expect(finding.confirmation_page_url).toBe(confirmation);
  expect(finding.confirmation_page_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(JSON.stringify(finding)).not.toContain("do-not-copy");
  expect(JSON.stringify(finding)).not.toContain("anything");
  expect(await page.locator("button").count()).toBe(0);
  expect(traffic()).toBe(0);
});

test("SP42 a sibling Ashby job cannot yield a browser receipt for selected job",async ({page})=>{
  const traffic=await setup(page,origin+"/synthetic-fi/another-job/application/confirmation");
  const finding=await observe(page);
  expect(finding.confirmed).toBe(false);
  expect(traffic()).toBe(0);
});

test("SP42 similar text without stable reference or with live Submit never qualifies",async ({page})=>{
  await setup(page,confirmation,{phrase:"Thank you for your application."});
  expect((await observe(page)).confirmed).toBe(false);
});

test("SP42 an unfinished Ashby application form cannot masquerade as a completed one",async ({page})=>{
  await setup(page,confirmation,{submit:true});
  expect((await observe(page)).confirmed).toBe(false);
});

test("SP42 historical Lever observation path still accepts only tenant scope",async ({page})=>{
  const host="https://jobs.lever.co";
  await page.route("**/*",async route=>{
    if(route.request().url()!==originalLever) return route.abort();
    await route.fulfill({status:200,contentType:"text/html",
      body:"<!doctype html><html><body>Thank you for your application. Reference: LEVER-12345</body></html>"});
  });
  await page.goto(originalLever);
  const source=await readFile(new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8");
  const start=source.indexOf("async function inspectReceipt(");
  const stop=source.indexOf("\n/* Ashby has NO",start);
  await page.addScriptTag({content:source.slice(start,stop)+"\nwindow.inspectReceipt=inspectReceipt;"});
  const finding=await page.evaluate(
    ({host,account})=>(window as any).inspectReceipt(host,account),
    {host,account:"synthetic"}
  );
  expect(finding.confirmed).toBe(true);
  expect(finding.reference).toBe("LEVER-12345");
});
