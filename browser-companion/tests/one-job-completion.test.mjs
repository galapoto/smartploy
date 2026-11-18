/** Execute the ACTUAL one-job popup orchestration with no employer requests.
 * This is a synthetic full journey contract, not a claim that production
 * employer acceptance occurred. Every external browser/owner action is mocked.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

const file=readFileSync(new URL("../popup.mjs",import.meta.url),"utf8");
const start=file.indexOf("async function onCompleteOneJob() {");
const end=file.indexOf("\nasync function onResumeReceipt() {",start);
assert.ok(start>0 && end>start,"real one-job completion must be present");
const actual=file.slice(start,end);
const JOB="https://jobs.lever.co/synthetic/test123/apply";

function mount({
  firstReady=true,secondReady=true,allowConsent=true,
  allowReceipt=true,serverAllows=true,employerConfirms=true,
  actuallyClicked=true,changedProfile=false,
  changedAfterConsent=false,missingInitialSnapshot=false,
  serverOutcomeUncertain=false,serverThrowsAfterClaim=false,
}={}) {
  const records=[],nodes=new Map();
  const packet={
    application_url:JOB,company:"Synthetic Employer",role_title:"Analyst",
    workspace_id:"kit-"+"a".repeat(30)
  };
  const tab={id:8,url:JOB};
  let dryCount=0;
  const getNode=id=>{
    if(!nodes.has(id))nodes.set(id,{value:"",disabled:false,
      textContent:"",hidden:false,checked:false});
    return nodes.get(id);
  };
  getNode("packet").value="reviewed-synthetic-packet";
  const context={
    completingOneJob:false,receiptOnly:false,
    currentPacket:packet,targetTabId:8,attemptReserved:false,
    oneJobClaimMayExist:false,
    inspectedUrl:JOB,preflightPassed:false,oneJobFinalApproval:false,
    oneJobSubmitWasAttempted:false,oneJobFormSnapshotSha256:"",
    $:getNode,
    window:{confirm:message=>{
      records.push(message.startsWith("COMPLETE")?"final-consent":"receipt-consent");
      return message.startsWith("COMPLETE")?allowConsent:allowReceipt;
    }},
    isLeverFinalProvider:()=>true,
    isSmartPloyTab:()=>true,
    exactLeverForm:()=>true,
    exactReceiptPage:url=>url.includes("/thanks"),
    validatePacket:()=>packet,
    requireVerifiedReview:async()=>{records.push("current-review-marker");},
    requireFreshOwnerReview:async()=>{
      records.push("fresh-owner-profile");
      if(changedProfile) throw Error("Profile changed");
    },
    activeTab:async()=>({...tab}),
    hasPriorLeverAttempt:async()=>false,
    signedInAppTab:async()=>({id:3,url:"https://smartploy.komplyint.fi/"}),
    finalEmployerBinding:()=>({dry_run:true}),
    finalOneJobClaimBinding:async()=>({source:"exact-signed-in-profile"}),
    submitReviewedLeverOnce:function submitReviewedLeverOnce(){},
    reserveFinalClickOnSmartPloy:function reserveFinalClickOnSmartPloy(){},
    saveOneObservedReceiptOnSmartPloy:function saveOneObservedReceiptOnSmartPloy(){},
    chrome:{storage:{session:{}},scripting:{
      executeScript:async p=>{
        if(p.func.name==="submitReviewedLeverOnce"){
          dryCount++;records.push("dry-run-"+dryCount);
          return [{frameId:0,result:{
            preflight_ready:dryCount===1?firstReady:secondReady,
            form_snapshot_sha256:dryCount===1 && missingInitialSnapshot ?
              "" : dryCount===2 && changedAfterConsent ?
              "f".repeat(64) : "e".repeat(64),
            reason:"required-fields-missing"
          }}];
        }
        if(p.func.name==="reserveFinalClickOnSmartPloy"){
          records.push("server-one-use-claim");
          assert.equal(p.target.tabId,3);
          if(serverThrowsAfterClaim) throw Error("The claim response was lost");
          return [{frameId:0,result:{claim_reserved:serverAllows && !serverOutcomeUncertain,
            reason:serverOutcomeUncertain?"outcome_uncertain_check_attempt_status":
              "unavailable_or_not_authorized",
            claim_id:"employer-claim-"+"f".repeat(32)}}];
        }
        if(p.func.name==="saveOneObservedReceiptOnSmartPloy"){
          records.push("save-owner-receipt");
          assert.equal(p.args[0].receipt.reference,"SYN-REF-2026");
          return [{frameId:0,result:{saved:true}}];
        }
        throw Error("Unexpected extension action: "+p.func.name);
      }
    }},
    recordOneUseFinalAttempt:async()=>{records.push("claim-stored-before-click");},
    onSubmit:async()=>{
      assert.equal(context.oneJobFinalApproval,true);
      assert.equal(context.preflightPassed,true);
      assert.equal(context.oneJobFormSnapshotSha256,"e".repeat(64));
      context.oneJobFinalApproval=false;
      records.push("one-permitted-employer-click");
      context.oneJobSubmitWasAttempted=actuallyClicked;
      if(actuallyClicked && employerConfirms)tab.url=JOB.replace("/apply","/thanks");
    },
    onReceipt:async()=>{
      records.push("inspect-visible-confirmation");
      getNode("receiptExport").value=JSON.stringify({
        schema:"smartploy.browser_receipt.v1",
        reference:"SYN-REF-2026",confirmed_visible:true,
        workspace_id:packet.workspace_id
      });
    },
    normalizeError:e=>e?.message||"Unknown",
    status:(s)=>{records.push("status:"+s);},
    PacketError:class PacketError extends Error{},
    Promise,
    setTimeout:cb=>cb(),
  };
  runInNewContext(actual+"\nthis.completeOneJob=onCompleteOneJob;",context);
  return {complete:context.completeOneJob,context,records,tab};
}
test("complete one exact synthetic job: 2 PDF preflights → consent → owner claim → one click → reference → save",async()=>{
  const {complete,records}=mount();
  assert.equal(await complete(),true);
  const filter=records.filter(x=>!x.startsWith("status:") &&
    x!=="current-review-marker" && x!=="fresh-owner-profile");
  assert.deepEqual(filter,[
    "dry-run-1","final-consent","dry-run-2","server-one-use-claim",
    "claim-stored-before-click","one-permitted-employer-click",
    "inspect-visible-confirmation","receipt-consent","save-owner-receipt"
  ]);
});
test("incomplete documents never cause a server attempt or employer click",async()=>{
  const {complete,records}=mount({firstReady:false});
  assert.equal(await complete(),false);
  assert.equal(records.includes("server-one-use-claim"),false);
  assert.equal(records.includes("one-permitted-employer-click"),false);
});
test("declining applicant's irreversible final consent cannot reserve employer claim",async()=>{
  const {complete,records}=mount({allowConsent:false});
  assert.equal(await complete(),false);
  assert.equal(records.includes("server-one-use-claim"),false);
});
test("reactive employer form changes after consent do not consume one-use claim",async()=>{
  const {complete,records}=mount({secondReady:false});
  assert.equal(await complete(),false);
  assert.equal(records.includes("server-one-use-claim"),false);
});

test("changed answer or submit destination AFTER approval never consumes claim",async()=>{
  const {complete,records}=mount({changedAfterConsent:true});
  assert.equal(await complete(),false);
  assert.equal(records.includes("final-consent"),true);
  assert.equal(records.filter(x=>x.startsWith("dry-run-")).length,2);
  assert.equal(records.includes("server-one-use-claim"),false);
  assert.equal(records.includes("one-permitted-employer-click"),false);
  assert.equal(records.some(x=>x.includes("changed after your approval")),true);
});

test("missing initial form fingerprint blocks before consent and claim",async()=>{
  const {complete,records}=mount({missingInitialSnapshot:true});
  assert.equal(await complete(),false);
  assert.equal(records.includes("final-consent"),false);
  assert.equal(records.includes("server-one-use-claim"),false);
  assert.equal(records.includes("one-permitted-employer-click"),false);
});
test("independent server permission denial never submits one job",async()=>{
  const {complete,records}=mount({serverAllows:false});
  assert.equal(await complete(),false);
  assert.equal(records.includes("one-permitted-employer-click"),false);
});
test("a click without employer confirmation is NOT a completed application",async()=>{
  const {complete,records}=mount({employerConfirms:false});
  assert.equal(await complete(),false);
  assert.equal(records.filter(s=>s==="one-permitted-employer-click").length,1);
  assert.equal(records.includes("save-owner-receipt"),false);
});
test("applicant can decline receipt persistence after a real visible confirmation",async()=>{
  const {complete,records}=mount({allowReceipt:false});
  assert.equal(await complete(),false);
  assert.equal(records.includes("inspect-visible-confirmation"),true);
  assert.equal(records.includes("save-owner-receipt"),false);
});

test("a real one-use click leaves Finish and Start disabled; receipt recovery stays available",async()=>{
  const {complete,context,records}=mount();
  assert.equal(await complete(),true);
  assert.equal(context.oneJobClaimMayExist,true);
  assert.equal(context.$("finishOneJob").disabled,true);
  assert.match(context.$("finishOneJob").textContent,/check confirmation/i);
  assert.equal(context.$("startAutoApply").disabled,true);
  assert.equal(context.$("receipt").disabled,false);
  assert.match(context.$("finalClaimInfo").textContent,/no[t]?\s+.*submit|do not/i);
  assert.equal(await complete(),false);
  assert.equal(records.filter(x=>x==="one-permitted-employer-click").length,1);
});

test("lost server response locks one-job repeat before a second irreversible claim",async()=>{
  for(const option of [{serverOutcomeUncertain:true},{serverThrowsAfterClaim:true}]){
    const {complete,context,records}=mount(option);
    assert.equal(await complete(),false);
    assert.equal(context.oneJobClaimMayExist,true);
    assert.equal(context.$("finishOneJob").disabled,true);
    assert.equal(context.$("startAutoApply").disabled,true);
    assert.equal(context.$("receipt").disabled,false);
    assert.equal(records.filter(x=>x==="server-one-use-claim").length,1);
    assert.equal(records.includes("one-permitted-employer-click"),false);
    assert.equal(await complete(),false);
    assert.equal(records.filter(x=>x==="server-one-use-claim").length,1);
  }
});

test("a definite rejected authorization does not pretend a claim was consumed",async()=>{
  const {complete,context,records}=mount({serverAllows:false});
  assert.equal(await complete(),false);
  assert.equal(context.oneJobClaimMayExist,false);
  assert.equal(context.$("startAutoApply").disabled,false);
  assert.equal(records.includes("one-permitted-employer-click"),false);
});
