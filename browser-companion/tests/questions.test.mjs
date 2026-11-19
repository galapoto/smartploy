import test from "node:test";
import assert from "node:assert/strict";
import {
  QuestionError, MAX_QUESTION_ANSWER, planReviewedQuestions,
  validateReviewedAnswers, isSensitiveQuestion, suggestSavedAnswers
} from "../questions.mjs";

function row(overrides = {}) {
  return {
    index: 1, type: "textarea", label: "Why are you interested in this role?",
    id: "motivation", name: "questions[role_motivation]",
    placeholder: "", autocomplete: "",
    required: true, hasValue: false, readonly: false,
    disabled: false, visible: true, maxLength: -1,
    ...overrides
  };
}

test("only unidentified, visible, required text questions enter reviewed-answer plan", () => {
  const input = [
    row({index:0, label:"Full name",type:"text",name:"name"}),
    row(),
    row({index:2,label:"Describe a Python project you worked on",type:"text",id:"python",name:"python_example",maxLength:220}),
    row({index:3,label:"Email",type:"email"}),
    row({index:4,label:"Cover letter",type:"textarea"}),
    row({index:5,label:"What would you improve?",hasValue:true}),
    row({index:6,label:"Explain a team achievement",visible:false}),
    row({index:7,label:"Willing to relocate?",type:"checkbox"})
  ];
  const plan = planReviewedQuestions(input);
  assert.deepEqual(plan.questions.map(x=>x.index), [1,2]);
  assert.equal(plan.questions[1].max_answer_length, 220);
  assert.ok(plan.humanOnly.includes("Willing to relocate?"));
});

test("legal, protected, privacy, salary, immigration, availability questions remain manual", () => {
  const text = [
    "Do you need visa sponsorship?",
    "What is your expected salary?",
    "Are you a citizen of Finland?",
    "Are you legally eligible to work in Finland?",
    "Are you authorized to work in this country?",
    "I consent to data retention",
    "Please certify that you can legally work here",
    "Gender identity",
    "Disability status",
    "Criminal background check",
    "Työlupa ja oleskelulupa",
    "Sukupuoli ja kansalaisuus",
    "Lön och arbetstillstånd",
    "Samtycke till GDPR policy"
  ];
  const plan = planReviewedQuestions(text.map((label,index) =>
    row({index, label, id:"sensitive"+index, name:"field"+index})));
  assert.equal(plan.questions.length, 0);
  assert.equal(plan.humanOnly.length, text.length);
  for (const label of text) assert.equal(isSensitiveQuestion(row({label})), true, label);
});

test("candidate reused from exact plan is accepted only with explicit bounded human answer", () => {
  const plan = planReviewedQuestions([row()]);
  const actions = validateReviewedAnswers(plan, ["I reviewed this: an accurate Python example."]);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].index, 1);
  assert.equal(actions[0].type, "textarea");
  assert.equal(actions[0].value, "I reviewed this: an accurate Python example.");
  for (const value of ["", "   ", "x".repeat(MAX_QUESTION_ANSWER+1), "invalid\u0000value"]) {
    assert.throws(() => validateReviewedAnswers(plan, [value]), QuestionError);
  }
  assert.throws(() => validateReviewedAnswers(plan, []), QuestionError);
});

test("duplicate labels, existing values, unsupported controls and form overflow fail closed", () => {
  let plan = planReviewedQuestions([
    row({index:0,label:"Why us?",id:"why1"}),
    row({index:1,label:"Why us?",id:"why2"}),
    row({index:2,label:"Reason",type:"select"}),
    row({index:3,label:"Document",type:"file"}),
    row({index:4,label:"Your motivation",readonly:true}),
    row({index:5,label:"Reasoning",maxLength:1})
  ]);
  assert.equal(plan.questions.length, 0);
  assert.equal(plan.humanOnly.length, 5);
  assert.throws(() => planReviewedQuestions(Array.from({length:251},(_,i)=>row({index:i}))), QuestionError);
  assert.throws(() => planReviewedQuestions(Array.from({length:13},(_,i)=>row({
    index:i,label:"Question "+i,id:"q"+i,name:"q"+i
  }))), QuestionError);
});

test("reviewed answers may only contain ordinary printable text in matching field", () => {
  const plan=planReviewedQuestions([row()]);
  assert.deepEqual(validateReviewedAnswers(plan, ["  My approved example  "]).map(x=>x.value), ["My approved example"]);
  assert.throws(() => validateReviewedAnswers({questions:[]}, ["value"]), QuestionError);
  assert.throws(() => validateReviewedAnswers(plan, [12]), QuestionError);
  plan.questions[0].label="Expected salary?";
  assert.throws(() => validateReviewedAnswers(plan, ["75000"]), QuestionError);
});


