import test from "node:test";
import assert from "node:assert/strict";
import {saveOneObservedReceiptOnSmartPloy} from "../page-receipt-import.mjs";

const workspace="kit-"+"a".repeat(30);
const receipt={
  schema:"smartploy.browser_receipt.v1",workspace_id:workspace,
  reference:"SYN-REF-2026",confirmed_visible:true
};
async function run({
  origin="https://smartploy.komplyint.fi",
  oidc=true,accepted=true,correctOwner=true,record=receipt,
  confirm=true,iframe=false,
}={}) {
  const old={
    location:globalThis.location,window:globalThis.window,fetch:globalThis.fetch
  },calls=[],frame={};
  globalThis.location={origin,protocol:origin.startsWith("https:")?"https:":"http:"};
  globalThis.window={top:frame,self:iframe?{}:frame};
  globalThis.fetch=async (url,options)=>{
    calls.push({url,options});
    if(url==="/api/v1/session")return {
      ok:true,async json(){return {
        authenticated:oidc,auth_source:oidc?"oidc":"none",
        user_id:"usr-"+"b".repeat(32)
      };}
    };
    if(url.endsWith("/browser-receipt")){
      return {ok:accepted,status:accepted?200:409,
        async json(){return {
          receipt:{workspace_id:correctOwner?workspace:"kit-"+"c".repeat(30)},
          external_confirmation_verified:false
        };}
      };
    }
    throw Error("Unexpected destination: "+url);
  };
  try {
    const result=await saveOneObservedReceiptOnSmartPloy({
      workspace_id:workspace,receipt:record,confirm_user_observed:confirm
    });
    return {result,calls};
  } finally {
    for(const [key,value]of Object.entries(old)){
      if(value===undefined)delete globalThis[key];else globalThis[key]=value;
    }
  }
}
test("one real observed reference is POSTed ONLY to the signed-in account",async()=>{
  const {result,calls}=await run();
  assert.equal(result.saved,true);
  assert.equal(result.reference,"SYN-REF-2026");
  assert.equal(result.external_confirmation_verified,false);
  assert.deepEqual(calls.map(x=>x.url),[
    "/api/v1/session",
    "/api/v1/application-workspaces/"+workspace+"/browser-receipt"
  ]);
  assert.equal(calls[1].options.credentials,"same-origin");
  assert.equal(calls[1].options.redirect,"error");
  const data=JSON.parse(calls[1].options.body);
  assert.equal(data.confirm_user_observed,true);
  assert.equal(data.receipt.reference,"SYN-REF-2026");
  assert.ok(!JSON.stringify(result).includes("usr-"));
});
test("forged, unconfirmed, wrong-origin or nested browser receipt performs no network",async()=>{
  for(const options of [
    {origin:"https://smartploy.komplyint.fi.evil.invalid"},
    {origin:"http://smartploy.komplyint.fi"},
    {iframe:true},
    {confirm:false},
    {record:{...receipt,workspace_id:"kit-"+"b".repeat(30)}},
    {record:{...receipt,confirmed_visible:false}},
    {record:{...receipt,reference:"?"}},
  ]){
    const {result,calls}=await run(options);
    assert.equal(result.saved,false,JSON.stringify(options));
    assert.equal(calls.length,0,JSON.stringify(options));
  }
});
test("signed-out, server denial or cross-user response cannot masquerade as completion",async()=>{
  for(const options of [{oidc:false},{accepted:false},{correctOwner:false}]){
    const {result}=await run(options);
    assert.equal(result.saved,false,JSON.stringify(options));
  }
});
