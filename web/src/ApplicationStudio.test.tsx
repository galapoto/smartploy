// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import ApplicationStudio from "./ApplicationStudio";
import type {
  ApplicationAgentInboxItem, ApplicationWorkspace, ApplicationWorkspacesResponse, SessionInfo,
} from "./types";

vi.mock("./api", () => ({
  getSession: vi.fn(),
  getApplicationWorkspaces: vi.fn(),
  getApplicationWorkspaceById: vi.fn(),
  getApplicationAgents: vi.fn(),
  getApplicationAgentInbox: vi.fn(),
  checkDueApplicationAgentInbox: vi.fn(),
  getApplicationAgentForWorkspace: vi.fn(),
  getApplicationAgent: vi.fn(),
  createApplicationAgent: vi.fn(),
  changeApplicationAgent: vi.fn(),
  getLocalAIStatus: vi.fn(),
  getBrowserHandoffReadiness: vi.fn(),
  getEmployerAttemptStatus: vi.fn(),
  getEmployerReviewIntent: vi.fn(),
  getEmployerFinalActionReadiness: vi.fn(),
  getLeverPartnerReadiness: vi.fn(),
  getLeverPartnerReceipt: vi.fn(),
  sendLeverPartnerApplication: vi.fn(),
  getAshbyPartnerReadiness: vi.fn(),
  getAshbyPartnerReceipt: vi.fn(),
  sendAshbyPartnerApplication: vi.fn(),
  recordEmployerReviewIntent: vi.fn(),
  cancelEmployerReviewIntent: vi.fn(),
  getBrowserReceipt: vi.fn(),
  editApplicationWorkspace: vi.fn(),
  deleteApplicationWorkspace: vi.fn(),
  markApplicationManuallySent: vi.fn(),
  requestLocalAISuggestions: vi.fn(),
  proposeEvidenceLetter: vi.fn(),
  createBrowserHandoffPacket: vi.fn(),
  importBrowserReceipt: vi.fn(),
  applicationDownloadUrl: vi.fn(() => "/synthetic-download"),
}));

function job(tag: string): ApplicationWorkspace {
  return {
    workspace_id: "workspace-" + tag, canonical_key: "fictional-" + tag,
    role_title: tag + " private role", company: "Fictional Employer",
    application_url: "https://jobs.lever.co/synthetic-fi/job-" + tag,
    cv_text: "PRIVATE-CV-" + tag, cover_letter_text: "PRIVATE-LETTER-" + tag,
    source_cv_sha256: "a".repeat(64), approved_evidence_ids: [],
    revision: 1, status: "draft", self_reported_applied_at: "",
    self_reported_reference: "", created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    authority: {
      may_edit: true, may_download: true, may_submit_to_employer: false,
      has_external_submission_proof: false,
    },
  };
}

function draft(tag: string): ApplicationWorkspacesResponse {
  return { workspaces: [job(tag)], count: 1 };
}

function inboxItem(tag: string): ApplicationAgentInboxItem {
  return {
    agent_id: "agent-" + tag, workspace_id: "workspace-" + tag,
    canonical_key: "fictional-" + tag, role_title: tag + " private role",
    company: "Fictional Employer", state: "active", revision: 1,
    next_due_at: "2026-10-25T10:00:00Z",
    last_woke_at: "", created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z", closed_at: "", close_reason: "",
    milestone: "none", milestone_source: "none",
    workspace_status: "draft", observed_workspace_status: "draft",
    followups_sent: 0, last_followup_at: "", followup_suggestion: "",
    external_actions_authorized: false, employer_contacted: false,
    notification_channel: "in_app_only", attention_state: "due_review",
  };
}