test("camelCase or concatenated sensitive form identifiers never become reviewed answers", () => {
  const ordinary = "Why are you interested in this role?";
  const identifiers = [
    {name:"visaStatus"},
    {id:"salaryExpectation"},
    {name:"citizenshipStatus"},
    {name:"genderIdentity"},
    {name:"GDPRConsent"},
    {placeholder:"workAuthorization"},
    {id:"visastatus"},
    {name:"sponsorshipRequired"},
    {name:"criminalBackgroundCheck"},
    {name:"dateOfBirth"},
    {id:"privacyAgreement"}
  ];
  for (const fields of identifiers) {
    const candidate=row({label:ordinary,...fields});
    assert.equal(isSensitiveQuestion(candidate),true,JSON.stringify(fields));
    const plan=planReviewedQuestions([candidate]);
    assert.equal(plan.questions.length,0,JSON.stringify(fields));
    assert.deepEqual(plan.humanOnly,[ordinary],JSON.stringify(fields));
  }
});

test("known ordinary question metadata remains eligible after identifier hardening", () => {
  const ordinary = row({id:"roleMotivation",name:"questions[role_motivation]"});
  assert.equal(isSensitiveQuestion(ordinary),false);
  assert.equal(planReviewedQuestions([ordinary]).questions.length,1);
});

test("V4 ordinary native select has applicant-visible exact options only", () => {
  const rowSelect = row({
    type:"select", label:"Where did you find this job?",
    id:"job_source", name:"job_source", maxLength:-1,
    options:[
      {value:"",label:"Choose",disabled:true},
      {value:"job-board",label:"Job board",disabled:false},
      {value:"referral",label:"Referral",disabled:false}
    ]
  });
  const plan = planReviewedQuestions([rowSelect]);
  assert.equal(plan.questions.length,1);
  assert.equal(plan.questions[0].type,"select");
  assert.deepEqual(plan.questions[0].options.map(o=>o.value),["job-board","referral"]);
  assert.deepEqual(validateReviewedAnswers(plan,["referral"]).map(x=>x.value),["referral"]);
  for(const bad of ["ref","Referral","", "job-board ", "JOB-BOARD"]) {
    assert.throws(()=>validateReviewedAnswers(plan,[bad]),QuestionError);
  }
});
test("V4 sensitive, duplicate or overflowing native select options remain manual", () => {
  const ordinary = { type:"select", label:"Choose a source", id:"source",
    name:"source", maxLength:-1,
    options:[{value:"yes",label:"Yes"},{value:"yes",label:"Yes again"}]};
  assert.equal(planReviewedQuestions([row(ordinary)]).questions.length,0);
  const sensitive = {...ordinary, label:"Do you consent to GDPR processing?",
    options:[{value:"yes",label:"Yes"},{value:"no",label:"No"}]};
  assert.equal(planReviewedQuestions([row(sensitive)]).questions.length,0);
  const tooMany = {...ordinary, options:Array.from({length:31},(_,i)=>({
    value:"value-"+i,label:"Label "+i
  }))};
  assert.equal(planReviewedQuestions([row(tooMany)]).questions.length,0);
});

test("V4 rejects entire voluntary disclosure dropdown if even one choice is sensitive", () => {
  const rows = [
    {
      type:"select",label:"Voluntary self-identification",id:"demographic",
      name:"demographic",maxLength:-1,
      options:[
        {value:"yes",label:"Yes, I have a disability",disabled:false},
        {value:"no",label:"No, I do not have one",disabled:false},
        {value:"decline",label:"I prefer not to say",disabled:false},
      ],
    },
    {
      type:"select",label:"Choose an option",id:"optional",name:"optional",
      maxLength:-1,options:[
        {value:"yes",label:"I require visa sponsorship",disabled:false},
        {value:"no",label:"No",disabled:false}
      ],
    },
  ];
  for (const candidate of rows) {
    const result = planReviewedQuestions([row(candidate)]);
    assert.equal(result.questions.length,0,candidate.label);
    assert.deepEqual(result.humanOnly,[candidate.label],candidate.label);
  }
  assert.equal(isSensitiveQuestion(row({label:"Equal employment opportunity"})),true);
  assert.equal(isSensitiveQuestion(row({label:"Voluntary self-identification"})),true);
});

