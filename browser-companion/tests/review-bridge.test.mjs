import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { PacketError } from "../logic.mjs";
import {
  approvedFieldsSha256, isSmartPloyTab, recordVerifiedReview,
  requireVerifiedReview, reviewSessionKey, sha256Text,
  validateReviewPacket, REVIEW_SESSION_SECONDS,
  recordOneUseFinalAttempt, requireOneUseFinalAttempt,
  consumeLocalFinalAttempt, finalAttemptSessionKey
} from "../review-bridge.mjs";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

const now = Date.parse("2026-10-18T15:20:00Z");
const packet = (overrides = {}) => ({
  schema: "smartploy.browser_handoff.v2",
  workspace_id: "kit-" + "a".repeat(30),
  revision: 2,
  issued_at: new Date(now-10_000).toISOString(),
  expires_at: new Date(now+10*60_000).toISOString(),
  document_sha256: "b".repeat(64),
  cv_pdf_sha256: "c".repeat(64),
  cv_pdf_size: 87522,
  application_url: "https://jobs.lever.co/example/88888888-8888-4000-8000-888888888888/apply",
  company: "Synthetic Employer",
  role_title: "Synthetic Analyst",
  fields: {
    full_name: "Synthetic Applicant", first_name: "Synthetic",
    last_name: "Applicant", email: "test@example.invalid",
    phone: "", location: "", linkedin: "", github: "",
    cover_letter: "I have reviewed every statement in this synthetic cover letter."
  },
  privacy: {
    approved_contact_only: true, original_cv_included: false,
    browser_form_fill_allowed_after_user_click: true,
    employer_submit_allowed_without_new_approval: false
  },
  ...overrides
});
const verdict=(expires=now+8*60_000)=>({
  review_verified:true,review_state:"pending",
  expires_at:new Date(expires).toISOString(),
  automatic_employer_submit_authorized:false,
  external_actions_performed:false,browser_grant_issued:false
});
function storage() {
  const state=new Map();
  return {
    state,
    async set(records) {
      for(const [key,val] of Object.entries(records)) state.set(key,val);
    },
    async get(key) { return {[key]:state.get(key)}; }
  };
}

test("only exact SmartPloy HTTPS origin can pair; employer or lookalike origins cannot",()=>{
  assert.equal(isSmartPloyTab("https://smartploy.komplyint.fi/"),true);
  assert.equal(isSmartPloyTab("https://smartploy.obumai.com/"),true);
  for(const url of [
    "http://smartploy.komplyint.fi", "http://smartploy.obumai.com",
    "https://smartploy.komplyint.fi.evil.invalid",
    "https://smartploy.obumai.com.evil.invalid",
    "https://komplyint.fi", "https://evil.invalid",
    "https://user:secret@smartploy.komplyint.fi/app",
    "https://user:secret@smartploy.obumai.com/app",
    "https://smartploy.komplyint.fi:9090/",
    "https://smartploy.obumai.com:9090/", "not a URL",
  ])assert.equal(isSmartPloyTab(url),false,url);
});

test("reuse existing approved packet validation; reject no CV or spoofed employer",()=>{
  const reviewed=validateReviewPacket(JSON.stringify(packet()),now);
  assert.equal(reviewed.workspace_id,packet().workspace_id);
  assert.equal(reviewed.cv_pdf_sha256,packet().cv_pdf_sha256);
  for(const altered of [
    packet({revision:0}),packet({schema:"bad"}),
    packet({application_url:"https://evil.invalid/role"}),
    packet({expires_at:new Date(now-1).toISOString()}),
    packet({cv_pdf_sha256:"bad"}),
    packet({privacy:{...packet().privacy,employer_submit_allowed_without_new_approval:true}})
  ])assert.throws(()=>validateReviewPacket(altered,now),PacketError);
});

test("signed-in review stores a NON-BEARER SHA-key and expiry, not private data",async()=>{
  const first=storage(), reviewed=validateReviewPacket(packet(),now);
  await assert.rejects(requireVerifiedReview(first,reviewed,now),PacketError);
  const saved=await recordVerifiedReview(first,reviewed,verdict(),now);
  const key=await reviewSessionKey(reviewed);
  assert.match(key,/^smartploy\.review\.[a-f0-9]{64}$/);
  assert.deepEqual([...first.state.keys()],[key]);
  assert.deepEqual(first.state.get(key),{
    marker:"signed-in-review-v1",
    expires_at:now+REVIEW_SESSION_SECONDS*1000
  });
  const persisted=JSON.stringify(Object.fromEntries(first.state));
  for(const forbidden of ["Synthetic Applicant","test@example.invalid","jobs.lever.co",
    "bearer","session_cookie","cover_letter","cv_pdf_sha256","workspace_id"])
    assert.equal(persisted.includes(forbidden),false,forbidden);
  assert.equal(await requireVerifiedReview(first,reviewed,now+150000),true);
  await assert.rejects(
    requireVerifiedReview(first,reviewed,now+REVIEW_SESSION_SECONDS*1000),
    PacketError
  );
  assert.ok(Date.parse(saved.expires_at)===now+REVIEW_SESSION_SECONDS*1000);
});

test("a distinct browser session cannot borrow another browser's attestation",async()=>{
  const pkt=validateReviewPacket(packet(),now), a=storage(),b=storage();
  await recordVerifiedReview(a,pkt,verdict(),now);
  assert.equal(await requireVerifiedReview(a,pkt,now),true);
  await assert.rejects(requireVerifiedReview(b,pkt,now),PacketError);
});

