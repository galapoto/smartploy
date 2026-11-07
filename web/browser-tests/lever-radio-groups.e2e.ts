/** V4 synthetic Chromium radio-group parity. No real employer contact or submission. */
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const JOB = "https://jobs.lever.co/synthetic-org/99999999-0000-4000-8000-123456789abc/apply";
const HTML = `<!doctype html><html><body>
<form id="job">
  <fieldset>
    <legend>Where did you hear about this job?</legend>
    <label><input id="friend" name="job_source" type="radio" value="friend">Friend referral</label>
    <label><input id="board" name="job_source" type="radio" value="job-board" required>Job board</label>
  </fieldset>
  <fieldset>
    <legend>Are you authorized to work in Finland?</legend>
    <label><input id="legalyes" name="workAuthorization" type="radio" value="yes">Yes</label>
    <label><input id="legalno" name="workAuthorization" type="radio" value="no" required>No</label>
  </fieldset>
  <button type="submit">Submit</button>
</form>
<script>window.submits=0;document.getElementById("job").addEventListener("submit",e=>{
e.preventDefault();window.submits++;});</script></body></html>`;
async function setup(page:Page) {
  let outside=0;
  await page.route("**/*",async route=>{
    if(route.request().url()!==JOB) {outside++; await route.abort();return;}
    await route.fulfill({status:200,contentType:"text/html",body:HTML});
  });
  await page.goto(JOB);
  const code=await readFile(
    new URL("../../browser-companion/page-questions.mjs",import.meta.url),"utf8");
  await page.addScriptTag({content:code.replace(
    "export async function fillReviewedAnswers(",
    "window.extensionFillReviewed = async function fillReviewedAnswers(",
  )});
  return ()=>outside;
}
function approved(value="job-board") {
  return {
    index:0,label:"Where did you hear about this job?",type:"radio_group",
    expected_id:"friend",expected_name:"job_source",
    expected_placeholder:"",expected_max_length:-1,max_answer_length:150,
    options:[
      {index:0,id:"friend",value:"friend",label:"Friend referral"},
      {index:1,id:"board",value:"job-board",label:"Job board"}
    ],value
  };
}
async function fill(page:Page, actions:unknown[], url=JOB) {
  return page.evaluate(async input=>
    (window as any).extensionFillReviewed(input.actions,input.url,JOB),
    {actions,url}
  );
}
test("radio selection is exact and observed after event settling",async({page})=>{
  const outside=await setup(page);
  const result=await fill(page,[approved()]);
  expect(result.status).toBe("filled_for_review");
  expect(result.filled).toBe(1);
  expect(await page.locator("#board").isChecked()).toBe(true);
  expect(await page.locator("#friend").isChecked()).toBe(false);
  expect(await page.locator("#legalyes").isChecked()).toBe(false);
  expect(await page.locator("#legalno").isChecked()).toBe(false);
  expect(await page.evaluate(()=>(window as any).submits)).toBe(0);
  expect(outside()).toBe(0);
});
test("React-like employer state receives an exact radio click once",async({page})=>{
  const outside=await setup(page);
  await page.locator("#board").evaluate(el=>{
    (window as any).radioClicks=0;
    (window as any).radioSaved=false;
    el.addEventListener("click",()=>{
      (window as any).radioClicks++;
      (window as any).radioSaved=(el as HTMLInputElement).checked;
    });
  });
  const outcome=await fill(page,[approved()]);
  expect(outcome.status).toBe("filled_for_review");
  expect(outcome.filled).toBe(1);
  expect(await page.evaluate(()=>(window as any).radioClicks)).toBe(1);
  expect(await page.evaluate(()=>(window as any).radioSaved)).toBe(true);
  expect(await page.evaluate(()=>(window as any).submits)).toBe(0);
  expect(outside()).toBe(0);
});
test("changed radio identity, protected eligibility and answer guesses stop",async({page})=>{
  const outside=await setup(page);
  for(const bad of [
    {...approved(),value:"Job board"},
    {...approved(),options:[approved().options[0], {...approved().options[1],id:"wrong"}]},
    {...approved(),label:"Are you authorized to work in Finland?"},
    {...approved(),expected_name:"workAuthorization"}
  ]) {
    const verdict=await fill(page,[bad]);
    expect(verdict.status).toBe("blocked");
    expect(verdict.filled).toBe(0);
  }
  expect(await page.locator("#board").isChecked()).toBe(false);
  expect(await page.locator("#legalyes").isChecked()).toBe(false);
  expect(await page.evaluate(()=>(window as any).submits)).toBe(0);
  expect(outside()).toBe(0);
});
test("reactive delayed radio reset never counts as a filled choice",async({page})=>{
  const outside=await setup(page);
  await page.locator("#board").evaluate(el=>{
    el.addEventListener("change",()=>{
      setTimeout(()=>{(el as HTMLInputElement).checked=false;},25);
    },{once:true});
  });
  const result=await fill(page,[approved()]);
  expect(result.status).toBe("blocked");
  expect(result.filled).toBe(0);
  expect(await page.locator("#board").isChecked()).toBe(false);
  expect(await page.evaluate(()=>(window as any).submits)).toBe(0);
  expect(outside()).toBe(0);
});