function session(id: string): SessionInfo {
  return {
    authenticated: true, email: "same-email@example.invalid",
    user_id: id, profile_id: "profile-" + id, auth_source: "oidc",
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((success, failure) => {
    resolve = success; reject = failure;
  });
  return { promise, resolve, reject };
}

let activeUser = "usr-a";
const studio = () => render(<ApplicationStudio
  focusId="" expectedUserId="usr-a" expectedAuthSource="oidc"
  onFindJobs={vi.fn()}
/>);

beforeEach(() => {
  vi.resetAllMocks();
  activeUser = "usr-a";
  vi.mocked(api.getSession).mockImplementation(async () => session(activeUser));
  vi.mocked(api.getApplicationWorkspaces).mockResolvedValue(draft("A"));
  vi.mocked(api.getApplicationWorkspaceById).mockRejectedValue(
    new Error("No such owned application in this synthetic fixture"),
  );
  vi.mocked(api.getApplicationAgentInbox).mockResolvedValue({
    items: [], count: 0, has_more: false, next_offset: null,
    background_worker_verified: false, external_actions_authorized: false,
  });
  vi.mocked(api.checkDueApplicationAgentInbox).mockResolvedValue({
    checked_in_app: true, cases_checked: 1, in_app_reminders: 1,
    workspace_updates_reconciled: 0, more_actionable_cases: false,
    external_actions_performed: 0, employer_contacts: 0,
    background_worker_verified: false,
  });
  vi.mocked(api.getApplicationAgents).mockResolvedValue({
    agents: [], count: 0, external_actions_authorized: false,
  });
  vi.mocked(api.getApplicationAgentForWorkspace).mockResolvedValue({
    present: false, agent: null, external_actions_authorized: false,
  });
  vi.mocked(api.getLocalAIStatus).mockResolvedValue({
    configured: false, ready: false, provider: "disabled",
    model: "", external_ai_forwarding: false,
  });
  vi.mocked(api.getBrowserHandoffReadiness).mockResolvedValue({
    ready: true, blockers: [], document_revision: 1,
    contact_fields_ready: true, employer_submission_performed: false,
    will_require_manual_review: true, files_attached: false,
  });
  vi.mocked(api.getBrowserReceipt).mockResolvedValue({ present: false, receipt: null });
  vi.mocked(api.getEmployerReviewIntent).mockResolvedValue({
    review_recorded: false, review_state: "not_recorded", expires_at: "",
    automatic_employer_submit_authorized: false, external_actions_performed: false,
    browser_grant_issued: false,
  });
  vi.mocked(api.getLeverPartnerReadiness).mockResolvedValue({
    review_evidence:null,review_evidence_is_authorization:false,
    partner_provider:"lever",partner_api_configured:false,
    independent_partner_rights_reviewed:false,
    current_applicant_review_recorded:false,current_document_and_posting_ready:false,
    prior_employer_attempt:false,provider_acknowledged:false,
    eligible_for_explicit_partner_submit:false,
    unattended_auto_apply_enabled:false,automatic_retry_authorized:false
  });
  vi.mocked(api.getLeverPartnerReceipt).mockResolvedValue({
    present:false,receipt:null,
  });
  vi.mocked(api.sendLeverPartnerApplication).mockResolvedValue({
    state:"provider_acknowledged", provider:"lever",
    provider_application_id:"app-fixture-1234567890",
    provider_application_acknowledged:true,
    employer_hiring_decision_verified:false,automatic_retry_authorized:false,
    external_actions_performed:true,
  });
  vi.mocked(api.getAshbyPartnerReadiness).mockResolvedValue({
    partner_provider:"ashby",partner_api_configured:false,
    independent_partner_rights_reviewed:false,
    current_applicant_review_recorded:false,current_document_and_posting_ready:false,
    prior_employer_attempt:false,provider_acknowledged:false,
    eligible_for_explicit_partner_submit:false,review_evidence:null,
    review_evidence_is_authorization:false,
    unattended_auto_apply_enabled:false,automatic_retry_authorized:false,
  });
  vi.mocked(api.getAshbyPartnerReceipt).mockResolvedValue({
    present:false,receipt:null,
  });
  vi.mocked(api.sendAshbyPartnerApplication).mockResolvedValue({
    state:"provider_acknowledged", provider:"ashby",
    provider_application_id:"12345678-abcd-49ab-8abc-123456789012",
    provider_form_submission_id:"87654321-abcd-49ab-8abc-123456789012",
    provider_application_acknowledged:true,
    employer_hiring_decision_verified:false,automatic_retry_authorized:false,
    external_actions_performed:true,
  });
  vi.mocked(api.getEmployerFinalActionReadiness).mockResolvedValue({
    operator_permission_reviewed: false,
    current_applicant_review_recorded: false,
    separate_final_user_approval_recorded: false,
    previous_employer_attempt_reserved: false,
    trusted_one_use_browser_redemption_available: false,
    final_browser_click_authorized: false,
    employer_submission_performed: false,
    employer_receipt_verified: false,
    blockers: [
      "independent_employer_permission_missing",
      "trusted_one_use_browser_redemption_unavailable",
    ],
  });
  vi.mocked(api.recordEmployerReviewIntent).mockResolvedValue({
    review_recorded: true, review_state: "pending",
    expires_at: "2099-01-01T00:10:00+00:00",
    automatic_employer_submit_authorized: false, external_actions_performed: false,
    browser_grant_issued: false,
  });
  vi.mocked(api.cancelEmployerReviewIntent).mockResolvedValue({
    review_recorded: false, review_state: "cancelled", expires_at: "",
    automatic_employer_submit_authorized: false, external_actions_performed: false,
    browser_grant_issued: false,
  });
  vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue({
    previous_attempt_reserved: false, state: "not_reserved",
    requires_human_reconciliation: false, automatic_employer_submit_authorized: false,
    external_confirmation_verified: false, cross_device_server_claim_required: true
  });
  vi.mocked(api.editApplicationWorkspace).mockImplementation(async (_, __, cvText, coverLetterText) =>
    ({ workspace: { ...job("A"), cv_text: cvText, cover_letter_text: coverLetterText, revision: 2 } })
  );
  vi.mocked(api.proposeEvidenceLetter).mockImplementation(async (_, revision, language) => ({
    cover_letter: language === "fi"
      ? "Hei rekrytointitiimi,\\n\\nOsaaminen: Python\\n[Kerro omin sanoin]"
      : "Dear Hiring Team,\\n\\nSkill: Python\\n[Explain in your own words]",
    language, workspace_revision: revision,
    review_required: true, saved: false,
    external_actions_performed: 0, employer_contacts: 0,
  }));
  vi.mocked(api.requestLocalAISuggestions).mockResolvedValue({
    workspace_revision: 1,
    suggestion: {
      provider: "local_obumai_ollama", model: "synthetic-fixture", approved_evidence_ids: [],
      external_actions_performed: false, suggestions_applied: false, requires_owner_review: true,
      proposal: {
        schema: "smartploy.local_draft.v1",
        cv_headline: "Synthetic job title", cv_summary: "Synthetic approved evidence",
        cover_letter: "Synthetic cover letter", highlights: [], risks: [], review_notes: [],
      },
    },
  });
  vi.mocked(api.markApplicationManuallySent).mockResolvedValue({
    workspace: { ...job("A"), status: "self_reported_applied", revision: 2 },
    external_confirmation_verified: false,
  });
  vi.mocked(api.deleteApplicationWorkspace).mockResolvedValue({ deleted: true });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Application Studio private-read account boundary", () => {

  it("shows rights withheld without an employer-submit button or fake success",async()=>{
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const panel=await screen.findByLabelText("Employer final-action permission");
    expect(panel.textContent).toContain("not attested");
    expect(panel.textContent).toContain("never permits");
    expect(api.getEmployerFinalActionReadiness).toHaveBeenCalledWith("workspace-A");
    expect(screen.queryByRole("button",{name:/Automatically submit to employer/i})).toBeNull();
  });

  it("a rejected policy read stays blocked; it does not make an automatic submit possible",async()=>{
    vi.mocked(api.getEmployerFinalActionReadiness).mockRejectedValue(
      new Error("Policy database unavailable")
    );
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const panel=await screen.findByLabelText("Employer final-action permission");
    expect(panel.textContent).toContain("Policy verification unavailable");
    expect(panel.textContent).toContain("blocked");
  });


  it("keeps direct partner submission unavailable for an unapproved employer",async()=>{
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const panel=await screen.findByLabelText("Official Lever partner submission");
    expect(panel.textContent).toContain("No authorized direct Lever submission");
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Lever employer/
    })).toBeNull();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it.each([
    ["hosted Greenhouse", "https://boards.greenhouse.io/syntheticfi/jobs/12345"],
    ["unrelated employer", "https://example.invalid/job-A"],
    ["Lever lookalike host", "https://jobs.lever.co.evil.invalid/synthetic-fi/role"],
    ["Ashby lookalike host", "https://jobs.ashbyhq.com.evil.invalid/synthetic-fi/role"],
    ["plain HTTP", "http://jobs.lever.co/synthetic-fi/role"],
    ["credential-bearing URL", "https://user:secret@jobs.ashbyhq.com/synthetic-fi/role"],
    ["nondefault port", "https://jobs.lever.co:444/synthetic-fi/role"],
  ])("SP54 keeps %s on manual handoff without partner API calls",async(_,applicationUrl)=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),application_url:applicationUrl}],count:1,
    });
    studio();
    const fallback=await screen.findByLabelText("Manual-only employer application");
    expect(fallback.textContent).toContain("no direct employer API submission");
    expect(fallback.textContent).toContain("personally complete");
    await waitFor(()=>expect(api.getEmployerFinalActionReadiness)
      .toHaveBeenCalledWith("workspace-A"));
    expect(api.getLeverPartnerReadiness).not.toHaveBeenCalled();
    expect(api.getLeverPartnerReceipt).not.toHaveBeenCalled();
    expect(api.getAshbyPartnerReadiness).not.toHaveBeenCalled();
    expect(api.getAshbyPartnerReceipt).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Official Lever partner submission")).toBeNull();
    expect(screen.queryByLabelText("Official Ashby partner submission")).toBeNull();
    expect(screen.queryByRole("button",{name:/Submit reviewed application to authorized/})).toBeNull();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    expect(api.sendAshbyPartnerApplication).not.toHaveBeenCalled();
  });

  it("SP54 preserves the official EU Lever host without treating other employers as Lever",async()=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),application_url:"https://jobs.eu.lever.co/synthetic-fi/job-A"}],count:1,
    });
    studio();
    const panel=await screen.findByLabelText("Official Lever partner submission");
    expect(panel.textContent).toContain("No authorized direct Lever submission");
    await waitFor(()=>expect(api.getLeverPartnerReadiness)
      .toHaveBeenCalledWith("workspace-A"));
    expect(api.getAshbyPartnerReadiness).not.toHaveBeenCalled();
  });

  it("SP54 ignores mismatched partner readiness and never exposes a send",async()=>{
    vi.mocked(api.getLeverPartnerReadiness).mockResolvedValue({
      partner_provider:"ashby",partner_api_configured:true,
      independent_partner_rights_reviewed:true,
      current_applicant_review_recorded:true,current_document_and_posting_ready:true,
      prior_employer_attempt:false,provider_acknowledged:false,
      eligible_for_explicit_partner_submit:true,review_evidence:{
        workspace_id:"workspace-A",revision:1,expires_at:"2099-01-01T00:15:00Z",
        document_sha256:"a".repeat(64),cv_pdf_sha256:"b".repeat(64),
        approved_fields_sha256:"c".repeat(64),cv_pdf_size:1002,
      },
      review_evidence_is_authorization:false,
      unattended_auto_apply_enabled:false,automatic_retry_authorized:false,
    });
    studio();
    const panel=await screen.findByLabelText("Official Lever partner submission");
    await waitFor(()=>expect(panel.textContent).toContain("Partner readiness unavailable"));
    expect(screen.queryByRole("button",{name:/Record reviewed CV, letter and job/})).toBeNull();
    expect(screen.queryByRole("button",{name:/Submit reviewed application to authorized/})).toBeNull();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    expect(api.sendAshbyPartnerApplication).not.toHaveBeenCalled();
  });

  it("SP54 never labels an unsupported provider acknowledgement as Lever",async()=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),status:"provider_acknowledged",
        application_url:"https://boards.greenhouse.io/syntheticfi/jobs/12345"}],count:1,
    });
    studio();
    expect(await screen.findByText("Sent · provider acknowledged")).toBeTruthy();
    expect(await screen.findByLabelText("Employer provider acknowledgement")).toBeTruthy();
    expect(screen.queryByLabelText("Official Lever provider acknowledgement")).toBeNull();
    expect(api.getLeverPartnerReceipt).not.toHaveBeenCalled();
    expect(api.getAshbyPartnerReceipt).not.toHaveBeenCalled();
  });

  it("reviews and completes a real authorized partner application without copying private data",async()=>{
    const reviewEvidence={
      workspace_id:"workspace-A", revision:1,
      expires_at:"2099-01-01T00:15:00Z",
      document_sha256:"a".repeat(64),cv_pdf_sha256:"b".repeat(64),
      approved_fields_sha256:"c".repeat(64),cv_pdf_size:1002
    };
    const ready={
      partner_provider:"lever" as const,partner_api_configured:true,
      independent_partner_rights_reviewed:true,
      current_applicant_review_recorded:true,current_document_and_posting_ready:true,
      prior_employer_attempt:false,provider_acknowledged:false,
      eligible_for_explicit_partner_submit:true,review_evidence:reviewEvidence,
      review_evidence_is_authorization:false as const,
      unattended_auto_apply_enabled:false as const,automatic_retry_authorized:false as const
    };
    vi.mocked(api.getLeverPartnerReadiness)
      .mockResolvedValueOnce({...ready,current_applicant_review_recorded:false,
        eligible_for_explicit_partner_submit:false})
      .mockResolvedValue(ready);
    vi.spyOn(window,"confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const official=await screen.findByLabelText("Official Lever partner submission");
    expect(official.textContent).toContain("No extension, copied personal-data packet or clipboard");
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Lever employer/
    })).toBeNull();
    const review=await screen.findByRole("button",{
      name:/Record reviewed CV, letter and job \(no submit\)/
    });
    fireEvent.click(review);
    await waitFor(()=>expect(api.recordEmployerReviewIntent).toHaveBeenCalledWith(
      "workspace-A",1,"a".repeat(64),"b".repeat(64),"usr-a"
    ));
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    await waitFor(()=>expect(api.getLeverPartnerReadiness).toHaveBeenCalledTimes(2));
    const send=await screen.findByRole("button",{
      name:/Submit reviewed application to authorized Lever employer/
    });
    await waitFor(()=>expect((send as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(send);
    await waitFor(()=>expect(api.sendLeverPartnerApplication).toHaveBeenCalledWith(
      "workspace-A",1,"a".repeat(64),"b".repeat(64),
      "c".repeat(64),1002,"usr-a"
    ));
    const acknowledged=await screen.findByLabelText("Official Lever provider acknowledgement");
    expect(acknowledged.textContent).toContain("app-fixture-1234567890");
    expect(await screen.findByText("Sent · Lever acknowledged")).toBeTruthy();
    expect(screen.getByText(/Documents are locked to preserve the submitted version/)).toBeTruthy();
    expect(screen.queryByRole("button",{name:/I applied on employer site/})).toBeNull();
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Lever employer/
    })).toBeNull();
    expect(api.sendLeverPartnerApplication).toHaveBeenCalledTimes(1);
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
  });

  it("SP52 reviews and sends once to an independently authorized Ashby partner, never Lever",async()=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),
        application_url:"https://jobs.ashbyhq.com/synthetic-fi/junior-qa"}],count:1,
    });
    const evidence={
      workspace_id:"workspace-A",revision:1,expires_at:"2099-01-01T00:15:00Z",
      document_sha256:"a".repeat(64),cv_pdf_sha256:"b".repeat(64),
      approved_fields_sha256:"c".repeat(64),cv_pdf_size:1002,
    };
    const ready={
      partner_provider:"ashby" as const,partner_api_configured:true,
      independent_partner_rights_reviewed:true,
      current_applicant_review_recorded:true,current_document_and_posting_ready:true,
      prior_employer_attempt:false,provider_acknowledged:false,
      eligible_for_explicit_partner_submit:true,review_evidence:evidence,
      review_evidence_is_authorization:false as const,
      unattended_auto_apply_enabled:false as const,automatic_retry_authorized:false as const,
    };
    vi.mocked(api.getAshbyPartnerReadiness)
      .mockResolvedValueOnce({...ready,current_applicant_review_recorded:false,
        eligible_for_explicit_partner_submit:false})
      .mockResolvedValue(ready);
    vi.spyOn(window,"confirm").mockReturnValue(true);
    studio();
    const panel=await screen.findByLabelText("Official Ashby partner submission");
    expect(panel.textContent).toContain("No extension, copied personal-data packet or clipboard");
    expect(api.getLeverPartnerReadiness).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button",{
      name:/Record reviewed CV, letter and job \(no submit\)/
    }));
    await waitFor(()=>expect(api.getAshbyPartnerReadiness).toHaveBeenCalledTimes(2));
    expect(api.sendAshbyPartnerApplication).not.toHaveBeenCalled();
    const send=await screen.findByRole("button",{
      name:/Submit reviewed application to authorized Ashby employer/
    });
    fireEvent.click(send);
    await waitFor(()=>expect(api.sendAshbyPartnerApplication).toHaveBeenCalledWith(
      "workspace-A",1,"a".repeat(64),"b".repeat(64),
      "c".repeat(64),1002,"usr-a"
    ));
    const proof=await screen.findByLabelText("Official Ashby provider acknowledgement");
    expect(proof.textContent).toContain("12345678-abcd-49ab-8abc-123456789012");
    expect(await screen.findByText("Sent · Ashby acknowledged")).toBeTruthy();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    expect(api.sendAshbyPartnerApplication).toHaveBeenCalledTimes(1);
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Ashby employer/
    })).toBeNull();
  });

  it("SP52 rejects Ashby submit without independent posting permission or review",async()=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),
        application_url:"https://jobs.ashbyhq.com/synthetic-fi/junior-qa"}],count:1,
    });
    studio();
    const panel=await screen.findByLabelText("Official Ashby partner submission");
    expect(panel.textContent).toContain("No authorized direct Ashby submission");
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Ashby employer/
    })).toBeNull();
    expect(api.sendAshbyPartnerApplication).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("reloads an independently acknowledged application as non-editable, never a draft",async()=>{
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces:[{...job("A"),status:"provider_acknowledged"}],count:1
    });
    vi.mocked(api.getLeverPartnerReceipt).mockResolvedValue({
      present:true,
      receipt:{provider:"lever",provider_application_id:"confirmed-identity-12345",
        provider_application_acknowledged:true,
        employer_hiring_decision_verified:false,automatic_retry_authorized:false}
    });
    studio();
    expect(await screen.findByText("Sent · Lever acknowledged")).toBeTruthy();
    const proof=await screen.findByLabelText("Official Lever provider acknowledgement");
    await waitFor(()=>expect(proof.textContent).toContain("confirmed-identity-12345"));
    expect(screen.getByText(/Documents are locked to preserve the submitted version/)).toBeTruthy();
    expect(screen.queryByRole("button",{name:/Save changes/})).toBeNull();
    expect(screen.queryByRole("button",{name:/I applied on employer site/})).toBeNull();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("stale or withheld non-bearer evidence never creates an employer action",async()=>{
    const evidence={
      workspace_id:"workspace-A",revision:2,
      expires_at:"2099-01-01T00:15:00Z",
      document_sha256:"a".repeat(64),cv_pdf_sha256:"b".repeat(64),
      approved_fields_sha256:"c".repeat(64),cv_pdf_size:1002,
    };
    vi.mocked(api.getLeverPartnerReadiness).mockResolvedValue({
      partner_provider:"lever",partner_api_configured:true,
      independent_partner_rights_reviewed:true,
      current_applicant_review_recorded:true,current_document_and_posting_ready:true,
      prior_employer_attempt:false,provider_acknowledged:false,
      eligible_for_explicit_partner_submit:true,review_evidence:evidence,
      review_evidence_is_authorization:false,
      unattended_auto_apply_enabled:false,automatic_retry_authorized:false,
    });
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    expect(await screen.findByLabelText("Official Lever partner submission")).toBeTruthy();
    expect(screen.queryByRole("button",{
      name:/Record reviewed CV, letter and job/
    })).toBeNull();
    expect(screen.queryByRole("button",{
      name:/Submit reviewed application to authorized Lever employer/
    })).toBeNull();
    expect(api.recordEmployerReviewIntent).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });


  it("records the approved packet hashes for one job and can cancel, without a submit API", async () => {
    const packet = {
      schema: "smartploy.browser_handoff.v2" as const,
      issued_at: new Date().toISOString(),
      expires_at: "2099-01-01T00:15:00Z",
      application_url: "https://jobs.lever.co/synthetic/role",
      company: "Synthetic", role_title: "Review Test",
      workspace_id: "workspace-A", revision: 1,
      document_sha256: "a".repeat(64), cv_pdf_sha256: "b".repeat(64),
      cv_pdf_size: 1024,
      fields: {full_name:"Test Applicant", first_name:"Test", last_name:"Applicant",
        email:"test@example.invalid", phone:"", location:"", linkedin:"",github:"",
        cover_letter:"Approved synthetic cover letter"},
      privacy: {approved_contact_only:true as const, original_cv_included:false as const,
        browser_form_fill_allowed_after_user_click:true as const,
        employer_submit_allowed_without_new_approval:false as const},
    };
    vi.mocked(api.createBrowserHandoffPacket).mockResolvedValue({
      packet, external_actions_performed: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", {name:"A private role"})).toBeTruthy();
    const button=screen.getByRole("button",{name:/Copy approved autofill packet/});
    await waitFor(()=>expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    const record=await screen.findByRole("button",{name:/Record exact CV and job review/});
    await waitFor(()=>expect((record as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(record);
    await waitFor(()=>expect(api.recordEmployerReviewIntent).toHaveBeenCalledWith(
      "workspace-A", 1, "a".repeat(64), "b".repeat(64), "usr-a"
    ));
    expect(await screen.findByText(/Review recorded temporarily/)).toBeTruthy();
    expect(screen.getByLabelText("Employer final-action permission").textContent)
      .toContain("Current applicant review: recorded");
    expect(api.getEmployerAttemptStatus).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button",{name:"Cancel recorded review"}));
    await waitFor(()=>expect(api.cancelEmployerReviewIntent).toHaveBeenCalledWith(
      "workspace-A", "usr-a"
    ));
    await waitFor(()=>expect(screen.getByLabelText("Employer final-action permission").textContent)
      .toContain("Current applicant review: pending"));
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
  });

  it("never records the old account's reviewed packet after sign-in changes", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api.createBrowserHandoffPacket).mockResolvedValue({
      packet: {
        workspace_id:"workspace-A", revision:1,
        document_sha256:"a".repeat(64), cv_pdf_sha256:"b".repeat(64),
        expires_at:"2099-01-01T00:00:00Z",
      } as Awaited<ReturnType<typeof api.createBrowserHandoffPacket>>["packet"],
      external_actions_performed:false,
    });
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const copy=screen.getByRole("button",{name:/Copy approved autofill packet/});
    await waitFor(()=>expect((copy as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(copy);
    const record=await screen.findByRole("button",{name:/Record exact CV and job review/});
    activeUser="usr-b";
    fireEvent.click(record);
    expect(await screen.findByRole("heading",{name:"Account verification required"})).toBeTruthy();
    expect(api.recordEmployerReviewIntent).not.toHaveBeenCalled();
  });


  it("blocks a fresh private packet after the server reports an uncertain employer attempt", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue({
      previous_attempt_reserved: true, state: "uncertain",
      requires_human_reconciliation: true, automatic_employer_submit_authorized: false,
      external_confirmation_verified: false, cross_device_server_claim_required: true
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/An attempt for this employer job is already reserved across devices/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Copy approved autofill packet/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
  });

  it("reconciles a consumed browser attempt with an observed receipt and owner report, never a second send", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue({
      previous_attempt_reserved: true, state: "uncertain",
      requires_human_reconciliation: true, automatic_employer_submit_authorized: false,
      external_confirmation_verified: false, cross_device_server_claim_required: true
    });
    const observed = {
      workspace_id: "workspace-A", document_revision: 1,
      document_sha256: "a".repeat(64),
      reference: "SYNTHETIC-ACK-1234", status: "browser_observed_unverified",
      observed_at: "2026-10-25T10:00:00Z", confirmation_page_url: "https://example.invalid/confirmed",
      confirmation_page_sha256: "b".repeat(64), evidence_digest: "c".repeat(64),
      independently_verified_by_employer: false, actually_submitted_count_changed: false,
    } as never;
    vi.mocked(api.getBrowserReceipt)
      .mockResolvedValueOnce({ present: false, receipt: null })
      .mockResolvedValue({ present: true, receipt: observed });
    vi.mocked(api.importBrowserReceipt).mockResolvedValue({
      receipt: observed, external_confirmation_verified: false
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("SYNTHETIC-ACK-1234");

    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const panel = await screen.findByLabelText("Reserved attempt reconciliation");
    expect(panel.textContent).toContain("Do not submit again");
    expect(panel.textContent).toContain("import its observed receipt");
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).readOnly).toBe(true);
    expect((screen.getByRole("textbox", { name: "Editable cover letter text" }) as HTMLTextAreaElement).readOnly).toBe(true);
    expect((screen.getByRole("button", { name: /Copy approved autofill packet/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Save changes/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Confirm outcome of previous attempt/ }) as HTMLButtonElement).disabled).toBe(true);

    // The existing owner-bound receipt import remains available AFTER claim
    // reservation; it is evidence-only and cannot perform an employer action.
    fireEvent.click(screen.getByRole("button", { name: /Import observed receipt/ }));
    const payload = {
      schema: "smartploy.browser_receipt.v1", workspace_id: "workspace-A",
      document_revision: 1, confirmed_visible: true,
    };
    fireEvent.change(screen.getByRole("textbox", { name: "Paste receipt from the companion" }), {
      target: { value: JSON.stringify(payload) },
    });
    fireEvent.click(screen.getByRole("button", { name: /Store observed confirmation/ }));
    await waitFor(() => expect(api.importBrowserReceipt).toHaveBeenCalledWith(
      "workspace-A", payload, "usr-a"
    ));
    expect(await screen.findByText(/confirmation was observed in your browser/)).toBeTruthy();

    const reconcile = screen.getByRole("button", { name: /Confirm outcome of previous attempt/ });
    expect((reconcile as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(reconcile);
    await waitFor(() => expect(api.markApplicationManuallySent).toHaveBeenCalledWith(
      "workspace-A", 1, "SYNTHETIC-ACK-1234", "usr-a"
    ));
    expect(confirm.mock.calls.some((c) =>
      String(c[0]).includes("RECONCILE THIS PREVIOUS EMPLOYER ATTEMPT")
    )).toBe(true);
    expect(await screen.findByText(/Recorded as personally reported applied/)).toBeTruthy();
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("does not mark a reserved attempt applied when the owner cannot confirm the result", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue({
      previous_attempt_reserved: true, state: "reserved_unverified",
      requires_human_reconciliation: true, automatic_employer_submit_authorized: false,
      external_confirmation_verified: false, cross_device_server_claim_required: true
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const reconcile = await screen.findByRole("button", { name: /Confirm outcome of previous attempt/ });
    expect((reconcile as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(reconcile);
    expect(confirm).not.toHaveBeenCalled();
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
    expect(api.importBrowserReceipt).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    expect(screen.getByText(/Previous attempt · outcome needs review/)).toBeTruthy();
  });

  it("shows manual-only guidance if the server attempt status cannot be verified", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockRejectedValue(new Error("Synthetic database unavailable"));
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    expect(await screen.findByText(/server attempt status is currently unavailable/)).toBeTruthy();
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
  });


  it("previews approved-evidence Finnish text without changing uploaded CV or saving automatically", async () => {
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const originalCV = (screen.getByRole("textbox", {
      name: "Editable CV text",
    }) as HTMLTextAreaElement).value;
    const initialLetter = (screen.getByRole("textbox", {
      name: "Editable cover letter text",
    }) as HTMLTextAreaElement).value;
    expect(initialLetter).toBe("PRIVATE-LETTER-A");
    fireEvent.click(screen.getByRole("button", { name: "Finnish draft" }));
    await waitFor(() => expect(api.proposeEvidenceLetter).toHaveBeenCalledWith(
      "workspace-A", 1, "fi", "usr-a",
    ));
    const letter = screen.getByRole("textbox", {
      name: "Editable cover letter text",
    }) as HTMLTextAreaElement;
    await waitFor(() => expect(letter.value).toContain("Hei rekrytointitiimi"));
    expect((screen.getByRole("textbox", {
      name: "Editable CV text",
    }) as HTMLTextAreaElement).value).toBe(originalCV);
    expect(screen.getByText(/Nothing was sent to an employer/)).toBeTruthy();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledWith(
      "workspace-A", 1, originalCV, expect.stringContaining("Hei rekrytointitiimi"), "usr-a",
    ));
  });

  it("never overwrites unsaved applicant wording after declined language confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const letter = screen.getByRole("textbox", {
      name: "Editable cover letter text",
    }) as HTMLTextAreaElement;
    fireEvent.change(letter, { target: { value: "Personally authored and not yet saved" } });
    fireEvent.click(screen.getByRole("button", { name: "English draft" }));
    expect(letter.value).toBe("Personally authored and not yet saved");
    expect(window.confirm).toHaveBeenCalled();
    expect(api.proposeEvidenceLetter).not.toHaveBeenCalled();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("does not publish stale language text after same-email sign-in changes", async () => {
    const pending = deferred<Awaited<ReturnType<typeof api.proposeEvidenceLetter>>>();
    vi.mocked(api.proposeEvidenceLetter).mockReturnValue(pending.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Finnish draft" }));
    await waitFor(() => expect(api.proposeEvidenceLetter).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    pending.resolve({
      cover_letter: "PRIVATE-PREVIOUS-ACCOUNT-FINNISH-LETTER",
      language: "fi", workspace_revision: 1,
      review_required: true, saved: false,
      external_actions_performed: 0, employer_contacts: 0,
    });
    expect(await screen.findByRole("heading", {
      name: "Account verification required",
    })).toBeTruthy();
    expect(screen.queryByText(/PRIVATE-PREVIOUS-ACCOUNT-FINNISH-LETTER/)).toBeNull();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("cannot redraft once a cross-device employer final attempt is reserved", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue({
      previous_attempt_reserved: true, state: "uncertain",
      requires_human_reconciliation: true,
      automatic_employer_submit_authorized: false,
      external_confirmation_verified: false,
      cross_device_server_claim_required: true,
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    await screen.findByLabelText("Reserved attempt reconciliation");
    expect((screen.getByRole("button", { name: "Finnish draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "English draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.proposeEvidenceLetter).not.toHaveBeenCalled();
  });

  it("keeps normal same-account loading, edits and refresh available", async () => {
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-A");
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "PRIVATE-CV-A plus unsaved draft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("heading", { name: "Account verification required" })).toBeNull();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-A plus unsaved draft");
    expect(api.getSession).toHaveBeenCalled();
  });

  it("blocks a changed same-email account before dispatching manual refresh", async () => {
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const before = vi.mocked(api.getApplicationWorkspaces).mock.calls.length;
    activeUser = "usr-b";
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(before);
    expect(screen.queryByText("PRIVATE-CV-A")).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("rejects B's delayed draft GET rather than displaying it in A's editor", async () => {
    const late = deferred<ApplicationWorkspacesResponse>();
    vi.mocked(api.getApplicationWorkspaces)
      .mockResolvedValueOnce(draft("A"))
      .mockImplementationOnce(() => late.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    activeUser = "usr-b";
    await act(async () => { late.resolve(draft("B")); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText("B private role")).toBeNull();
    expect(screen.queryByText("A private role")).toBeNull();
    expect(screen.queryByText("PRIVATE-CV-A")).toBeNull();
    expect(screen.queryByText("PRIVATE-CV-B")).toBeNull();
    expect(screen.queryByRole("link", { name: /download cv/i })).toBeNull();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("discards old overlapping refresh results after a newer same-account refresh", async () => {
    const old = deferred<ApplicationWorkspacesResponse>();
    const newest = deferred<ApplicationWorkspacesResponse>();
    vi.mocked(api.getApplicationWorkspaces)
      .mockResolvedValueOnce(draft("A"))
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => newest.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(3));
    await act(async () => { newest.resolve(draft("newest")); });
    expect(await screen.findByRole("heading", { name: "newest private role" })).toBeTruthy();
    await act(async () => { old.resolve(draft("old")); });
    expect(screen.queryByRole("heading", { name: "old private role" })).toBeNull();
    expect(screen.getByRole("heading", { name: "newest private role" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Account verification required" })).toBeNull();
  });

  it("clears private editor content when post-GET identity verification fails", async () => {
    const late = deferred<ApplicationWorkspacesResponse>();
    vi.mocked(api.getApplicationWorkspaces)
      .mockResolvedValueOnce(draft("A"))
      .mockImplementationOnce(() => late.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    vi.mocked(api.getSession).mockRejectedValueOnce(new Error("Synthetic session lookup failed"));
    await act(async () => { late.resolve(draft("A")); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Editable cover letter text" })).toBeNull();
    expect(screen.queryByText("PRIVATE-CV-A")).toBeNull();
  });

  it("fails closed for selected receipt/handoff reads completed under account B", async () => {
    const receipt = deferred<{ present: boolean; receipt: null }>();
    vi.mocked(api.getBrowserReceipt).mockImplementationOnce(() => receipt.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    await waitFor(() => expect(api.getBrowserReceipt).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { receipt.resolve({ present: false, receipt: null }); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
    expect(screen.queryByText("PRIVATE-LETTER-A")).toBeNull();
    expect(screen.queryByRole("button", { name: /copy approved autofill packet/i })).toBeNull();
  });
});


describe("Application Studio delayed mutation and private clipboard safeguards", () => {
  it("saves a same-user draft and retains editable text, using A's user precondition", async () => {
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "PRIVATE-CV-A updated after review" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledWith(
      "workspace-A", 1, "PRIVATE-CV-A updated after review", "PRIVATE-LETTER-A", "usr-a"
    ));
    expect(await screen.findByText(/Your edits were saved/)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-A updated after review");
    expect(screen.queryByRole("heading", { name: "Account verification required" })).toBeNull();
  });

  it("does not dispatch a draft save if the account changed before verification", async () => {
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "PRIVATE-CV-A secret unsaved edit" },
    });
    activeUser = "usr-b";
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
    expect(screen.queryByText(/Your edits were saved/)).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
  });

  it("rejects A's delayed successful draft save response when cookies now belong to B", async () => {
    const pending = deferred<{ workspace: ApplicationWorkspace }>();
    vi.mocked(api.editApplicationWorkspace).mockImplementationOnce(() => pending.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "PRIVATE-CV-A edited" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { pending.resolve({ workspace: { ...job("A"), cv_text: "PRIVATE-CV-A saved", revision: 2 } }); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/Your edits were saved/)).toBeNull();
    expect(screen.queryByText("PRIVATE-CV-A saved")).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
  });

  it("rejects even a failed old-user save without showing that failure under account B", async () => {
    const pending = deferred<{ workspace: ApplicationWorkspace }>();
    vi.mocked(api.editApplicationWorkspace).mockImplementationOnce(() => pending.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "PRIVATE-CV-A changed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { pending.reject(new Error("private A user-only server error")); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/private A user-only server error/)).toBeNull();
  });

  it("discards A's delayed AI suggestion after an account switch", async () => {
    const pending = deferred<Awaited<ReturnType<typeof api.requestLocalAISuggestions>>>();
    vi.mocked(api.requestLocalAISuggestions).mockImplementationOnce(() => pending.promise);
    vi.mocked(api.getLocalAIStatus).mockResolvedValue({
      configured: true, ready: true, provider: "local_obumai_ollama",
      model: "synthetic-fixture", external_ai_forwarding: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const suggest = screen.getByRole("button", { name: /Suggest tailored wording/ });
    await waitFor(() => expect(suggest.hasAttribute("disabled")).toBe(false));
    fireEvent.click(suggest);
    await waitFor(() => expect(api.requestLocalAISuggestions).toHaveBeenCalledWith("workspace-A", 1, "usr-a"));
    activeUser = "usr-b";
    await act(async () => {
      pending.resolve({
        workspace_revision: 1,
        suggestion: {
          provider: "local_obumai_ollama", model: "synthetic-private-A",
          approved_evidence_ids: [], external_actions_performed: false,
          suggestions_applied: false, requires_owner_review: true,
          proposal: {
            schema: "smartploy.local_draft.v1", cv_headline: "A-only resume",
            cv_summary: "PRIVATE-A-ONLY-SUMMARY", cover_letter: "PRIVATE-A-ONLY-LETTER",
            highlights: [], risks: [], review_notes: [],
          },
        },
      });
    });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-A-ONLY-SUMMARY")).toBeNull();
    expect(screen.queryByText(/Insert into editor/)).toBeNull();
  });

  it("never copies or renders the old account's delayed browser handoff packet", async () => {
    const pending = deferred<Awaited<ReturnType<typeof api.createBrowserHandoffPacket>>>();
    vi.mocked(api.createBrowserHandoffPacket).mockImplementationOnce(() => pending.promise);
    const copy = vi.fn(async (_s: string) => {});
    Object.defineProperty(navigator, "clipboard", {
      configurable: true, value: { writeText: copy },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const button = screen.getByRole("button", { name: /Copy approved autofill packet/ });
    await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(api.createBrowserHandoffPacket).toHaveBeenCalledWith("workspace-A", 1, "usr-a"));
    activeUser = "usr-b";
    await act(async () => {
      pending.resolve({ packet: {
        schema: "smartploy.browser_handoff.v2",
        workspace_id: "workspace-A",
        fields: { full_name: "PRIVATE-ACCOUNT-A-NAME" },
      } } as never);
    });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(copy).not.toHaveBeenCalled();
    expect(screen.queryByText(/PRIVATE-ACCOUNT-A-NAME/)).toBeNull();
    expect(screen.queryByRole("textbox", { name: /Select and copy the private/i })).toBeNull();
  });

  it("blocks a copied packet's delayed clipboard-completion message after account change", async () => {
    const pending = deferred<void>();
    const copy = vi.fn(() => pending.promise);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true, value: { writeText: copy },
    });
    vi.mocked(api.createBrowserHandoffPacket).mockResolvedValue({ packet: {
      schema: "smartploy.browser_handoff.v2",
      fields: { full_name: "PRIVATE-A" },
    } } as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const button = screen.getByRole("button", { name: /Copy approved autofill packet/ });
    await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(copy).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { pending.resolve(); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/Private packet copied/)).toBeNull();
    expect(screen.queryByText(/PRIVATE-A/)).toBeNull();
  });

  it("does not publish a delayed manually reported application state under B", async () => {
    const pending = deferred<Awaited<ReturnType<typeof api.markApplicationManuallySent>>>();
    vi.mocked(api.markApplicationManuallySent).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("FICTITIOUS-REFERENCE-A");
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /I applied on employer site/ }));
    await waitFor(() => expect(api.markApplicationManuallySent).toHaveBeenCalledWith(
      "workspace-A", 1, "FICTITIOUS-REFERENCE-A", "usr-a"
    ));
    activeUser = "usr-b";
    await act(async () => {
      pending.resolve({
        workspace: { ...job("A"), status: "self_reported_applied", revision: 2 },
        external_confirmation_verified: false,
      });
    });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/Recorded as personally reported applied/)).toBeNull();
    expect(screen.queryByText(/FICTITIOUS-REFERENCE-A/)).toBeNull();
  });

  it("does not show A's delayed draft deletion success under B", async () => {
    const pending = deferred<{ deleted: true }>();
    vi.mocked(api.deleteApplicationWorkspace).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Delete this application workspace/ }));
    await waitFor(() => expect(api.deleteApplicationWorkspace).toHaveBeenCalledWith("workspace-A", "usr-a"));
    activeUser = "usr-b";
    await act(async () => { pending.resolve({ deleted: true }); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/Draft removed from SmartPloy/)).toBeNull();
    expect(screen.queryByText("A private role")).toBeNull();
  });

  it("does not publish an old account's imported browser receipt", async () => {
    const pending = deferred<Awaited<ReturnType<typeof api.importBrowserReceipt>>>();
    vi.mocked(api.importBrowserReceipt).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Import observed receipt/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Paste receipt from the companion" }), {
      target: { value: JSON.stringify({
        schema: "smartploy.browser_receipt.v1", workspace_id: "workspace-A",
        document_revision: 1, confirmed_visible: true,
      }) },
    });
    fireEvent.click(screen.getByRole("button", { name: /Store observed confirmation/ }));
    await waitFor(() => expect(api.importBrowserReceipt).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { pending.resolve({ receipt: {
      workspace_id: "workspace-A", reference: "PRIVATE-A-RECEIPT", status: "browser_observed_unverified",
    } } as never); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByText(/PRIVATE-A-RECEIPT/)).toBeNull();
    expect(screen.queryByText(/Employer confirmation was recorded/)).toBeNull();
  });
});


describe("Application Studio per-draft result isolation", () => {
  const twoDrafts = () =>
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces: [job("A"), job("B")], count: 2,
    });

  function selectB() {
    fireEvent.click(screen.getByRole("button", { name: /B private role/ }));
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
  }

  it("binds one-click due-agent review to the original Studio OIDC identity", async () => {
    vi.mocked(api.getApplicationAgentInbox).mockResolvedValue({
      items: [inboxItem("A")], count: 1, has_more: false, next_offset: null,
      background_worker_verified: false, external_actions_authorized: false,
    });
    studio();
    const action = await screen.findByRole("button", {
      name: "Check due private agents (up to 10)",
    });
    fireEvent.click(action);
    await waitFor(() => expect(api.checkDueApplicationAgentInbox).toHaveBeenCalledTimes(1));
    expect(api.checkDueApplicationAgentInbox).toHaveBeenCalledWith("usr-a");
    expect(await screen.findByText(/No employer was contacted/)).toBeTruthy();
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("opens a prioritized agent-inbox item using the existing draft selection controls", async () => {
    twoDrafts();
    vi.mocked(api.getApplicationAgentInbox).mockResolvedValue({
      items: [inboxItem("B")], count: 1, has_more: false, next_offset: null,
      background_worker_verified: false, external_actions_authorized: false,
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const inbox = await screen.findByRole("region", { name: "Application agent inbox" });
    expect(inbox.textContent).toContain("Review due");
    fireEvent.click(screen.getByRole("button", {
      name: "Open B private role at Fictional Employer application",
    }));
    expect(await screen.findByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(api.getApplicationWorkspaceById).not.toHaveBeenCalled();
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("opens an older owned inbox case outside the first listing and keeps it on refresh", async () => {
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces: [job("A"), job("B")], count: 2,
    });
    vi.mocked(api.getApplicationWorkspaceById).mockResolvedValue({
      workspace: job("OLD"),
    });
    vi.mocked(api.getApplicationAgentInbox).mockResolvedValue({
      items: [inboxItem("OLD")], count: 1, has_more: false, next_offset: null,
      background_worker_verified: false, external_actions_authorized: false,
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const action = await screen.findByRole("button", {
      name: "Open OLD private role at Fictional Employer application",
    });
    fireEvent.click(action);
    await waitFor(() => expect(api.getApplicationWorkspaceById).toHaveBeenCalledWith(
      "workspace-OLD",
    ));
    expect(await screen.findByRole("heading", { name: "OLD private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(api.getApplicationWorkspaceById).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "OLD private role" })).toBeTruthy();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("keeps an older inbox case and current unsaved CV isolated across an account switch", async () => {
    const pending = deferred<{workspace:ApplicationWorkspace}>();
    vi.mocked(api.getApplicationWorkspaceById).mockReturnValue(pending.promise);
    vi.mocked(api.getApplicationAgentInbox).mockResolvedValue({
      items: [inboxItem("OLD")], count: 1, has_more: false, next_offset: null,
      background_worker_verified: false, external_actions_authorized: false,
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", {
      name: "Open OLD private role at Fictional Employer application",
    }));
    await waitFor(() => expect(api.getApplicationWorkspaceById).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";  // same email, different OIDC subject
    pending.resolve({ workspace: job("OLD") });
    expect(await screen.findByText(/signed-in SmartPloy account changed/i)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "OLD private role" })).toBeNull();
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("opens the next queued private draft and preserves the selected job across Refresh", async () => {
    twoDrafts();
    render(<ApplicationStudio focusId="workspace-A" expectedUserId="usr-a"
      expectedAuthSource="oidc" onFindJobs={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next application" }));
    expect(await screen.findByRole("heading", { name: "B private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-B");
    fireEvent.click(screen.getByRole("button", { name: "Refresh drafts" }));
    await waitFor(() => expect(api.getApplicationWorkspaces).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable cover letter text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-LETTER-B");
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("keeps unsaved application changes when Next is cancelled", async () => {
    twoDrafts();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "A-only unsaved corrections" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Next application" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved changes and open another draft?");
    expect(screen.getByRole("heading", { name: "A private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("A-only unsaved corrections");
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Next application" }));
    expect(await screen.findByRole("heading", { name: "B private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-B");
    expect(api.editApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("skips completed applications when advancing the saved-draft review queue", async () => {
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces: [job("A"), { ...job("B"), status: "provider_acknowledged" }, job("C")],
      count: 3,
    });
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const next = screen.getByRole("button", { name: "Next application" });
    expect(next.textContent).toContain("C private role");
    fireEvent.click(next);
    expect(await screen.findByRole("heading", { name: "C private role" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next application" }).textContent)
      .toContain("A private role");
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
  });

  it("does not switch from B back to A when A's saved draft completes", async () => {
    twoDrafts();
    const pending = deferred<{ workspace: ApplicationWorkspace }>();
    vi.mocked(api.editApplicationWorkspace).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "unsaved A-only text" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledTimes(1));
    selectB();
    await act(async () => {
      pending.resolve({ workspace: { ...job("A"), revision: 2, cv_text: "SAVED-A-ONLY" } });
    });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-B");
    expect(screen.queryByText(/Your edits were saved/)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Account verification required" })).toBeNull();
  });

  it("does not publish an A-only AI proposal in B's job draft", async () => {
    twoDrafts();
    const pending = deferred<Awaited<ReturnType<typeof api.requestLocalAISuggestions>>>();
    vi.mocked(api.requestLocalAISuggestions).mockImplementationOnce(() => pending.promise);
    vi.mocked(api.getLocalAIStatus).mockResolvedValue({
      configured: true, ready: true, provider: "local_obumai_ollama",
      model: "synthetic-model", external_ai_forwarding: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const suggest = screen.getByRole("button", { name: /Suggest tailored wording/ });
    await waitFor(() => expect(suggest.hasAttribute("disabled")).toBe(false));
    fireEvent.click(suggest);
    await waitFor(() => expect(api.requestLocalAISuggestions).toHaveBeenCalledWith(
      "workspace-A", 1, "usr-a"
    ));
    selectB();
    await act(async () => {
      pending.resolve({
        workspace_revision: 1,
        suggestion: {
          provider: "local_obumai_ollama", model: "synthetic",
          approved_evidence_ids: [], external_actions_performed: false,
          suggestions_applied: false, requires_owner_review: true,
          proposal: {
            schema: "smartploy.local_draft.v1", cv_headline: "A only",
            cv_summary: "A-ONLY-PRIVATE-AI-SUMMARY",
            cover_letter: "A-ONLY-PRIVATE-COVER-LETTER",
            highlights: [], risks: [], review_notes: [],
          },
        },
      });
    });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(screen.queryByText("A-ONLY-PRIVATE-AI-SUMMARY")).toBeNull();
    expect(screen.queryByRole("button", { name: /Insert into editor/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Account verification required" })).toBeNull();
  });

  it("does not copy an A-only browser packet after the user selects B", async () => {
    twoDrafts();
    const pending = deferred<Awaited<ReturnType<typeof api.createBrowserHandoffPacket>>>();
    vi.mocked(api.createBrowserHandoffPacket).mockImplementationOnce(() => pending.promise);
    const clipboardCopy = vi.fn(async (_s: string) => {});
    Object.defineProperty(navigator, "clipboard", {
      configurable: true, value: { writeText: clipboardCopy },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const copyButton = screen.getByRole("button", { name: /Copy approved autofill packet/ });
    await waitFor(() => expect(copyButton.hasAttribute("disabled")).toBe(false));
    fireEvent.click(copyButton);
    await waitFor(() => expect(api.createBrowserHandoffPacket).toHaveBeenCalledTimes(1));
    selectB();
    await act(async () => {
      pending.resolve({ packet: {
        schema: "smartploy.browser_handoff.v2",
        workspace_id: "workspace-A",
        fields: { full_name: "A-ONLY-PRIVATE-PACKET" },
      } } as never);
    });
    expect(clipboardCopy).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: /Select and copy the private/i })).toBeNull();
    expect(screen.queryByText(/Private packet copied/)).toBeNull();
  });

  it("does not publish A's pending receipt into B's receipt area", async () => {
    twoDrafts();
    const pending = deferred<Awaited<ReturnType<typeof api.importBrowserReceipt>>>();
    vi.mocked(api.importBrowserReceipt).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Import observed receipt/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Paste receipt from the companion" }), {
      target: { value: JSON.stringify({
        schema: "smartploy.browser_receipt.v1", workspace_id: "workspace-A",
        document_revision: 1, confirmed_visible: true,
      }) },
    });
    fireEvent.click(screen.getByRole("button", { name: /Store observed confirmation/ }));
    await waitFor(() => expect(api.importBrowserReceipt).toHaveBeenCalledTimes(1));
    selectB();
    await act(async () => { pending.resolve({ receipt: {
      workspace_id: "workspace-A", reference: "A-ONLY-RECEIPT",
      status: "browser_observed_unverified",
    } } as never); });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(screen.queryByText("A-ONLY-RECEIPT")).toBeNull();
    expect(screen.queryByText(/Employer confirmation was recorded/)).toBeNull();
    expect(screen.getByRole("button", { name: /Import observed receipt/ })).toBeTruthy();
  });

  it("does not publish A's manual application status after switching to B", async () => {
    twoDrafts();
    const pending = deferred<Awaited<ReturnType<typeof api.markApplicationManuallySent>>>();
    vi.mocked(api.markApplicationManuallySent).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("A-ONLY-REFERENCE");
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    // Wait for the selected draft's editor synchronization effect. The
    // first heading render can precede textarea hydration in React tests.
    await waitFor(() => {
      expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
        .toBe("PRIVATE-CV-A");
      expect((screen.getByRole("textbox", { name: "Editable cover letter text" }) as HTMLTextAreaElement).value)
        .toBe("PRIVATE-LETTER-A");
    });
    fireEvent.click(screen.getByRole("button", { name: /I applied on employer site/ }));
    await waitFor(() => expect(api.markApplicationManuallySent).toHaveBeenCalledTimes(1));
    selectB();
    await act(async () => { pending.resolve({
      workspace: { ...job("A"), revision: 2, status: "self_reported_applied" },
      external_confirmation_verified: false,
    }); });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(screen.queryByText(/Recorded as personally reported applied/)).toBeNull();
    expect(screen.queryByText("A-ONLY-REFERENCE")).toBeNull();
  });

  it("does not jump away from B when A's deletion finishes late", async () => {
    twoDrafts();
    const pending = deferred<{ deleted: true }>();
    vi.mocked(api.deleteApplicationWorkspace).mockImplementationOnce(() => pending.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Delete this application workspace/ }));
    await waitFor(() => expect(api.deleteApplicationWorkspace).toHaveBeenCalledWith(
      "workspace-A", "usr-a"
    ));
    selectB();
    await act(async () => { pending.resolve({ deleted: true }); });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect(screen.queryByText(/Draft removed from SmartPloy/)).toBeNull();
  });

  it("rejects A's AI insertion if the user switches to B during identity verification", async () => {
    twoDrafts();
    vi.mocked(api.getLocalAIStatus).mockResolvedValue({
      configured: true, ready: true, provider: "local_obumai_ollama",
      model: "synthetic", external_ai_forwarding: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const suggest = screen.getByRole("button", { name: /Suggest tailored wording/ });
    await waitFor(() => expect(suggest.hasAttribute("disabled")).toBe(false));
    fireEvent.click(suggest);
    expect(await screen.findByText(/Synthetic approved evidence/)).toBeTruthy();
    const verification = deferred<SessionInfo>();
    vi.mocked(api.getSession).mockImplementationOnce(() => verification.promise);
    fireEvent.click(screen.getByRole("button", { name: /Insert into editor/ }));
    await waitFor(() => expect(api.getSession).toHaveBeenCalled());
    selectB();
    await act(async () => { verification.resolve(session("usr-a")); });
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-CV-B");
    expect((screen.getByRole("textbox", { name: "Editable cover letter text" }) as HTMLTextAreaElement).value)
      .toBe("PRIVATE-LETTER-B");
  });
});


describe("Application Studio draft-scoped pending indicators", () => {
  const twoDrafts = () =>
    vi.mocked(api.getApplicationWorkspaces).mockResolvedValue({
      workspaces: [job("A"), job("B")], count: 2,
    });

  async function pickB() {
    fireEvent.click(screen.getByRole("button", { name: /B private role/ }));
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    await waitFor(() => {
      expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
        .toBe("PRIVATE-CV-B");
    });
  }

  it("unlocks Job B despite Job A's unfinished save and keeps B locked if A finishes first", async () => {
    twoDrafts();
    const oldSave = deferred<{ workspace: ApplicationWorkspace }>();
    const newSave = deferred<{ workspace: ApplicationWorkspace }>();
    vi.mocked(api.editApplicationWorkspace)
      .mockImplementationOnce(() => oldSave.promise)
      .mockImplementationOnce(() => newSave.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "A unsaved changes" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledWith(
      "workspace-A", 1, "A unsaved changes", "PRIVATE-LETTER-A", "usr-a"
    ));
    await pickB();
    fireEvent.change(screen.getByRole("textbox", { name: "Editable CV text" }), {
      target: { value: "B unsaved changes" },
    });
    const bSaveButton = screen.getByRole("button", { name: "Save changes" });
    expect(bSaveButton.hasAttribute("disabled")).toBe(false);
    fireEvent.click(bSaveButton);
    await waitFor(() => expect(api.editApplicationWorkspace).toHaveBeenCalledWith(
      "workspace-B", 1, "B unsaved changes", "PRIVATE-LETTER-B", "usr-a"
    ));
    expect(screen.getByRole("button", { name: "Working…" }).hasAttribute("disabled")).toBe(true);
    await act(async () => { oldSave.resolve({
      workspace: { ...job("A"), cv_text: "saved A", revision: 2 },
    }); });
    // A's finally block must not unlock B's still-pending save.
    expect(screen.getByRole("button", { name: "Working…" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
    await act(async () => { newSave.resolve({
      workspace: { ...job("B"), cv_text: "B unsaved changes", revision: 2 },
    }); });
    expect(await screen.findByText(/Your edits were saved/)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Editable CV text" }) as HTMLTextAreaElement).value)
      .toBe("B unsaved changes");
  });

  it("unlocks B's AI action while A is pending and does not clear B's new AI spinner", async () => {
    twoDrafts();
    vi.mocked(api.getLocalAIStatus).mockResolvedValue({
      configured: true, ready: true, provider: "local_obumai_ollama",
      model: "synthetic-only", external_ai_forwarding: false,
    });
    const oldAI = deferred<Awaited<ReturnType<typeof api.requestLocalAISuggestions>>>();
    const newAI = deferred<Awaited<ReturnType<typeof api.requestLocalAISuggestions>>>();
    vi.mocked(api.requestLocalAISuggestions)
      .mockImplementationOnce(() => oldAI.promise)
      .mockImplementationOnce(() => newAI.promise);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    const aButton = screen.getByRole("button", { name: /Suggest tailored wording/ });
    await waitFor(() => expect(aButton.hasAttribute("disabled")).toBe(false));
    fireEvent.click(aButton);
    await waitFor(() => expect(api.requestLocalAISuggestions).toHaveBeenCalledWith(
      "workspace-A", 1, "usr-a"
    ));
    await pickB();
    const bButton = screen.getByRole("button", { name: /Suggest tailored wording/ });
    expect(bButton.hasAttribute("disabled")).toBe(false);
    fireEvent.click(bButton);
    await waitFor(() => expect(api.requestLocalAISuggestions).toHaveBeenCalledWith(
      "workspace-B", 1, "usr-a"
    ));
    const suggestion = (tag: string): Awaited<ReturnType<typeof api.requestLocalAISuggestions>> => ({
      workspace_revision: 1,
      suggestion: {
        provider: "local_obumai_ollama", model: "synthetic-only",
        approved_evidence_ids: [], external_actions_performed: false,
        suggestions_applied: false, requires_owner_review: true,
        proposal: {
          schema: "smartploy.local_draft.v1", cv_headline: tag + " headline",
          cv_summary: tag + " summary", cover_letter: tag + " letter",
          highlights: [], risks: [], review_notes: [],
        },
      },
    });
    await act(async () => { oldAI.resolve(suggestion("A-ONLY")); });
    expect(screen.getByRole("button", { name: /Generating with the local model/ })
      .hasAttribute("disabled")).toBe(true);
    expect(screen.queryByText("A-ONLY summary")).toBeNull();
    await act(async () => { newAI.resolve(suggestion("B-ONLY")); });
    expect(await screen.findByText("B-ONLY summary")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Generating with the local model/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "B private role" })).toBeTruthy();
  });

  it("offers the first-party Chrome companion ZIP beside reviewed packet controls",async()=>{
    studio();
    expect(await screen.findByRole("heading",{name:"A private role"})).toBeTruthy();
    const link=screen.getByRole("link",{name:"Download Chrome companion ZIP from SmartPloy"});
    expect(link.getAttribute("href")).toBe("/smartploy-apply-companion.zip");
    expect(link.getAttribute("download")).toBe("smartploy-apply-companion.zip");
    expect(link.getAttribute("target")).toBeNull();
    expect(screen.getByText(/Desktop Chrome or Chromium: download and extract/)).toBeTruthy();
    expect(screen.getByText(/does not submit jobs in the background/)).toBeTruthy();
    expect(api.createBrowserHandoffPacket).not.toHaveBeenCalled();
    expect(api.sendLeverPartnerApplication).not.toHaveBeenCalled();
    expect(api.markApplicationManuallySent).not.toHaveBeenCalled();
  });

});
