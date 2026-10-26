/** SP47: run the actual serialized receipt observer in real Chromium.
 * Every document is supplied by an isolated route fixture. No live employer
 * access, application submission, generated provider receipt or API calls. */
import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";

const LEVER = "https://jobs.lever.co/synthetic-fi/analyst-123/apply";
const GREENHOUSE = "https://boards.greenhouse.io/synthetic-fi/jobs/123456";

async function fixture(page:Page,activeUrl:string,{
  body="Thank you for your application. Confirmation ID: SYNTHETIC-REF-1234",
  liveSubmit=false,
}={}){
  let unexpectedTraffic=0;
  const requested=new URL(activeUrl);
  requested.hash="";
  await page.route("**/*",async route=>{
    if(route.request().url()!==requested.href || route.request().method()!=="GET"){
      unexpectedTraffic++;
      return route.abort();
    }
    return route.fulfill({status:200,contentType:"text/html",body:
      "<!doctype html><html><body><main><p>"+body+"</p>"+
      (liveSubmit?"<button>Submit application</button>":"")+"</main></body></html>"});
  });
  await page.goto(activeUrl);
  const source=await readFile(new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8");
  const start=source.indexOf("async function inspectReceipt(");
  const stop=source.indexOf("\n/* Ashby has NO",start);
  if(start<0 || stop<=start)throw new Error("Original standalone receipt inspector missing");
  await page.addScriptTag({content:source.slice(start,stop)+
    "\nwindow.inspectReceipt=inspectReceipt;"});
  return ()=>unexpectedTraffic;
}

async function observe(page:Page,applicationUrl:string){
  return page.evaluate(expectedUrl=>(window as any).inspectReceipt(expectedUrl),applicationUrl);
}

test("SP47 manual Lever confirmation retains exact posting identity and drops private URL data",async ({page})=>{
  const confirmation="https://jobs.lever.co/synthetic-fi/analyst-123/thanks";
  const traffic=await fixture(page,confirmation+"?private=discard#secret");
  const result=await observe(page,LEVER);
  expect(result.confirmed).toBe(true);
  expect(result.reference).toBe("SYNTHETIC-REF-1234");
  expect(result.confirmation_page_url).toBe(confirmation);
  expect(result.confirmation_page_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(JSON.stringify(result)).not.toContain("discard");
  expect(JSON.stringify(result)).not.toContain("secret");
  expect(traffic()).toBe(0);
});

for(const [label,pageUrl] of [
  ["sibling job", "https://jobs.lever.co/synthetic-fi/other-job/thanks"],
  ["similar job prefix", "https://jobs.lever.co/synthetic-fi/analyst-123-other/thanks"],
  ["tenant-wide thank-you page", "https://jobs.lever.co/synthetic-fi/thanks"],
]) test("SP47 real Lever observer refuses "+label,async ({page})=>{
  const traffic=await fixture(page,pageUrl);
  expect((await observe(page,LEVER)).confirmed).toBe(false);
  expect(traffic()).toBe(0);
});

test("SP47 Greenhouse legacy-to-modern confirmation observes only the unchanged board and numeric job",async ({page})=>{
  const confirmation="https://job-boards.greenhouse.io/synthetic-fi/jobs/123456/confirmation";
  const traffic=await fixture(page,confirmation+"?private=discard#secret");
  const result=await observe(page,GREENHOUSE);
  expect(result.confirmed).toBe(true);
  expect(result.reference).toBe("SYNTHETIC-REF-1234");
  expect(result.confirmation_page_url).toBe(confirmation);
  expect(result.confirmation_page_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(JSON.stringify(result)).not.toMatch(/discard|secret/);
  expect(traffic()).toBe(0);
});

for(const [label,pageUrl] of [
  ["sibling job", "https://job-boards.greenhouse.io/synthetic-fi/jobs/123457/confirmation"],
  ["another board", "https://job-boards.greenhouse.io/other-board/jobs/123456/confirmation"],
  ["tenant-wide confirmation", "https://job-boards.greenhouse.io/synthetic-fi/confirmation"],
]) test("SP47 real Greenhouse observer refuses "+label,async ({page})=>{
  const traffic=await fixture(page,pageUrl);
  expect((await observe(page,GREENHOUSE)).confirmed).toBe(false);
  expect(traffic()).toBe(0);
});

test("SP47 Greenhouse visible success without reference remains a manual self-report",async ({page})=>{
  const traffic=await fixture(page,GREENHOUSE,{body:"Thank you for your application."});
  expect((await observe(page,GREENHOUSE)).confirmed).toBe(false);
  expect(traffic()).toBe(0);
});

test("SP47 Greenhouse unfinished form cannot supply a receipt from success-like text",async ({page})=>{
  const traffic=await fixture(page,GREENHOUSE,{liveSubmit:true});
  expect((await observe(page,GREENHOUSE)).confirmed).toBe(false);
  expect(traffic()).toBe(0);
});

test("SP47 a confirmation disappearing during async hashing is not exported",async ({page})=>{
  const traffic=await fixture(page,GREENHOUSE);
  await page.evaluate(()=>{
    const digest=crypto.subtle.digest.bind(crypto.subtle);
    crypto.subtle.digest=async (...args:Parameters<typeof digest>)=>{
      const value=await digest(...args);
      document.querySelector("main")!.textContent="The confirmation is no longer visible.";
      return value;
    };
  });
  expect((await observe(page,GREENHOUSE)).confirmed).toBe(false);
  expect(traffic()).toBe(0);
});
