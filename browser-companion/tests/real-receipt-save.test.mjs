/** Source-level browser orchestration: no employer network or actual submission. */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

const popup=readFileSync(new URL("../popup.mjs",import.meta.url),"utf8");
const saveBegin=popup.indexOf("let savingObservedReceipt = false;");
const saveEnd=popup.indexOf('\n$("verifyReview").addEventListener',saveBegin);
assert.ok(saveBegin>=0 && saveEnd>saveBegin,"real manual receipt action must be wired");
const saveSource=popup.slice(saveBegin,saveEnd);

const permissionBegin=popup.indexOf("async function inspectOwnFinalActionReadiness(");
const permissionEnd=popup.indexOf("\nasync function onVerifySmartPloyReview()",permissionBegin);
assert.ok(permissionBegin>=0 && permissionEnd>permissionBegin,"real readiness helper required");
const permissionSource=popup.slice(permissionBegin,permissionEnd);

const JOB="https://jobs.lever.co/fictional/one";
const WORKSPACE="kit-"+"a".repeat(30);
const packet={
  workspace_id:WORKSPACE,revision:2,document_sha256:"b".repeat(64),
  application_url:JOB,company:"Fictional",role_title:"Engineer"
};
const visible={
  confirmed:true,reference:"SYN-REF-2026",
  confirmation_page_url:JOB+"/confirmation",
  confirmation_page_sha256:"c".repeat(64)
};
const receipt={
  schema:"smartploy.browser_receipt.v1",workspace_id:WORKSPACE,
  document_revision:packet.revision,document_sha256:packet.document_sha256,
  application_url:JOB,reference:visible.reference,
  confirmation_page_url:visible.confirmation_page_url,
  confirmation_page_sha256:visible.confirmation_page_sha256,
  observed_at:"2026-11-18T00:00:00Z",confirmed_visible:true
};

function mountSave({
  consent=true,serverSaved=true,tabId=7,scan=visible,
  receiptOverride={},changeAfterConsent=false,priorClaim=false,
  appTabAvailable=true
}={}){
  const p={...packet},r={...receipt,...receiptOverride};
  const nodes={
    receiptPanel:{hidden:false},
    receiptExport:{value:JSON.stringify(r)},
    packet:{value:JSON.stringify(p)},
    saveReceipt:{disabled:false,textContent:"Save to My applications"}
  };
  const calls=[];
  const scope={
    URL,receiptOnly:true,currentPacket:p,targetTabId:7,
    $:id=>{assert.ok(nodes[id],"unexpected node "+id);return nodes[id];},
    activeTab:async()=>({id:tabId,url:visible.confirmation_page_url}),
    exactReceiptPage:(active,expected)=>expected===JOB &&
      active===visible.confirmation_page_url,
    validateReviewPacket:s=>JSON.parse(s),
    hasPriorLeverAttempt:async()=>priorClaim,
    requireVerifiedReview:async()=>{calls.push("owner-review");},
    inspectReceipt:function inspectReceipt(){},
    saveOneObservedReceiptOnSmartPloy:function saveOneObservedReceiptOnSmartPloy(){},
    signedInAppTab:async()=>{
      calls.push("signed-in-app");
      if(!appTabAvailable)throw Error("Owner app unavailable");
      return {id:30};
    },
    chrome:{storage:{session:{}},scripting:{
      executeScript:async ({func})=>{
        if(func.name==="inspectReceipt"){
          calls.push("scan");
          return [{frameId:0,result:scan}];
        }
        assert.equal(func.name,"saveOneObservedReceiptOnSmartPloy");
        calls.push("account-write");
        return [{frameId:0,result:{saved:serverSaved,
          reason:serverSaved?"":"receipt_not_saved_check_application"}}];
      }
    }},
    window:{confirm:()=>{
      calls.push("consent");
      if(changeAfterConsent){
        nodes.receiptExport.value=JSON.stringify({...r,reference:"CHANGED"});
      }
      return consent;
    }},
    PacketError:class extends Error{},
    normalizeError:error=>String(error?.message || "Unexpected error"),
    status:(message,success=false)=>calls.push({message,success})
  };
  runInNewContext(saveSource+"\nthis.saveReceipt=onSaveObservedReceipt;",scope);
  return {save:scope.saveReceipt,calls,nodes};
}

