import test from "node:test";
import assert from "node:assert/strict";
import { identifyField, PacketError, planFields, validatePacket } from "../logic.mjs";

const job = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply";

function packet(overrides = {}) {
  const start = Date.parse("2026-10-11T09:20:00Z");
  return {
    schema: "smartploy.browser_handoff.v1",
    issued_at: new Date(start).toISOString(),
    expires_at: new Date(start + 900000).toISOString(),
    workspace_id: "kit-" + "a".repeat(30),
    revision: 3,
    document_sha256: "b".repeat(64),
    application_url: job,
    company: "The Upright Project",
    role_title: "Data Analyst",
    fields: {
      full_name: "Test Candidate",
      first_name: "Test",
      last_name: "Candidate",
      email: "person@example.org",
      phone: "+358 40 1234567",
      location: "Helsinki",
      linkedin: "https://www.linkedin.com/in/test-candidate",
      github: "",
      cover_letter: "Dear hiring team, I have reviewed this letter and approve it for my job application."
    },
    privacy: {
      approved_contact_only: true,
      original_cv_included: false,
      browser_form_fill_allowed_after_user_click: true,
      employer_submit_allowed_without_new_approval: false
    },
    ...overrides
  };
}

const validNow = Date.parse("2026-10-11T09:23:00Z");

test("valid 15-minute application packet only for the exact job URL", () => {
  const result = validatePacket(JSON.stringify(packet()), job, validNow);
  assert.equal(result.role_title, "Data Analyst");
  assert.equal(result.fields.email, "person@example.org");
  assert.equal(result.fields.cover_letter.length > 30, true);
  assert.equal(Object.hasOwn(result, "original_cv"), false);
  assert.equal(Object.hasOwn(result, "may_submit"), false);
});

test("reject even a matching malicious non-Lever host; auto-fill is scoped to supported ATS", () => {
  const unsupported = "https://evil.example.com/uprightproject/fake-job/apply";
  assert.throws(() => validatePacket(packet({ application_url: unsupported }), unsupported, validNow), PacketError);
});

test("reject expired, future, overlong, malformed and unsupported packets", () => {
  const inputs = [
    packet({expires_at: new Date(validNow - 1).toISOString()}),
    packet({issued_at: new Date(validNow + 150000).toISOString()}),
    packet({expires_at: new Date(validNow + 3600000).toISOString()}),
    packet({schema: "untrusted"}),
    packet({revision: -1}),
    packet({workspace_id: "../private"}),
    packet({document_sha256: "x"}),
    packet({privacy: {...packet().privacy, employer_submit_allowed_without_new_approval: true}}),
    packet({fields: {...packet().fields, email: "invalid"}}),
    packet({fields: {...packet().fields, cover_letter: "x".repeat(12000)}}),
  ];
  for (const source of inputs) {
    assert.throws(() => validatePacket(source, job, validNow), PacketError);
  }
  assert.throws(() => validatePacket("x".repeat(41000), job, validNow), PacketError);
  assert.throws(() => validatePacket("not JSON", job, validNow), PacketError);
});

test("wrong job, origin, protocol or other applicant link always blocked", () => {
  for (const url of [
    "https://jobs.lever.co/othercompany/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply",
    "https://evil.example.com/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply",
    "http://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply",
    "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/other",
    "about:blank",
  ]) {
    assert.throws(() => validatePacket(packet(), url, validNow), PacketError);
  }
});

function element(props) {
  return {
    index: 0, type: "text", label: "", name: "", id: "",
    autocomplete: "", required: false, hasValue: false,
    readonly: false, disabled: false, visible: true, maxLength: -1,
    ...props
  };
}

test("strict contact mapping for English, Finnish and Swedish", () => {
  const matches = [
    [element({label: "Full name"}), "full_name"],
    [element({label: "First name"}), "first_name"],
    [element({label: "Last name"}), "last_name"],
    [element({label: "Etunimi"}), "first_name"],
    [element({label: "Sukunimi"}), "last_name"],
    [element({label: "Sähköpostiosoite", type: "email"}), "email"],
    [element({label: "Förnamn"}), "first_name"],
    [element({label: "E-post", type: "email"}), "email"],
    [element({autocomplete: "given-name", label: "Name"}), "first_name"],
    [element({autocomplete: "family-name", label: "Name"}), "last_name"],
    [element({label: "LinkedIn profile URL", type: "url"}), "linkedin"],
    [element({label: "Cover letter", type: "textarea"}), "cover_letter"],
  ];
  for (const [field, target] of matches) {
    assert.equal(identifyField(field), target, field.label);
  }
});

test("refuse bank, employer identity and legal consent fields", () => {
  for (const row of [
    element({label: "Company name"}),
    element({label: "Employer reference"}),
    element({label: "Password", type: "password"}),
    element({label: "CV upload", type: "file"}),
    element({label: "I agree to privacy policy", type: "checkbox"}),
    element({label: "Submit application", type: "submit"}),
    element({label: "Salary", type: "number"}),
    element({label: "Email", visible: false}),
    element({label: "Phone", disabled: true}),
  ]) {
    assert.equal(identifyField(row), null);
  }
});

test("refuse files and unknown required answers, preserve existing values", () => {
  const rows = [
    element({index: 0, label: "Full name", required: true}),
    element({index: 1, label: "Email", required: true, type: "email", hasValue: true}),
    element({index: 2, label: "Upload résumé", type: "file", required: true}),
    element({index: 3, label: "Visa type", required: true, type: "select"}),
    element({index: 4, label: "Phone number", type: "tel", required: true}),
    element({index: 5, label: "Company name", required: true}),
    element({index: 6, label: "Agree to policy", type: "checkbox", required: true}),
    element({index: 7, label: "Cover letter", type: "textarea"}),
  ];
  const result = planFields(rows, validatePacket(packet(), job, validNow));
  assert.deepEqual(result.actions.map((a) => a.key), ["full_name", "phone", "cover_letter"]);
  assert.equal(result.autoSubmitAllowed, false);
  assert.equal(result.skippedUploads.length, 1);
  assert.ok(result.unresolvedRequired.some(x => x.includes("résumé")));
  assert.ok(result.unresolvedRequired.some(x => x.includes("Visa type")));
  assert.ok(result.unresolvedRequired.some(x => x.includes("Agree to policy")));
});

test("additional information receives reviewed letter only when no dedicated cover-letter field exists", () => {
  const base = [
    element({index: 0, label: "Additional information", type: "textarea"}),
  ];
  const pkt = validatePacket(packet(), job, validNow);
  assert.equal(planFields(base, pkt).actions[0].key, "cover_letter");
  assert.equal(planFields([...base, element({
    index: 1, label: "Cover letter", type: "textarea"
  })], pkt).actions.length, 1);
});

test("conservative input limits and missing values stay unfilled", () => {
  const pkt = validatePacket(packet(), job, validNow);
  assert.throws(() => planFields(Array.from({length: 251}, (_, i) => element({index:i})), pkt), PacketError);
  const rows = [
    element({index: 0, label: "Full name", maxLength: 5}),
    element({index: 1, label: "Unknown control", required: true}),
  ];
  const result = planFields(rows, pkt);
  assert.equal(result.actions.length, 0);
  assert.equal(result.unresolvedRequired.length, 1); // first row was not 'required'
});
