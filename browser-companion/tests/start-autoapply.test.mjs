/** Real source orchestration checks; no network, employer, or applicant data. */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

const popup = readFileSync(new URL("../popup.mjs", import.meta.url), "utf8");
const html = readFileSync(new URL("../popup.html", import.meta.url), "utf8");
const begin = popup.indexOf("async function onStartAutoApply() {");
const end = popup.indexOf("\nasync function onAttach() {", begin);
assert.ok(begin > 0 && end > begin, "existing real Start function required");
const source = popup.slice(begin, end);

function mount(override = {}) {
  const button = {disabled:false};
  const calls = [];
  const context = {
    startAutoApplyInFlight:false, currentPlan:null, currentQuestionPlan:null,
    currentPacket:null, targetTabId:null, inspectedUrl:"",
    receiptOnly:false, attemptReserved:false,
    $:id=>{assert.equal(id,"startAutoApply");return button;},
    onInspect:async()=>{
      calls.push("inspect");
      context.currentPlan={actions:[{key:"email"}]};
      context.currentPacket={application_url:"https://jobs.lever.co/fictional/one"};
      context.targetTabId=7;
    },
    onFill:async()=>{calls.push("fill");return true;},
    onReviewQuestions:async()=>{calls.push("questions");},
    normalizeError:()=> "Please inspect the employer form manually.",
    status:s=>calls.push("status:"+s),
    ...override,
  };
  runInNewContext(source+"\nthis.launch=onStartAutoApply;",context);
  return {context,button,calls,launch:context.launch};
}
test("one visible Start chains observed exact-job inspect, consented fill, then read-only questions",async()=>{
  const {launch,calls,button}=mount();
  await launch();
  assert.deepEqual(calls,["inspect","fill","questions"]);
  assert.equal(button.disabled,false);
  assert.doesNotMatch(source,/^[^/\n]*\b(?:onSubmit|onAttach|onFillQuestions|onReserveFinalAttempt)\s*\(/m);
  assert.match(html,/id="startAutoApply"/);
  assert.match(html,/Manual controls &amp; safety details/);
  assert.match(popup,/await requireVerifiedReview\(chrome\.storage\?\.session, currentPacket\)/);
  assert.match(popup,/if \(!window\.confirm\(/);
});
test("question-only and upload-only applications continue to review without a fake contact fill",async()=>{
  for (const plan of [{actions:[],skippedUploads:[]},{actions:[],skippedUploads:[{key:"cv"}]}]) {
    const {launch,calls,context,button}=mount({
      onInspect:async()=>{
        calls.push("inspect");
        context.currentPlan=plan;
        context.currentPacket={application_url:"https://jobs.ashbyhq.com/example/job"};
        context.targetTabId=7;
      },
      onFill:async()=>{calls.push("unexpected-fill");return false;},
    });
    await launch();
    assert.deepEqual(calls,["inspect","questions"]);
    assert.equal(button.disabled,false);
  }
});
test("successful zero-write real fill continues, while cancelled fill does not",async()=>{
  const start=popup.indexOf("async function onFill() {");
  const finish=popup.indexOf("\n/** One AutoApply action",start);
  assert.ok(start>0&&finish>start);
  const fragment=popup.slice(start,finish);
  function mountFill(approve) {
    const nodes=new Map(),writes=[];
    const url="https://jobs.lever.co/fictional/one/apply";
    const scope={
      receiptOnly:false,
      currentPacket:{application_url:url},
      currentPlan:{actions:[{key:"email"}]},
      targetTabId:7,inspectedUrl:url,
      currentQuestionPlan:null,
      preflightPassed:false,
      window:{confirm:()=>approve},
      activeTab:async()=>({id:7,url}),
      validatePacket:()=>{},
      currentPacketToJSON:()=>({application_url:url}),
      requireVerifiedReview:async()=>{},
      exactAssistedForm:()=>true,
      fillPlanned:()=>{},
      chrome:{storage:{session:{}},scripting:{executeScript:async()=> {
        writes.push("execute");
        return [{result:{filled:0,skipped:1,blocker:""}}];
      }}},
      $:id=>{
        if(!nodes.has(id))nodes.set(id,{
          hidden:false,disabled:false,replaceChildren:()=>{}
        });
        return nodes.get(id);
      },
      status:()=>{},normalizeError:()=> "Safe failure",
    };
    runInNewContext(fragment+"\nthis.fillActual=onFill;",scope);
    return {scope,writes};
  }
  const accepted=mountFill(true);
  assert.equal(await accepted.scope.fillActual(),true);
  assert.deepEqual(accepted.writes,["execute"]);
  const declined=mountFill(false);
  assert.equal(await declined.scope.fillActual(),false);
  assert.deepEqual(declined.writes,[]);
});
test("failed or changed form inspection cannot reuse a previous plan",async()=>{
  const {launch,calls,context,button}=mount({
    onInspect:async()=>{calls.push("inspect-blocked");}
  });
  context.currentPlan={actions:[{key:"email"}]};
  context.currentPacket={application_url:"https://jobs.lever.co/old/role"};
  context.targetTabId=11;
  await launch();
  assert.deepEqual(calls,["inspect-blocked"]);
  assert.equal(context.currentPlan,null);
  assert.equal(context.currentPacket,null);
  assert.equal(context.targetTabId,null);
  assert.equal(button.disabled,false);
});
test("declined or uncertain fill stops before question-flow",async()=>{
  const {launch,calls,button}=mount({onFill:async()=>{calls.push("not-approved");return false;}});
  await launch();
  assert.deepEqual(calls,["inspect","not-approved"]);
  assert.equal(button.disabled,false);
});
test("two concurrent Start clicks have one active scan only",async()=>{
  let proceed;
  const held=new Promise(resolve=>{proceed=resolve;});
  const {launch,calls,button}=mount({onInspect:async()=>{calls.push("inspect");await held;}});
  const first=launch();
  assert.equal(button.disabled,true);
  const second=launch();
  proceed();
  await Promise.all([first,second]);
  assert.deepEqual(calls,["inspect"]);
  assert.equal(button.disabled,false);
});
test("unexpected inspection rejection restores controls and reports safe blocker",async()=>{
  const {launch,calls,button}=mount({onInspect:async()=>{throw Error("SENSITIVE_DETAILS");}});
  await launch();
  assert.deepEqual(calls,["status:Please inspect the employer form manually."]);
  assert.equal(button.disabled,false);
});
