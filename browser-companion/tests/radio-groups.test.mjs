import test from "node:test";
import assert from "node:assert/strict";
import {
  planReviewedQuestions, validateReviewedAnswers, QuestionError
} from "../questions.mjs";

// This radio-group shape comes from SmartPloy's existing inspectForm() native
// fieldset/legend extraction, not generated applicant answers or hidden DOM.
const options = [
  {index:3, id:"friend", value:"friend", label:"Friend referral"},
  {index:4, id:"board", value:"job-board", label:"Job board"},
];
function nativeGroup(changes = {}) {
  const group = {label:"Where did you hear about this job?",
    name:"job_source", firstIndex:3, required:true, checked:false,
    options, ...(changes.group || {})};
  return [
    ...[0,1,2].map(index => ({index, type:"hidden", label:"Other",
      id:"other"+index, name:"other"+index, required:false, hasValue:true,
      readonly:false, disabled:false, visible:false})),
    {index:3, type:"radio", label:"Friend referral", id:"friend",
      name:"job_source", required:false, hasValue:false,
      readonly:false, disabled:false, visible:true, radioGroup:group},
    {index:4, type:"radio", label:"Job board", id:"board",
      name:"job_source", required:true, hasValue:false,
      readonly:false, disabled:false, visible:true, radioGroup:group}
  ];
}
test("V4 required fieldset radio is one exact applicant-reviewed question", () => {
  const plan = planReviewedQuestions(nativeGroup());
  assert.equal(plan.questions.length,1);
  const q=plan.questions[0];
  assert.equal(q.type,"radio_group");
  assert.equal(q.label,"Where did you hear about this job?");
  assert.equal(q.index,3);
  assert.deepEqual(q.options,options);
  assert.deepEqual(validateReviewedAnswers(plan,["job-board"]).map(a=>a.value),["job-board"]);
  for(const unsupported of ["", "job", "Job board", "yes", "job-board ", "JOB-BOARD"]) {
    assert.throws(()=>validateReviewedAnswers(plan,[unsupported]),QuestionError);
  }
});
test("V4 protected group labels and protected option IDs require personal handling", () => {
  for(const patch of [
    {label:"Are you authorized to work in Finland?"},
    {label:"I agree to privacy and consent terms"},
    {options:[{...options[0],id:"visaStatus"},options[1]]},
    {options:[options[0],{...options[1],label:"Salary expectation"}]},
    {options:[options[0],{...options[1],value:"friend"}]},
    {options:[options[0],{...options[1],label:"Friend referral"}]},
    {checked:true},
    {required:false},
    {options:[options[0]]}
  ]) {
    const rows=nativeGroup({group:patch});
    const plan=planReviewedQuestions(rows);
    assert.equal(plan.questions.length,0,JSON.stringify(patch));
  }
});
test("V4 radio choices with missing fieldset observation never receive autofill", () => {
  const rows=nativeGroup().map(row=>({...row,radioGroup:null}));
  const plan=planReviewedQuestions(rows);
  assert.equal(plan.questions.length,0);
  assert.ok(plan.humanOnly.length>=1);
});
