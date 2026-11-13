import test from "node:test";
import {createHash} from "node:crypto";
import assert from "node:assert/strict";
import {validatePacket,PacketError} from "../logic.mjs";
import {planReviewedQuestions,suggestSavedAnswers} from "../questions.mjs";

const url="https://jobs.lever.co/test/12345678-0000-4000-8000-123456789abc/apply";
function packet(changes={}) {
  const time=Date.parse("2026-11-13T10:00:00Z");
  return {
    schema:"smartploy.browser_handoff.v2",
    issued_at:new Date(time).toISOString(),
    expires_at:new Date(time+900000).toISOString(),
    workspace_id:"kit-"+"a".repeat(30), revision:2,
    application_url:url,company:"Test",role_title:"Analyst",
    document_sha256:"b".repeat(64),cv_pdf_sha256:"c".repeat(64),
    cv_pdf_size:2048,letter_pdf_sha256:"d".repeat(64),
    letter_pdf_size:1024,
    fields:{
      full_name:"Test Person",first_name:"Test",last_name:"Person",
      email:"test@example.org",phone:"",location:"",linkedin:"",github:"",
      cover_letter:"Reviewed accurate cover letter text for this candidate."
    },
    saved_answers:[
      {question:"How did you hear about us?",answer:"Career page"}
    ],
    privacy:{
      approved_contact_only:true,approved_saved_answers_only:true,
      original_cv_included:false,employer_submit_allowed_without_new_approval:false
    },
    ...changes
  };
}
const now=Date.parse("2026-11-13T10:05:00Z");
function question(label, maxLength=500){
  return {index:0,type:"textarea",label,id:"why",name:"reason",
    required:true,visible:true,hasValue:false,disabled:false,
    readonly:false,maxLength};
}

test("exact signed-in packet carries reusable answers and both reviewed document fingerprints",()=>{
  const v=validatePacket(packet(),url,now);
  assert.deepEqual(v.saved_answers,[
    {question:"How did you hear about us?",answer:"Career page"}
  ]);
  assert.equal(v.letter_pdf_sha256,"d".repeat(64));
  assert.equal(v.letter_pdf_size,1024);
  assert.equal(v.cv_pdf_sha256,"c".repeat(64));
});

test("known unchanged question is prefilled but an employer rewrite asks the applicant",()=>{
  const plan=planReviewedQuestions([question("How did you hear about us?")]);
  const exact=suggestSavedAnswers(plan,packet().saved_answers);
  assert.deepEqual(exact.values,["Career page"]);
  assert.equal(exact.reused,1);
  assert.deepEqual(exact.needsReview,[]);
  const changed=planReviewedQuestions([question("How did you hear about this specific position?")]);
  const unknown=suggestSavedAnswers(changed,packet().saved_answers);
  assert.deepEqual(unknown.values,[""]);
  assert.equal(unknown.reused,0);
  assert.deepEqual(unknown.needsReview,["How did you hear about this specific position?"]);
});

test("duplicates and too-long answers must be re-reviewed, not automatically filled",()=>{
  const p=planReviewedQuestions([question("Where did you see the role?",4)]);
  const ans=[
    {question:"Where did you see the role?",answer:"Web"},
    {question:"Where did you see the role?",answer:"Referral"}
  ];
  assert.deepEqual(suggestSavedAnswers(p,ans).values,[""]);
  assert.deepEqual(suggestSavedAnswers(p,[ans[1]]).values,[""]);
});

test("tampered, illegal and over-broad profile packets cannot be trusted",()=>{
  for(const bad of [
    [{question:"Gender",answer:"Male"}],
    [{question:"How did you hear about us?",answer:"I am female"}],
    [{question:"How did you hear about us?",answer:"Job board"},
      {question:"How did you hear about us?",answer:"Referral"}],
    [{question:"How did you hear about us?",answer:"Job board",submit:true}],
    Array.from({length:17},(_,i)=>({question:"Why "+i+"?",answer:"Because"}))
  ]){
    assert.throws(()=>validatePacket(packet({saved_answers:bad}),url,now),PacketError);
  }
  assert.throws(()=>validatePacket(packet({privacy:{
    ...packet().privacy,approved_saved_answers_only:false
  }}),url,now),PacketError);
  assert.throws(()=>validatePacket(packet({letter_pdf_sha256:"x"}),url,now),PacketError);
  assert.throws(()=>validatePacket(packet({letter_pdf_size:2097153}),url,now),PacketError);
});
