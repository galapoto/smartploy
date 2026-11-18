import test from "node:test";
import assert from "node:assert/strict";
import {readOneJobFinalActionReadinessOnSmartPloy} from "../page-final-readiness.mjs";

const WORKSPACE="kit-"+"a".repeat(30);
async function probe({
  origin="https://smartploy.komplyint.fi",
  signedIn=true,authSource="oidc",permission=true,enabled=true,
  nested=false,invalidWorkspace=false,denyServer=false,networkError=false,
  previousAttempt=false
}={}){
  const prior={
    location:globalThis.location,window:globalThis.window,
    fetch:globalThis.fetch
  };
  const frame={},calls=[];
  globalThis.location={
    origin,protocol:origin.startsWith("https:")?"https:":"http:"
  };
  globalThis.window={top:frame,self:nested?{}:frame};
  globalThis.fetch=async (url,options)=>{
    calls.push({url,options});
    if(networkError)throw Error("network unavailable");
    if(url==="/api/v1/session")return {
      ok:signedIn,async json(){return {
        authenticated:signedIn,auth_source:authSource
      };}
    };
    if(url.endsWith("/final-action-readiness"))return {
      ok:!denyServer,async json(){return {
        operator_permission_reviewed:permission,
        trusted_one_use_browser_redemption_available:enabled,
        previous_employer_attempt_reserved:previousAttempt
      };}
    };
    throw Error("Unexpected endpoint");
  };
  try{
    const result=await readOneJobFinalActionReadinessOnSmartPloy(
      invalidWorkspace?"../other":WORKSPACE
    );
    return {result,calls};
  }finally{
    for(const [key,value]of Object.entries(prior)){
      if(value===undefined)delete globalThis[key];
      else globalThis[key]=value;
    }
  }
}
test("only a signed-in first-party GET with actual employer permission and enabled flag is ready",async()=>{
  const {result,calls}=await probe();
  assert.equal(result.ready,true);
  assert.deepEqual(calls.map(x=>x.url),[
    "/api/v1/session",
    "/api/v1/application-workspaces/"+WORKSPACE+"/final-action-readiness"
  ]);
  for(const {options} of calls){
    assert.equal(options.credentials,"same-origin");
    assert.equal(options.cache,"no-store");
    assert.equal(options.redirect,"error");
    assert.equal(options.method,undefined);
    assert.equal(options.headers.Accept,"application/json");
  }
});
test("zero approved jobs, disabled final-click flag, or unavailable server fails closed",async()=>{
  for(const options of [
    {permission:false},{enabled:false},{denyServer:true},
    {networkError:true}
  ]){
    const {result}=await probe(options);
    assert.equal(result.ready,false,JSON.stringify(options));
  }
});
test("untrusted origin, nested frame and invalid job path never make a network request",async()=>{
  for(const options of [
    {origin:"https://smartploy.komplyint.fi.evil.invalid"},
    {origin:"https://other.invalid"},
    {origin:"http://smartploy.komplyint.fi"},
    {origin:"https://smartploy.komplyint.fi:444"},
    {nested:true},{invalidWorkspace:true}
  ]){
    const {result,calls}=await probe(options);
    assert.equal(result.ready,false,JSON.stringify(options));
    assert.equal(calls.length,0,JSON.stringify(options));
  }
});
test("only OIDC sessions can request owner-specific authorization details",async()=>{
  for(const options of [{signedIn:false},{authSource:"cloudflare"}]){
    const {result,calls}=await probe(options);
    assert.equal(result.ready,false);
    assert.deepEqual(calls.map(c=>c.url),["/api/v1/session"]);
  }
});

test("an owner-scoped previously consumed claim survives popup restarts and overrides enablement",async()=>{
  const {result,calls}=await probe({previousAttempt:true});
  assert.equal(result.ready,false);
  assert.equal(result.previous_employer_attempt_reserved,true);
  assert.equal(result.reason,"previous_employer_attempt_reserved");
  assert.deepEqual(calls.map(c=>c.url),[
    "/api/v1/session",
    "/api/v1/application-workspaces/"+WORKSPACE+"/final-action-readiness"
  ]);
});