test("different job, CV, revision, or same email with a new workspace cannot reuse attestation",async()=>{
  const base=validateReviewPacket(packet(),now), store=storage();
  await recordVerifiedReview(store,base,verdict(),now);
  for(const x of [
    packet({workspace_id:"kit-"+"f".repeat(30)}),
    packet({revision:3}),packet({document_sha256:"f".repeat(64)}),
    packet({cv_pdf_sha256:"e".repeat(64)}),
    packet({fields:{...packet().fields,email:"different@example.invalid"}}),
    packet({fields:{...packet().fields,cover_letter:"Altered synthetic cover letter"}}),
    packet({application_url:"https://jobs.lever.co/other/88888888-8888-4000-8000-888888888888/apply"})
  ]){
    const other=validateReviewPacket(x,now);
    assert.notEqual(await reviewSessionKey(other),await reviewSessionKey(base));
    await assert.rejects(requireVerifiedReview(store,other,now),PacketError);
  }
});

test("invalid, stale, or submit-authorizing server response never pairs",async()=>{
  const pkt=validateReviewPacket(packet(),now);
  for(const v of [
    {...verdict(),review_verified:false},
    {...verdict(),browser_grant_issued:true},
    {...verdict(),automatic_employer_submit_authorized:true},
    {...verdict(),external_actions_performed:true},
    {...verdict(),expires_at:new Date(now-1).toISOString()},
    {...verdict(),expires_at:new Date(now+20*60_000).toISOString()},
    {...verdict(),review_state:"cancelled"},
    undefined
  ]){
    const store=storage();
    await assert.rejects(recordVerifiedReview(store,pkt,v,now),PacketError);
    assert.equal(store.state.size,0);
  }
  await assert.rejects(recordVerifiedReview(null,pkt,verdict(),now),PacketError);
});


test("reviewed field fingerprint matches independent Python UTF-8 length-prefix reference",async()=>{
  const hash=await approvedFieldsSha256(packet().fields);
  assert.equal(hash,"135df071b9de4a37fd07681b9a61b09c8e2bfe6bbba4df84108c69168176403c");
  assert.equal((await sha256Text(packet().application_url)).length,64);
  assert.notEqual(hash,await approvedFieldsSha256({
    ...packet().fields,email:"alternate@example.invalid"
  }));
  await assert.rejects(approvedFieldsSha256({
    ...packet().fields,unauthorized_field:"private CV"
  }),PacketError);
});


test("verified review + nonbearer server claim authorizes only one exact local attempt",async()=>{
  const pkt=validateReviewPacket(packet(),now),store=storage();
  await recordVerifiedReview(store,pkt,verdict(),now);
  const claim={
    claim_reserved:true,claim_id:"employer-claim-"+"1".repeat(32),
    expires_at:new Date(now+85_000).toISOString(),
    external_actions_performed:false,provider_acknowledged:false,
    automatic_retry_authorized:false,
  };
  const info=await recordOneUseFinalAttempt(store,pkt,claim,now);
  assert.equal(Date.parse(info.expires_at),now+85_000);
  assert.equal(await requireOneUseFinalAttempt(store,pkt,now),true);
  const key=await finalAttemptSessionKey(pkt);
  assert.match(key,/^smartploy\.final\.[a-f0-9]{64}$/);
  const written=JSON.stringify(Object.fromEntries(store.state));
  for(const forbidden of ["Synthetic Applicant","test@example.invalid","jobs.lever.co",
    "cover_letter","session_cookie","bearer","full_name"]){
    assert.equal(written.includes(forbidden),false,forbidden);
  }
  await assert.rejects(recordOneUseFinalAttempt(store,pkt,claim,now),PacketError);
  await consumeLocalFinalAttempt(store,pkt,now);
  await assert.rejects(requireOneUseFinalAttempt(store,pkt,now),PacketError);
  await assert.rejects(consumeLocalFinalAttempt(store,pkt,now),PacketError);
  await assert.rejects(requireOneUseFinalAttempt(store,pkt,now+85_000),PacketError);
  const another=validateReviewPacket(packet({revision:3}),now);
  await assert.rejects(requireOneUseFinalAttempt(store,another,now),PacketError);
});

test("missing review and forged final claim never unlock browser submit",async()=>{
  const pkt=validateReviewPacket(packet(),now);
  const claim={
    claim_reserved:true,claim_id:"employer-claim-"+"1".repeat(32),
    expires_at:new Date(now+20_000).toISOString(),
    external_actions_performed:false,provider_acknowledged:false,
    automatic_retry_authorized:false,
  };
  const absent=storage();
  await assert.rejects(recordOneUseFinalAttempt(absent,pkt,claim,now),PacketError);
  const ready=storage();
  await recordVerifiedReview(ready,pkt,verdict(),now);
  for(const altered of [
    {...claim,claim_id:"bad"}, {...claim,claim_reserved:false},
    {...claim,provider_acknowledged:true},
    {...claim,external_actions_performed:true},
    {...claim,automatic_retry_authorized:true},
    {...claim,expires_at:new Date(now-1000).toISOString()},
    {...claim,expires_at:new Date(now+400_000).toISOString()},
  ]){
    await assert.rejects(recordOneUseFinalAttempt(ready,pkt,altered,now),PacketError);
  }
  const key=await finalAttemptSessionKey(pkt);
  assert.equal((await ready.get(key))[key],undefined);
});
