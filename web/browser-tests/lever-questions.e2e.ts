/** SP14: only synthetic local Lever DOM; no real employer traffic or account. */
import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";

const URL_JOB = "https://jobs.lever.co/fictional-org/12345678-1234-1234-1234-123456789abc/apply";

async function prepare(page:Page) {
  let externalRequests=0;
  await page.route("**/*",async route=>{
    if(route.request().url()!==URL_JOB){externalRequests++;await route.abort();return;}
    await route.fulfill({
      status:200,contentType:"text/html",
      body:[
        '<!doctype html><html><body><form id="application">',
        '<label for="q_source">How did you hear about us?</label>',
        '<input id="q_source" name="source" type="text" maxlength="180">',
        '<label for="q_motivation">Why are you interested in this position?</label>',
        '<textarea id="q_motivation" name="motivation" maxlength="1200"></textarea>',
        '<label for="q_salary">Salary expectation</label>',
        '<input id="q_salary" name="salaryExpectation" type="text">',
        '<button id="submit" type="submit">Submit application</button></form>',
        '<script>window.questionChanges=0;window.submissions=0;',
        'document.querySelector("form").addEventListener("submit",e=>{e.preventDefault();window.submissions++;});',
        'for(const el of document.querySelectorAll("input,textarea")){',
        'el.addEventListener("change",()=>window.questionChanges++);',
        '}</script></body></html>'
      ].join("")
    });
  });
  await page.goto(URL_JOB);
  const source=await readFile(new URL("../../browser-companion/page-questions.mjs",import.meta.url),"utf8");
  await page.addScriptTag({content:source.replace(
    "export function fillReviewedQuestions(",
    "window.fillReviewedQuestions = function fillReviewedQuestions("
  )});
  return ()=>externalRequests;
}

function action(overrides:Record<string,unknown>={}) {
  return {
    key:"applicant_reviewed_question",
    index:0,
    question_kind:"source",
    expected_id:"q_source",
    expected_name:"source",
    expected_type:"text",
    expected_label:"How did you hear about us?",
    value:"Company careers page",
    ...overrides
  };
}

function payload(overrides:Record<string,unknown>={}) {
  return {
    application_url:URL_JOB,
    inspected_url:URL_JOB,
    actions:[action()],
    ...overrides
  };
}
async function run(page:Page,data:Record<string,unknown>) {
  return page.evaluate((params)=>
    (window as any).fillReviewedQuestions(params) as {status:string;filled:number;reason:string},
    data);
}

test("owner-typed ordinary answers fill exact text fields, leaving sensitive data and submit untouched",async ({page})=>{
  const external=await prepare(page);
  const reply=await run(page,payload({actions:[
    action(),
    action({index:1,question_kind:"motivation",expected_id:"q_motivation",
      expected_name:"motivation",expected_type:"textarea",
      expected_label:"Why are you interested in this position?",
      value:"I am motivated by practical data quality improvements."})
  ]}));
  expect(reply.status,reply.reason).toBe("filled_locally");
  expect(reply.filled).toBe(2);
  const saved=await page.evaluate(()=>({
    source:(document.querySelector("#q_source") as HTMLInputElement).value,
    motivation:(document.querySelector("#q_motivation") as HTMLTextAreaElement).value,
    salary:(document.querySelector("#q_salary") as HTMLInputElement).value,
    changes:(window as any).questionChanges,
    submitted:(window as any).submissions
  }));
  expect(saved).toEqual({
    source:"Company careers page",
    motivation:"I am motivated by practical data quality improvements.",
    salary:"",changes:2,submitted:0
  });
  expect(external()).toBe(0);
});

test("wrong job, changed URL, changed field identity or sensitive attribute is blocked",async ({page})=>{
  const external=await prepare(page);
  for(const delta of [
    {application_url:URL_JOB.replace("fictional-org","another-employer")},
    {inspected_url:URL_JOB+"?other=1"},
    {actions:[action({expected_id:"q_salary"})]},
    {actions:[action({expected_name:"salaryExpectation"})]},
    {actions:[action({expected_type:"textarea"})]},
    {actions:[action({expected_label:"Why are you interested in this role?"})]},
    {actions:[action({value:"x".repeat(181)})]},
    {actions:[action({question_kind:"visa"})]},
    {actions:[action(),action()]},
  ]){
    const verdict=await run(page,payload(delta));
    expect(verdict.status,JSON.stringify(delta)).toBe("blocked");
  }
  await page.locator("#q_source").evaluate(el=>el.setAttribute("name","visaStatus"));
  expect((await run(page,payload())).status).toBe("blocked");
  await page.locator("#q_source").evaluate(el=>el.setAttribute("name","source"));
  await page.locator("label[for='q_source']").evaluate(el=>el.textContent="Gender identity");
  expect((await run(page,payload())).status).toBe("blocked");
  expect(await page.locator("#q_source").inputValue()).toBe("");
  expect(await page.locator("#q_salary").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).submissions)).toBe(0);
  expect(external()).toBe(0);
});

test("duplicate live label and already answered field cannot be overwritten",async ({page})=>{
  await prepare(page);
  await page.locator("label[for='q_motivation']").evaluate(el=>el.textContent="How did you hear about us?");
  expect((await run(page,payload())).status).toBe("blocked");
  await page.locator("label[for='q_motivation']").evaluate(el=>el.textContent="Why are you interested in this position?");
  await page.locator("#q_source").fill("Already supplied by applicant");
  expect((await run(page,payload())).status).toBe("blocked");
  expect(await page.locator("#q_source").inputValue()).toBe("Already supplied by applicant");
  expect(await page.evaluate(()=>(window as any).submissions)).toBe(0);
});

test("React-like rerender during input is uncertain; no automatic retries or final click",async ({page})=>{
  const external=await prepare(page);
  await page.locator("#q_source").evaluate(el=>{
    el.addEventListener("input",()=>{
      const replacement=el.cloneNode(true) as HTMLElement;
      el.replaceWith(replacement);
    },{once:true});
  });
  const verdict=await run(page,payload());
  expect(verdict.status).toBe("uncertain");
  expect(await page.evaluate(()=>(window as any).submissions)).toBe(0);
  expect(external()).toBe(0);
});

test("hidden or disabled questions and challenges remain outside owner reviewed fill",async ({page})=>{
  await prepare(page);
  await page.locator("#q_source").evaluate(el=>(el as HTMLInputElement).disabled=true);
  expect((await run(page,payload())).status).toBe("blocked");
  await page.locator("#q_source").evaluate(el=>(el as HTMLInputElement).disabled=false);
  await page.locator("#q_source").evaluate(el=>(el as HTMLInputElement).hidden=true);
  expect((await run(page,payload())).status).toBe("blocked");
  expect(await page.evaluate(()=>(window as any).submissions)).toBe(0);
});