test("a matching manual receipt is freshly scanned and saved directly to the signed-in account",async()=>{
  const {save,calls,nodes}=mountSave();
  assert.equal(await save(),true);
  assert.deepEqual(calls.filter(x=>typeof x==="string"),[
    "owner-review","scan","consent","scan","signed-in-app",
    "scan","account-write"
  ]);
  assert.equal(nodes.saveReceipt.disabled,true);
  assert.equal(nodes.saveReceipt.textContent,"Saved to My applications");
  assert.equal(calls.at(-1).success,true);
  assert.match(calls.at(-1).message,/unverified/i);
  assert.doesNotMatch(saveSource,/\b(?:onSubmit|reserveFinalClickOnSmartPloy)\s*\(/);
});

test("declined receipt save consent leaves the employer untouched and no account POST",async()=>{
  const {save,calls,nodes}=mountSave({consent:false});
  assert.equal(await save(),false);
  assert.equal(calls.includes("account-write"),false);
  assert.equal(nodes.saveReceipt.disabled,false);
});
test("another tab, stale receipt, forged reference, or changed confirmation never saves",async()=>{
  for(const options of [
    {tabId:9},
    {receiptOverride:{document_revision:4}},
    {receiptOverride:{workspace_id:"kit-"+"f".repeat(30)}},
    {receiptOverride:{reference:"?"}},
    {receiptOverride:{confirmation_page_url:JOB+"/another"}},
    {scan:{...visible,confirmed:false}},
    {scan:{...visible,reference:"OTHER-REF"}},
    {scan:{...visible,confirmation_page_sha256:"e".repeat(64)}},
    {changeAfterConsent:true},
  ]){
    const {save,calls,nodes}=mountSave(options);
    assert.equal(await save(),false,JSON.stringify(options));
    assert.equal(calls.includes("account-write"),false,JSON.stringify(options));
    assert.equal(nodes.saveReceipt.disabled,false,JSON.stringify(options));
  }
});
test("lost or denied owner receipt persistence is not retried without checking My applications",async()=>{
  const {save,calls,nodes}=mountSave({serverSaved:false});
  assert.equal(await save(),false);
  assert.equal(calls.filter(x=>x==="account-write").length,1);
  assert.equal(nodes.saveReceipt.disabled,true);
  assert.match(calls.at(-1).message,/not confirmed/i);
  assert.equal(await save(),false);
  assert.equal(calls.filter(x=>x==="account-write").length,1);
});
test("missing signed-in SmartPloy app never sends receipt anywhere",async()=>{
  const {save,calls,nodes}=mountSave({appTabAvailable:false});
  assert.equal(await save(),false);
  assert.equal(calls.includes("account-write"),false);
  assert.equal(nodes.saveReceipt.disabled,false);
});

async function mountReadiness({permission=true,enabled=true,frameId=0}={}){
  const calls=[],context={
    signedInAppTab:async()=>({id:30}),
    readOneJobFinalActionReadinessOnSmartPloy:
      function readOneJobFinalActionReadinessOnSmartPloy(){},
    chrome:{scripting:{executeScript:async request=>{
      assert.equal(request.func.name,"readOneJobFinalActionReadinessOnSmartPloy");
      // VM-created arrays have a different realm prototype. Compare values, not prototypes.
      assert.equal(request.args.length,1);
      assert.equal(request.args[0],WORKSPACE);
      calls.push("signed-in-first-party-readiness");
      return [{frameId,result:{
        ready:permission && enabled,
        reason:!permission?"employer_permission_not_approved":
          !enabled?"browser_final_click_disabled":"ready"
      }}];
    }}}
  };
  runInNewContext(permissionSource+
    "\nthis.readiness=inspectOwnFinalActionReadiness;",context);
  return {result:await context.readiness(WORKSPACE),calls};
}
test("popup uses only the injected first-party readiness helper, never direct network",async()=>{
  const allowed=await mountReadiness();
  assert.equal(allowed.result.ready,true);
  assert.deepEqual(allowed.calls,["signed-in-first-party-readiness"]);
  // The popup readiness helper itself stays network-free; the separately
  // injected owner-workspace probe performs read-only first-party fetches.
  assert.doesNotMatch(permissionSource,/\bfetch\s*\(/);
  for(const options of [{permission:false},{enabled:false},{frameId:9}]){
    const denied=await mountReadiness(options);
    assert.equal(denied.result.ready,false,JSON.stringify(options));
  }
});
