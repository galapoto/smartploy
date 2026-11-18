/** Execute the original popup inspector and receipt-only UI transition.
 * Synthetic local controls; no profile, employer request or actual submission.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

const popup=readFileSync(new URL("../popup.mjs",import.meta.url),"utf8");
const css=readFileSync(new URL("../popup.css",import.meta.url),"utf8");
const enterStart=popup.indexOf("function enterReceiptMode() {");
const enterEnd=popup.indexOf("\nfunction status(",enterStart);
const inspectStart=popup.indexOf("async function onInspect() {");
const inspectEnd=popup.indexOf("\nasync function onFill() {",inspectStart);
assert.ok(enterStart>0 && enterEnd>enterStart);
assert.ok(inspectStart>0 && inspectEnd>inspectStart);
const realFunctions=popup.slice(enterStart,enterEnd)+
  "\n"+popup.slice(inspectStart,inspectEnd);

function mount({localAttempt=true,uncertainClaim=false,serverAttempt=false,
  serverUnavailable=false}={}){
  const records=[],nodes=new Map();
  const job="https://jobs.lever.co/test/actualjob/apply";
  const packet={application_url:job,workspace_id:"kit-"+"a".repeat(30)};
  const node=id=>{
    if(!nodes.has(id)) nodes.set(id,{
      disabled:false,hidden:true,checked:false,value:"",textContent:"",
      setAttribute:()=>{},replaceChildren:()=>{}
    });
    return nodes.get(id);
  };
  node("packet").value="reviewed-packet";
  const state={
    currentPacket:null,targetTabId:null,inspectedUrl:"",
    currentPlan:null,currentQuestionPlan:null,attemptReserved:false,
    oneJobClaimMayExist:uncertainClaim,receiptOnly:false,
    preflightPassed:true,receiptCheckSequence:0,$:node,
    clearReceiptObservation:()=>{state.receiptCheckSequence++;},
    activeTab:async()=>({id:4,url:job}),
    validatePacket:()=>packet,
    isLeverFinalProvider:()=>true,
    inspectOwnFinalActionReadiness:async()=>{
      records.push("read-owner-server-attempt");
      return serverUnavailable ?
        {ready:false,reason:"readiness_unavailable"} :
        {ready:!serverAttempt,reason:serverAttempt?
          "previous_employer_attempt_reserved":"ready",
          previous_employer_attempt_reserved:serverAttempt};
    },
    hasPriorLeverAttempt:async()=>{
      records.push("read-local-attempt");
      return localAttempt;
    },
    requireVerifiedReview:async()=>{records.push("incorrect-reenable-review");},
    chrome:{scripting:{executeScript:async()=>{records.push("incorrect-employer-injection");}}},
    status:v=>records.push(v),
    normalizeError:error=>error?.message||"unknown",
    PacketError:class PacketError extends Error{},
  };
  runInNewContext(realFunctions+"\nthis.inspect=onInspect;",state);
  return {inspect:state.inspect,state,node,records,packet};
}

test("already reserved employer job opens only read-only receipt recovery",async()=>{
  const {inspect,state,node,records,packet}=mount();
  await inspect();
  assert.equal(state.currentPacket,packet);
  assert.equal(state.attemptReserved,true);
  assert.equal(state.receiptOnly,true);
  assert.equal(node("submission").hidden,false);
  assert.equal(node("finishOneJob").disabled,true);
  assert.equal(node("startAutoApply").disabled,true);
  assert.equal(node("fill").disabled,true);
  assert.equal(node("attach").disabled,true);
  assert.equal(node("fillQuestions").disabled,true);
  assert.equal(node("submit").disabled,true);
  assert.equal(node("receipt").disabled,false);
  assert.match(node("finalClaimInfo").textContent,/check My applications/i);
  assert.equal(records.includes("incorrect-employer-injection"),false);
  assert.equal(records.includes("incorrect-reenable-review"),false);
});

test("uncertain server claim prevents even read-only inspector from rearming job",async()=>{
  const {inspect,state,node,records}=mount({
    uncertainClaim:true,localAttempt:false
  });
  await inspect();
  assert.equal(state.receiptOnly,true);
  assert.equal(node("finishOneJob").disabled,true);
  assert.equal(node("startAutoApply").disabled,true);
  assert.equal(records.includes("read-local-attempt"),false);
});

test("consumed final action never visually regains a bright hover and keeps accessible status",()=>{
  assert.match(css,/\.start-autoapply:hover:not\(:disabled\)/);
  assert.match(css,/\.start-autoapply:disabled:hover/);
  assert.match(css,/\.start-autoapply:disabled,[\s\S]*box-shadow:none/);
  const html=readFileSync(new URL("../popup.html",import.meta.url),"utf8");
  assert.match(html,/id="finalClaimInfo" role="status"/);
  assert.match(html,/id="feedback" role="status" aria-live="polite"/);
  assert.match(html,/id="receipt"/);
});

test("after popup reload the server-only consumed claim is still recovery-only",async()=>{
  const {inspect,state,node,records}=mount({
    localAttempt:false,uncertainClaim:false,serverAttempt:true
  });
  await inspect();
  assert.equal(state.attemptReserved,true);
  assert.equal(state.receiptOnly,true);
  assert.equal(node("startAutoApply").disabled,true);
  assert.equal(node("finishOneJob").disabled,true);
  assert.equal(node("receipt").disabled,false);
  assert.equal(records.includes("read-owner-server-attempt"),true);
  assert.equal(records.includes("incorrect-reenable-review"),false);
  assert.equal(records.includes("incorrect-employer-injection"),false);
});

test("cannot safely rearm a claimed Lever job while signed-in attempt status is unavailable",async()=>{
  const {inspect,node,records}=mount({localAttempt:false,serverUnavailable:true});
  await inspect();
  assert.equal(records.includes("incorrect-reenable-review"),false);
  assert.equal(records.includes("incorrect-employer-injection"),false);
  assert.equal(node("plan").hidden,true);
  assert.equal(records.some(s=>/cannot verify prior employer attempts/i.test(s)),true);
});
