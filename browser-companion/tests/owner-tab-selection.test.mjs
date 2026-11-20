/** Regression for the real SmartPloy popup: multiple first-party tabs must not
 * block one exact account-owned job. All external HTTP and Chrome calls are
 * synthetic; no applicant data or employer network actions are used.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import {PacketError} from "../logic.mjs";
import {isSmartPloyTab} from "../review-bridge.mjs";

const source=readFileSync(new URL("../popup.mjs",import.meta.url),"utf8");
const job="https://jobs.lever.co/fictional/one/apply";
const account="https://smartploy.komplyint.fi/";
const packet={
  workspace_id:"kit-"+"a".repeat(30),revision:3,application_url:job,
  letter_pdf_sha256:"b".repeat(64),letter_pdf_size:40,
  cv_pdf_sha256:"c".repeat(64),cv_pdf_size:40,
  saved_answers_sha256:"d".repeat(64),
  saved_answers:[{question:"How did you hear about us?",answer:"Company website"}],
  fields:{email:"test@example.invalid"}
};
const ownerTabs=[
  {id:6,url:"https://smartploy.komplyint.fi/?other-account=1"},
  {id:7,url:"https://smartploy.komplyint.fi/applications"}
];
function sliceBetween(start,end) {
  const index=source.indexOf(start),stop=source.indexOf(end,index);
  assert.ok(index>=0 && stop>index,"real popup function boundary must exist: "+start);
  return source.slice(index,stop);
}
function mountSelector(probe) {
  const calls=[];
  const code=sliceBetween("async function signedInAppTab(","\n/** Read-only: learn");
  const scope={
    PacketError,isSmartPloyTab,
    chrome:{
      tabs:{query:async()=>ownerTabs},
      scripting:{executeScript:async(request)=>{
        calls.push(request);
        return [{frameId:0,result:{owner_verified:probe(request.target.tabId)}}];
      }}
    }
  };
  runInNewContext(code+"\nthis.selectOwner=signedInAppTab;",scope);
  return {select:scope.selectOwner,calls};
}
test("two SmartPloy tabs: select exact account-owned workspace, not first unrelated tab",async()=>{
  const {select,calls}=mountSelector(id=>id===7);
  const chosen=await select(packet);
  assert.equal(chosen.id,7);
  assert.equal(calls.length,2);
  for(const request of calls){
    assert.equal(request.world,"ISOLATED");
    assert.equal(request.func.name,"inspectOwnWorkspaceOnSmartPloy");
    assert.equal(request.args[0].workspace_id,packet.workspace_id);
    assert.equal(request.args[0].revision,3);
    assert.equal(request.args[0].application_url,job);
    assert.doesNotMatch(JSON.stringify(request.args),/Company website|test@example/);
  }
});
test("two tabs for the same verified owner are allowed without duplicate writes",async()=>{
  const {select,calls}=mountSelector(()=>true);
  assert.equal((await select(packet)).id,6);
  assert.equal(calls.length,1);
});
test("no matching signed-in owner is fail-closed, never select another account",async()=>{
  const {select,calls}=mountSelector(()=>false);
  await assert.rejects(select(packet),PacketError);
  assert.equal(calls.length,2);
});
function mountWorkspaceProbe({origin="https://smartploy.komplyint.fi",
  auth=true,workspaceId=packet.workspace_id,revision=3,applicationUrl=job,
  workspaceStatus=200}={}){
  const begin=source.indexOf("async function inspectOwnWorkspaceOnSmartPloy(");
  assert.ok(begin>0,"real isolated-world owner/workspace probe is required");
  const end=source.indexOf("\nasync function signedInAppTab(",begin);
  assert.ok(end>begin,"probe must remain standalone before tab selection");
  const code=source.slice(begin,end),requests=[];
  const frame={};frame.top=frame;frame.self=frame;
  const scope={URL,encodeURIComponent,
    location:{origin,protocol:"https:"},window:frame,
    fetch:async(url,options)=>{
      requests.push({url,options});
      if(url==="/api/v1/session")return {
        ok:true,json:async()=>({authenticated:auth,auth_source:auth?"oidc":"none"})
      };
      return {ok:workspaceStatus===200,json:async()=>({
        workspace:{workspace_id:workspaceId,revision,application_url:applicationUrl,
          cv_text:"PRIVATE DOCUMENT DO NOT RETURN"}
      })};
    }
  };
  runInNewContext(code+"\nthis.probe=inspectOwnWorkspaceOnSmartPloy;",scope);
  return {probe:scope.probe,requests};
}
test("first-party probe confirms exact workspace, revision and job without returning applicant data",async()=>{
  const {probe,requests}=mountWorkspaceProbe();
  const result=await probe({
    workspace_id:packet.workspace_id,revision:packet.revision,application_url:job
  });
  assert.equal(result.owner_verified,true);
  assert.equal(Object.keys(result).length,1);
  assert.equal(requests.length,2);
  for(const r of requests){
    assert.equal(r.options.credentials,"same-origin");
    assert.equal(r.options.cache,"no-store");
    assert.equal(r.options.redirect,"error");
  }
  assert.doesNotMatch(JSON.stringify(result),/PRIVATE DOCUMENT/);
});
test("first-party probe blocks wrong session, revision, URL, missing workspace and false origin",async()=>{
  for(const options of [
    {auth:false},{revision:4},{applicationUrl:"https://jobs.lever.co/other/job/apply"},
    {workspaceStatus:404},{origin:"https://attacker.example"}
  ]) {
    const {probe}=mountWorkspaceProbe(options);
    const result=await probe({
      workspace_id:packet.workspace_id,revision:packet.revision,application_url:job
    });
    assert.equal(result.owner_verified,false,JSON.stringify(options));
  }
});
test("fresh packet review finds its matching owner even with a second SmartPloy tab",async()=>{
  const code=sliceBetween("async function requireFreshOwnerReview(packet) {",
    "\n/** One exact reviewed form binding");
  const calls=[];
  const node={
    "review_verified":true,"review_state":"pending",
    "bound_profile_and_letter":true,"automatic_employer_submit_authorized":false,
    "browser_grant_issued":false,"external_actions_performed":false,
    "expires_at":"2026-11-20T19:00:00Z"
  };
  const scope={
    PacketError,
    currentPacket:packet,
    isSmartPloyTab,
    approvedSavedAnswersSha256:async()=>packet.saved_answers_sha256,
    approvedFieldsSha256:async()=>("e".repeat(64)),
    sha256Text:async()=>("f".repeat(64)),
    verifyReviewOnSmartPloy:function verifyReviewOnSmartPloy(){},
    chrome:{
      tabs:{query:async()=>ownerTabs},
      scripting:{executeScript:async(request)=>{
        calls.push(request.target.tabId);
        return [{frameId:0,result:request.target.tabId===7?node:
          {review_verified:false,reason:"not_authorized"}}];
      }}
    }
  };
  runInNewContext(code+"\nthis.verifyFresh=requireFreshOwnerReview;",scope);
  const result=await scope.verifyFresh(packet);
  assert.equal(result.review_verified,true);
  assert.equal(result.owner_tab_id,7);
  assert.equal(calls.join(","),"6,7");
});
test("automatic current-PDF transfer uses matching verified tab, not a tab-count rule",async()=>{
  const code=sliceBetween("async function autoAttachSavedDocuments() {",
    "\n/** One applicant-approved AutoApply preparation action");
  const calls=[];
  const scope={
    PacketError,UploadError:class UploadError extends Error{},
    receiptOnly:false,attemptReserved:false,oneJobClaimMayExist:false,
    currentPacket:packet,targetTabId:9,inspectedUrl:job,
    chrome:{storage:{session:{}},
      tabs:{query:async()=>ownerTabs},
      scripting:{executeScript:async(request)=>{
        calls.push({tabId:request.target.tabId,fn:request.func.name});
        if(request.func.name==="inspectForm")return [{frameId:0,result:{
          url:job,allElementsCount:2,elements:[]
        }}];
        if(request.func.name==="readOwnReviewedPdf")return [{frameId:0,result:{
          ready:true,kind:request.args[0].kind,
          sha256:request.args[0].sha256,size:request.args[0].size,
          filename:"Reviewed.pdf",base64:"SYNTHETIC_NO_DOCUMENT"
        }}];
        if(request.func.name==="attachReviewedPdf")return [{frameId:0,result:{
          status:"attached_locally"
        }}];
        throw Error("Unexpected browser action "+request.func.name);
      }}
    },
    activeTab:async()=>({id:9,url:job}),validatePacket:()=>{},
    currentPacketToJSON:()=>packet,
    requireVerifiedReview:async()=>{},
    requireFreshOwnerReview:async()=>({review_verified:true,owner_tab_id:7}),
    exactAssistedForm:()=>true,hasPriorLeverAttempt:async()=>false,
    chooseResumeField:()=>({index:0}),
    chooseCoverLetterField:()=>({index:1}),
    isLeverFinalProvider:()=>true,
    inspectForm:function inspectForm(){},
    readOwnReviewedPdf:function readOwnReviewedPdf(){},
    attachReviewedPdf:function attachReviewedPdf(){},
    window:{confirm:()=>true},normalizeError:error=>error.message,
    UploadError:class UploadError extends Error{}
  };
  runInNewContext(code+"\nthis.attach=autoAttachSavedDocuments;",scope);
  const result=await scope.attach();
  assert.equal(result.ready,true,result.reason);
  assert.equal(result.attached,2);
  assert.deepEqual(calls.filter(x=>x.fn==="readOwnReviewedPdf").map(x=>x.tabId),[7,7]);
  assert.deepEqual(calls.filter(x=>x.fn==="attachReviewedPdf").map(x=>x.tabId),[9,9]);
});
