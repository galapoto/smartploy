import test from "node:test";
import assert from "node:assert/strict";
import { reserveFinalClickOnSmartPloy } from "../page-final-claim.mjs";

const request = Object.freeze({
  workspace_id:"kit-"+"a".repeat(30), expected_revision:2,
  expected_document_sha256:"b".repeat(64),
  expected_cv_pdf_sha256:"c".repeat(64),
  expected_fields_sha256:"d".repeat(64),
  expected_application_url_sha256:"e".repeat(64),
  expected_cv_pdf_size:334,
  confirm_one_job_final_click:true,
  acknowledge_external_employer_transfer:true,
  acknowledge_no_automatic_retry:true,
});
const approved = Object.freeze({
  claim_reserved:true,claim_id:"employer-claim-"+"f".repeat(32),
  expires_at:"2026-10-24T20:30:00Z",
  external_actions_performed:false,provider_acknowledged:false,
  automatic_retry_authorized:false,one_job_browser_click_permitted:true,
});

async function simulate(origin,{authSource="oidc",sessionValid=true,nested=false,
  deny=false,redirect=false,invalidReturn=false,body=request}={}) {
  const original = Object.fromEntries(
    ["location","window","fetch"].map(k=>[k,globalThis[k]])
  );
  const frame={};
  globalThis.window={top:frame,self:nested?{}:frame};
  globalThis.location={origin,protocol:origin.startsWith("https:")?"https:":"http:"};
  const events=[];
  globalThis.fetch=async (url,options)=>{
    events.push({url,options});
    if (redirect) throw TypeError("Refused cross-origin redirect");
    if (url==="/api/v1/session")return {
      ok:sessionValid,
      async json(){return {authenticated:true,auth_source:authSource,user_id:"usr-"+"1".repeat(32)};},
    };
    if (url.endsWith("/browser-final-attempt"))return {
      ok:!deny,status:deny?409:200,
      async json(){return invalidReturn?{claim_reserved:false}:approved;},
    };
    throw Error("Unexpected request "+url);
  };
  try{
    return {outcome:await reserveFinalClickOnSmartPloy(body),events};
  }finally{
    for(const [k,v] of Object.entries(original)){
      if(v===undefined)delete globalThis[k];else globalThis[k]=v;
    }
  }
}

test("exact first-party Komplyint page reserves one job using OIDC cookies only",async()=>{
  const {outcome,events}=await simulate("https://smartploy.komplyint.fi");
  assert.equal(outcome.claim_reserved,true);
  assert.equal(outcome.provider_acknowledged,false);
  assert.equal(outcome.external_actions_performed,false);
  assert.equal(outcome.automatic_retry_authorized,false);
  assert.equal(events.length,2);
  assert.equal(events[0].url,"/api/v1/session");
  assert.equal(events[1].url,"/api/v1/application-workspaces/"+request.workspace_id+
    "/browser-final-attempt");
  const payload=JSON.parse(events[1].options.body);
  const {workspace_id,...expected}=request;
  assert.deepEqual(payload,expected);
  for(const e of events){
    assert.equal(e.options.credentials,"same-origin");
    assert.equal(e.options.redirect,"error");
    assert.equal(e.options.cache,"no-store");
    assert.equal(e.options.headers.Authorization,undefined);
  }
  assert.equal(JSON.stringify(outcome).includes("usr-"),false);
});

test("wrong origin, frame or unauthenticated pages cannot reserve employer claim",async()=>{
  for(const origin of ["http://smartploy.komplyint.fi",
    "https://smartploy.komplyint.fi.evil.invalid",
    "https://example.invalid"]) {
    const {outcome,events}=await simulate(origin);
    assert.equal(outcome.reason,"wrong_origin");
    assert.equal(events.length,0);
  }
  const frame=await simulate("https://smartploy.komplyint.fi",{nested:true});
  assert.equal(frame.outcome.reason,"wrong_origin");
  assert.equal(frame.events.length,0);
  for(const c of [{authSource:"cloudflare"},{sessionValid:false}]) {
    const r=await simulate("https://smartploy.komplyint.fi",c);
    assert.equal(r.outcome.reason,"sign_in_required");
    assert.equal(r.events.length,1);
  }
});

test("missing final user consent is rejected without a network call",async()=>{
  for(const missing of ["confirm_one_job_final_click",
    "acknowledge_external_employer_transfer",
    "acknowledge_no_automatic_retry"]) {
    const r=await simulate("https://smartploy.komplyint.fi",{
      body:{...request,[missing]:false},
    });
    assert.equal(r.outcome.reason,"invalid_binding");
    assert.equal(r.events.length,0);
  }
});

test("outdated review, untrusted reply or ambiguous network never returns a claim",async()=>{
  for(const config of [{deny:true},{redirect:true},{invalidReturn:true}]) {
    const r=await simulate("https://smartploy.komplyint.fi",config);
    assert.equal(r.outcome.claim_reserved,false);
    assert.equal(r.events.length,2);
  }
});
