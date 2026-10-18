import test from "node:test";
import assert from "node:assert/strict";
import { AttemptError, oneAttemptKey, withSubmissionLock } from "../attempt-lock.mjs";

const base = {
  workspace_id: "kit-" + "a".repeat(30),
  application_url: "https://jobs.lever.co/acme/99999999-1234-0000-0000-111111111111/apply",
  revision: 1, document_sha256: "a".repeat(64)
};

test("attempt claim survives CV edits, revision updates and tracking links",async()=>{
  const old=await oneAttemptKey(base);
  for(const newPacket of [
    {...base,revision:42,document_sha256:"b".repeat(64)},
    {...base,application_url:base.application_url.replace("/apply","")},
    {...base,application_url:base.application_url+"/?ref=campaign#section"}
  ]) assert.equal(await oneAttemptKey(newPacket),old);
  assert.match(old,/^smartploy\.submit\.[a-f0-9]{64}$/);
});

test("separate applicants or employers do not share one job attempt claim",async()=>{
  const key=await oneAttemptKey(base);
  const variants=[
    {...base,workspace_id:"kit-"+ "b".repeat(30)},
    {...base,application_url:base.application_url.replace("/acme/","/another/")},
    {...base,application_url:base.application_url.replace("99999999","88888888")}
  ];
  for(const row of variants) assert.notEqual(await oneAttemptKey(row),key);
});

test("malformed or unrelated employer URLs and invalid owner IDs fail closed",async()=>{
  for(const row of [
    {...base,workspace_id:"other-user"},
    {...base,application_url:"http://jobs.lever.co/acme/123/apply"},
    {...base,application_url:"https://evil.example.com/acme/123/apply"},
    {...base,application_url:"https://jobs.lever.co/acme/123/other"},
    {...base,application_url:"https://user:secret@jobs.lever.co/acme/123/apply"},
    {...base,application_url:"not a URL"}
  ]) await assert.rejects(oneAttemptKey(row),AttemptError);
});

function mockWebLocks() {
  const byKey = new Map();
  return {
    async request(key,opts,task) {
      assert.equal(opts.mode,"exclusive");
      const preceding=byKey.get(key) || Promise.resolve();
      let finish;
      const now=new Promise(resolve=>{finish=resolve;});
      byKey.set(key,preceding.then(()=>now));
      await preceding;
      try { return await task({name:key}); }
      finally {finish();}
    }
  };
}

test("two approval popups cannot both reserve and click the same job",async()=>{
  const key=await oneAttemptKey(base);
  const locks=mockWebLocks();
  let persisted=false, clicks=0, reads=0;
  const submit=()=>withSubmissionLock(key,locks,async()=>{
    reads++;
    if(persisted) throw new AttemptError("Previously attempted, no retry.");
    await Promise.resolve();
    persisted=true; // opaque attempt storage is written before browser click
    clicks++;
    return "attempted_unverified";
  });
  const outcomes=await Promise.allSettled([submit(),submit()]);
  assert.deepEqual(outcomes.map(x=>x.status).sort(),["fulfilled","rejected"]);
  assert.equal(clicks,1);
  assert.equal(reads,2);
});

test("missing browser-wide lock or invalid claim never silently proceeds",async()=>{
  const key=await oneAttemptKey(base);
  let calls=0;
  const work=()=>{calls++;return Promise.resolve();};
  await assert.rejects(withSubmissionLock(key,null,work),AttemptError);
  await assert.rejects(withSubmissionLock("bad-key",mockWebLocks(),work),AttemptError);
  await assert.rejects(withSubmissionLock(key,{request:async(_k,_o,cb)=>cb(null)},work),AttemptError);
  assert.equal(calls,0);
});
