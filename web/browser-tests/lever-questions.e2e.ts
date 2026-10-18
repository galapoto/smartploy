/** Synthetic browser acceptance of approved employer text questions only.
 * A real employer, applicant account or final submit is NEVER contacted.
 */
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const JOB_URL = "https://jobs.lever.co/synthetic-org/99999999-0000-4000-8000-123456789abc/apply";

const syntheticHtml = [
  "<!doctype html><html><body>",
  "<form id='job'>",
  "<label for='email'>Email</label><input id='email' type='email' required value='approved@example.invalid'>",
  "<label for='why'>Why are you interested in this role?</label>",
  "<textarea id='why' name='questions[why]' required></textarea>",
  "<label for='project'>Describe a Python project you delivered</label>",
  "<input id='project' name='questions[project]' type='text' required>",
  "<label for='salary'>Expected salary</label>",
  "<input id='salary' name='questions[salary]' type='text' required>",
  "<label for='terms'>I agree to employer privacy terms</label>",
  "<input id='terms' type='checkbox' required>",
  "<button type='submit'>Submit application</button>",
  "</form>",
  "<script>",
  "window.events=[]; window.submitCount=0; window.injectDrift=false;",
  "document.getElementById('job').addEventListener('submit',e=>{e.preventDefault();window.submitCount++;});",
  "document.getElementById('why').addEventListener('change',()=>{",
  "window.events.push('why-change');",
  "if(window.injectDrift){const extra=document.createElement('input');",
  "extra.id='new_required';extra.required=true;",
  "document.getElementById('project').before(extra);}",
  "});",
  "document.getElementById('project').addEventListener('change',()=>window.events.push('project-change'));",
  "</script></body></html>"
].join("\n");

async function setup(page: Page) {
  let outside = 0;
  await page.route("**/*", async route => {
    if (route.request().url() !== JOB_URL) {
      outside++;
      await route.abort();
      return;
    }
    await route.fulfill({status:200,contentType:"text/html",body:syntheticHtml});
  });
  await page.goto(JOB_URL);
  const source=await readFile(
    new URL("../../browser-companion/page-questions.mjs",import.meta.url),"utf8"
  );
  await page.addScriptTag({
    content:source.replace(
      "export function fillReviewedAnswers(",
      "window.fillReviewedAnswers = function fillReviewedAnswers("
    )
  });
  return () => outside;
}

function why(value = "I reviewed an accurate example of relevant experience.") {
  return {
    index:1,label:"Why are you interested in this role?",type:"textarea",
    expected_id:"why",expected_name:"questions[why]",
    expected_placeholder:"",expected_max_length:-1,value
  };
}
function project(value = "I developed a Python reporting project with approved evidence.") {
  return {
    index:2,label:"Describe a Python project you delivered",type:"text",
    expected_id:"project",expected_name:"questions[project]",
    expected_placeholder:"",expected_max_length:-1,value
  };
}
function salary(value = "80000 EUR") {
  return {
    index:3,label:"Expected salary",type:"text",
    expected_id:"salary",expected_name:"questions[salary]",
    expected_placeholder:"",expected_max_length:-1,value
  };
}
async function act(page: Page, actions: Record<string,unknown>[], url = JOB_URL) {
  return page.evaluate(async ({actions, url, inspected}) =>
    (window as any).fillReviewedAnswers(actions,url,inspected) as
      {status:string;filled:number;reason:string},
  {actions,url,inspected:JOB_URL});
}

test("two human-reviewed answers fill only correct fields; never click submit",async ({page})=>{
  const outside=await setup(page);
  const result=await act(page,[why(),project()]);
  expect(result.status).toBe("filled_for_review");
  expect(result.filled).toBe(2);
  const state=await page.evaluate(()=>{
    const value=(id:string)=>(document.getElementById(id) as HTMLInputElement).value;
    return {
      why:value("why"),project:value("project"),salary:value("salary"),
      terms:(document.getElementById("terms") as HTMLInputElement).checked,
      submits:(window as any).submitCount,events:(window as any).events
    };
  });
  expect(state).toEqual({
    why:why().value,project:project().value,salary:"",terms:false,
    submits:0,events:["why-change","project-change"]
  });
  expect(outside()).toBe(0);
});

test("wrong job, changed question identity, protected salary and duplicates fail before filling",async ({page})=>{
  const outside=await setup(page);
  const variants=[
    {actions:[why()],url:JOB_URL.replace("synthetic-org","other")},
    {actions:[why(),salary()]},
    {actions:[project({} as never)]},
    {actions:[why(),why()]},
    {actions:[{...why(),expected_name:"different"}]},
    {actions:[{...why(),label:"Different question"}]},
    {actions:[{...why(),value:"x".repeat(1501)}]},
  ];
  for(const item of variants){
    const result=await act(page,item.actions,item.url);
    expect(result.status,JSON.stringify(item).slice(0,120)).toBe("blocked");
  }
  expect(await page.locator("#why").inputValue()).toBe("");
  expect(await page.locator("#project").inputValue()).toBe("");
  expect(outside()).toBe(0);
});

test("existing answers and hidden questions are not overwritten",async ({page})=>{
  await setup(page);
  await page.locator("#why").fill("Employer-provided original answer");
  expect((await act(page,[why()])).status).toBe("blocked");
  await page.locator("#why").fill("");
  await page.locator("#why").evaluate((el:HTMLElement)=>{el.hidden=true;});
  expect((await act(page,[why()])).status).toBe("blocked");
});

test("SPA inserts a field on change: browser stops before writing to shifted second control",async ({page})=>{
  await setup(page);
  await page.evaluate(()=>{(window as any).injectDrift=true;});
  const result=await act(page,[why(),project()]);
  expect(result.status).toBe("partial_needs_review");
  expect(result.filled).toBe(1);
  expect(await page.locator("#why").inputValue()).toBe(why().value);
  expect(await page.locator("#project").inputValue()).toBe("");
});

test("unknown consent control remains untouched even after partial text answer",async ({page})=>{
  await setup(page);
  const result=await act(page,[why()]);
  expect(result.status).toBe("filled_for_review");
  expect(await page.locator("#terms").isChecked()).toBe(false);
  expect(await page.evaluate(()=>(window as any).submitCount)).toBe(0);
});
