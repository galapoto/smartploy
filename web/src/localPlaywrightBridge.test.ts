import { describe, it, expect } from "vitest";
import { localReviewedQuestionValid } from "./localPlaywrightBridge";

// Pure transport boundary tests: the local helper may send untrusted JSON.
// Validating a native select does not authorize employer final submission.
const base = {
  index: 4, type: "select", label: "Where did you hear about this job?",
  expected_id: "job_source", expected_name: "job_source",
  expected_placeholder: "", expected_max_length: -1,
  max_answer_length: 1500,
};
const approved = {
  ...base, options: [
    { value: "job-board", label: "Job board" },
    { value: "referral", label: "Referral" },
  ],
};

describe("V4 exact reviewed Playwright dropdown transport", () => {
  it("allows a bounded exact option set and keeps ordinary text compatible", () => {
    expect(localReviewedQuestionValid(approved)).toBe(true);
    expect(localReviewedQuestionValid({
      ...base, type: "textarea", options: undefined
    })).toBe(true);
    expect(localReviewedQuestionValid({ ...base, type: "text", options: [] })).toBe(false);
  });

  it("refuses missing, ambiguous, duplicate or oversized options", () => {
    expect(localReviewedQuestionValid({ ...base })).toBe(false);
    expect(localReviewedQuestionValid({ ...base, options: [] })).toBe(false);
    expect(localReviewedQuestionValid({
      ...base, options: [{ value: "same", label: "Yes" }, { value: "same", label: "No" }]
    })).toBe(false);
    expect(localReviewedQuestionValid({
      ...base, options: [{ value: "x", label: "Same" }, { value: "y", label: " same " }]
    })).toBe(false);
    expect(localReviewedQuestionValid({
      ...base, options: [{ value: "x", label: "X", selected: true }]
    })).toBe(false);
    expect(localReviewedQuestionValid({
      ...base, options: Array.from({ length: 25 }, (_, i) =>
        ({ value: String(i), label: String(i) }))
    })).toBe(false);
  });
});

describe("V4 radio-group reviewed transport safety", () => {
  const group = {
    index: 3, type: "radio_group", label: "Where did you hear about this job?",
    expected_id: "friend", expected_name: "job_source",
    expected_placeholder: "", expected_max_length: -1,
    max_answer_length: 150,
    options: [
      {index:3, id:"friend", value:"friend", label:"Friend referral"},
      {index:4, id:"board", value:"job-board", label:"Job board"},
    ]
  };
  it("accepts a bounded first-party observed fieldset group", () => {
    expect(localReviewedQuestionValid(group)).toBe(true);
  });
  it("rejects duplicate, drifted and unobserved group options", () => {
    expect(localReviewedQuestionValid({...group, options:undefined})).toBe(false);
    expect(localReviewedQuestionValid({...group, options:[] })).toBe(false);
    expect(localReviewedQuestionValid({...group, options:[group.options[0]]})).toBe(false);
    expect(localReviewedQuestionValid({...group, expected_id:"changed"})).toBe(false);
    expect(localReviewedQuestionValid({...group, options:[
      group.options[0], {...group.options[1], index:3}
    ]})).toBe(false);
    expect(localReviewedQuestionValid({...group, options:[
      group.options[0], {...group.options[1], label:"Friend referral"}
    ]})).toBe(false);
    expect(localReviewedQuestionValid({...group, options:[
      group.options[0], {...group.options[1], checked:true}
    ]})).toBe(false);
  });
});