test("V4 rejects entire demographic option dropdown, even with an ordinary heading", () => {
  for(const optionLabel of [
    "Male", "Female", "Non-binary", "Asian",
    "Black or African American", "White", "Hispanic"
  ]) {
    const candidate=row({
      type:"select", label:"Choose an option", id:"field",
      name:"field", maxLength:-1, options:[
        {value:"answer",label:optionLabel,disabled:false},
        {value:"other",label:"Other",disabled:false}
      ]
    });
    const plan=planReviewedQuestions([candidate]);
    assert.equal(plan.questions.length,0,optionLabel);
    assert.deepEqual(plan.humanOnly,["Choose an option"],optionLabel);
  }
});

test("V4 optgroup heading remains protected, but ordinary group preserves full review context", () => {
  const options=[
    {value:"source-1",label:"Job board",group:"Job sources",disabled:false},
    {value:"source-2",label:"Referral",group:"Job sources",disabled:false}
  ];
  const candidate=row({
    type:"select",label:"Choose an option",id:"where",name:"where",
    maxLength:-1,options
  });
  const allowed=planReviewedQuestions([candidate]);
  assert.equal(allowed.questions.length,1);
  assert.deepEqual(allowed.questions[0].options.map(o=>o.group),["Job sources","Job sources"]);
  assert.deepEqual(validateReviewedAnswers(allowed,["source-1"]).map(o=>o.value),["source-1"]);

  const protectedGroup=row({
    ...candidate,
    options:options.map(o=>({...o,group:"Disability status"}))
  });
  const denied=planReviewedQuestions([protectedGroup]);
  assert.equal(denied.questions.length,0);
  assert.deepEqual(denied.humanOnly,["Choose an option"]);

  // Revalidation still fails if an already reviewed plan changes later.
  allowed.questions[0].options[1].label="Female";
  assert.throws(()=>validateReviewedAnswers(allowed,["source-1"]),QuestionError);
});

test("V4 option labels with immigration or legal semantics stay fully manual", () => {
  for(const label of ["Immigration status","Legal status"]) {
    const candidate=row({
      type:"select",label:"Choose an option",id:"ordinary_choice",
      name:"ordinary_choice",maxLength:-1,options:[
        {value:"option-1",label,disabled:false},
        {value:"option-2",label:"Other",disabled:false},
      ]
    });
    const result=planReviewedQuestions([candidate]);
    assert.equal(result.questions.length,0,label);
    assert.deepEqual(result.humanOnly,["Choose an option"],label);
    assert.equal(isSensitiveQuestion(row({label})),true,label);
  }
});

test("profile-once dropdown suggests only an exact current employer option, never an alias", () => {
  const select = row({
    type:"select",label:"Where did you hear about this job?",
    id:"source",name:"source",maxLength:-1,
    options:[{value:"",label:"Choose",disabled:true},
      {value:"job-site",label:"Career site",disabled:false},
      {value:"employee-referral",label:"Employee referral",disabled:false}]
  });
  const plan=planReviewedQuestions([select]);
  assert.equal(plan.questions.length,1);
  const good=suggestSavedAnswers(plan,[{
    question:select.label,answer:"employee-referral"
  }]);
  assert.equal(good.reused,1);
  assert.deepEqual(good.values,["employee-referral"]);
  assert.deepEqual(good.needsReview,[]);
  for(const stale of ["Employee referral","employee","EMPLOYEE-REFERRAL",
    "employee-referral ", "job-site "]) {
    const result=suggestSavedAnswers(plan,[{
      question:select.label,answer:stale
    }]);
    assert.equal(result.reused,0,stale);
    assert.deepEqual(result.values,[""],stale);
    assert.deepEqual(result.needsReview,[select.label],stale);
  }
});


test("mixed exact saved and changed questions send only unchanged answer on first pass", () => {
  const known = row({index:1,label:"Where did you hear about us?",
    id:"source_details",name:"source_details"});
  const changed = row({index:2,label:"Which team outcome best matches your experience?",
    id:"team_outcome",name:"team_outcome"});
  const plan = planReviewedQuestions([known,changed]);
  const remembered = suggestSavedAnswers(plan, [
    {question:"Where did you hear about us?",answer:"The employer career page"},
    {question:"Which team result best matches your experience?",
      answer:"This OLD wording must not be reused"}
  ]);
  assert.equal(remembered.reused,1);
  assert.deepEqual(remembered.values,["The employer career page",""]);
  assert.deepEqual(remembered.needsReview,[changed.label]);
  const firstPass = validateReviewedAnswers(plan,remembered.values);
  assert.equal(firstPass.length,1);
  assert.equal(firstPass[0].label,known.label);
  assert.equal(firstPass[0].value,"The employer career page");
  assert.equal(firstPass.some(x=>x.label===changed.label),false);
});
