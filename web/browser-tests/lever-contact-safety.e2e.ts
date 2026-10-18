/** Isolated Chromium test of the EXISTING SmartPloy contact field executor.
 * Reads the actual popup implementation; never contacts an employer. */
import {readFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";

const JOB="https://jobs.lever.co/fictional-org/99999999-0000-4000-8000-123456789abc/apply";

async function setup(page:Page) {
  let outside=0;
  await page.route("**/*",async route=>{
    if(route.request().url!==JOB){outside++;await route.abort();return;}
    await route.fulfill({status:200,contentType:"text/html",body:[
      '<!doctype html><html><body><form id="apply">',
      '<label for="contact">Email</label><input id="contact" name="email" type="email" required>',
      '<label for="legal">Visa sponsorship</label><input id="legal" name="visaStatus" type="text">',
      '<button type="submit" id="send">Submit application</button></form>',
      '<script>window.submitted=0;window.changed=0;',
      'document.querySelector("form").addEventListener("submit",e=>{e.preventDefault();window.submitted++;});',
      'document.querySelector("#contact").addEventListener("change",()=>window.changed++);',
      '</script></body></html>'
    ].join("")});
  });
  await page.goto(JOB);
  const source=await readFile(new URL("../../browser-companion/popup.mjs",import.meta.url),"utf8");
  const start=source.indexOf("function fillPlanned(actions, exactUrl) {");
  const end=source.indexOf("\nfunction inspectFinalSubmit(",start);
  if(start<0||end<=start)throw Error("Original browser contact executor not found");
  await page.addScriptTag({content:source.slice(start,end)+"\nwindow.fillPlanned=fillPlanned;"});
  return ()=>outside;
}

function action(overrides:Record<string,unknown>={}) {
  return {index:0,key:"email",value:"person@example.invalid",label:"Email",
    expected_id:"contact",expected_name:"email",expected_type:"email",...overrides};
}
async function run(page:Page,actions:Record<string,unknown>[]=[action()],url=JOB) {
  return page.evaluate(({a,url})=>(window as any).fillPlanned(a,url) as {
    filled:number;skipped:number;blocker:string
  },{a:actions,url});
}

test("reviewed ordinary email fills through original native setter without submission",async ({page})=>{
  const outside=await setup(page);
  const result=await run(page);
  expect(result).toEqual({filled:1,skipped:0,blocker:""});
  expect(await page.locator("#contact").inputValue()).toBe("person@example.invalid");
  expect(await page.locator("#legal").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).changed)).toBe(1);
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
  expect(outside()).toBe(0);
});

test("changed visible question label with same element identity is rejected",async ({page})=>{
  await setup(page);
  await page.locator('label[for="contact"]').evaluate(el=>el.textContent="Work authorization");
  const result=await run(page);
  expect(result.blocker).toMatch(/identity|label|metadata/i);
  expect(await page.locator("#contact").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
});

test("camouflaged sensitive field metadata cannot be filled even with approved email label",async ({page})=>{
  await setup(page);
  await page.locator("#contact").evaluate(el=>el.setAttribute("name","visaStatus"));
  const verdict=await run(page,[action({expected_name:"visaStatus"})]);
  expect(verdict.blocker).toMatch(/identity|label|metadata/i);
  expect(await page.locator("#contact").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
});

test("duplicated live contact label refuses to select an arbitrary field",async ({page})=>{
  await setup(page);
  await page.evaluate(()=>{
    const form=document.querySelector("form")!;
    const label=document.createElement("label");label.textContent="Email";label.htmlFor="extra_email";
    const input=document.createElement("input");input.id="extra_email";input.name="alternateEmail";input.type="email";
    form.append(label,input);
  });
  const verdict=await run(page);
  expect(verdict.blocker).toMatch(/Duplicate/i);
  expect(await page.locator("#contact").inputValue()).toBe("");
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
});

test("React detachment after input is reported as uncertain, not successful submission",async ({page})=>{
  await setup(page);
  await page.locator("#contact").evaluate(el=>{
    el.addEventListener("input",()=>{
      const replacement=el.cloneNode(true);
      el.replaceWith(replacement);
    },{once:true});
  });
  const verdict=await run(page);
  expect(verdict.blocker).toMatch(/changed after contact field input/i);
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
});

test("new required field inserted on last input is a blocked partial fill",async ({page})=>{
  const outside=await setup(page);
  await page.locator("#contact").evaluate(el=>{
    el.addEventListener("input",()=>{
      const input=document.createElement("input");input.required=true;input.name="new_question";
      el.closest("form")?.append(input);
    },{once:true});
  });
  const verdict=await run(page);
  expect(verdict.filled).toBe(1);
  expect(verdict.blocker).toMatch(/changed after contact field input/i);
  expect(await page.evaluate(()=>(window as any).submitted)).toBe(0);
  expect(outside()).toBe(0);
});
