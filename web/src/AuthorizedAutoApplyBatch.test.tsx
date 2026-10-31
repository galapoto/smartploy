// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as api from "./api";
import AuthorizedAutoApplyBatch from "./AuthorizedAutoApplyBatch";
import type { ApplicationWorkspace } from "./types";
vi.mock("./api", () => ({
  getLeverPartnerReadiness: vi.fn(),
  getAshbyPartnerReadiness: vi.fn(),
  submitAuthorizedAutoApplyBatch: vi.fn(),
}));
const h = (s: string) => s.repeat(64);
const workspace: ApplicationWorkspace = {
  workspace_id:"test-workspace",canonical_key:"test-key",role_title:"Test Data Analyst",
  company:"Test Company",application_url:"https://jobs.lever.co/testorg/job-one",
  cv_text:"Reviewed test CV",cover_letter_text:"Reviewed test letter",
  source_cv_sha256:h("a"),approved_evidence_ids:[],
  revision:2,status:"draft",self_reported_applied_at:"",self_reported_reference:"",
  created_at:"",updated_at:"",
  authority:{may_edit:true,may_download:true,may_submit_to_employer:false,
    has_external_submission_proof:false},
};
const evidence = {
  workspace_id:"test-workspace",revision:2,document_sha256:h("b"),
  cv_pdf_sha256:h("c"),approved_fields_sha256:h("d"),
  cv_pdf_size:2048,expires_at:"2099-01-01T00:00:00Z",
};
const eligible = {
  partner_provider:"lever" as const,partner_api_configured:true,
  independent_partner_rights_reviewed:true,current_applicant_review_recorded:true,
  current_document_and_posting_ready:true,prior_employer_attempt:false,
  provider_acknowledged:false,eligible_for_explicit_partner_submit:true,
  review_evidence:evidence,review_evidence_is_authorization:false as const,
  unattended_auto_apply_enabled:false as const,automatic_retry_authorized:false as const,
};
const result = {
  results:[{workspace_id:"test-workspace",provider:"lever" as const,
    state:"provider_acknowledged" as const,provider_application_id:"fixture-ack"}],
  selected_count:1,attempted_count:1,provider_acknowledged_count:1,
  unattempted_count:0,stopped:false,stop_reason:"",
  unattended_auto_apply_enabled:false as const,automatic_retry_authorized:false as const,
};
const verify = vi.fn(async () => undefined);
const finished = vi.fn();
function start(draft = workspace, dirty = false) {
  return render(<AuthorizedAutoApplyBatch workspaces={[draft]}
    expectedUserId="test-user" verifyAccount={verify}
    providerForUrl={(url) => url.includes("lever.co") ? "lever" : null}
    hasUnsavedEdits={dirty} onOpen={vi.fn()} onCompleted={finished}/>);
}
beforeEach(() => {
  vi.resetAllMocks();
  verify.mockResolvedValue(undefined);
  vi.mocked(api.getLeverPartnerReadiness).mockResolvedValue(eligible);
  vi.mocked(api.submitAuthorizedAutoApplyBatch).mockResolvedValue(result);
  vi.spyOn(window,"confirm").mockReturnValue(true);
});
afterEach(() => { cleanup();vi.restoreAllMocks(); });
describe("SP86 approved AutoApply batch", () => {
  it("requires exact reviewed jobs and two applicant approvals before posting",async () => {
    start();
    fireEvent.click(screen.getByRole("button",{name:/Check eligible reviewed jobs/}));
    fireEvent.click(await screen.findByRole("checkbox"));
    const button = screen.getByRole("button",{name:/Approve and AutoApply to 1 employer/}) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I personally reviewed each selected job/));
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I authorize one real application submission/));
    fireEvent.click(button);
    await waitFor(() => expect(api.submitAuthorizedAutoApplyBatch).toHaveBeenCalledWith([{
      workspace_id:"test-workspace",provider:"lever",expected_revision:2,
      expected_document_sha256:h("b"),expected_cv_pdf_sha256:h("c"),
      expected_fields_sha256:h("d"),expected_cv_pdf_size:2048,
    }],"test-user"));
    expect(finished).toHaveBeenCalledWith(result);
  });
  it("never submits if employer rights are missing",async () => {
    vi.mocked(api.getLeverPartnerReadiness).mockResolvedValue({
      ...eligible,independent_partner_rights_reviewed:false,
      eligible_for_explicit_partner_submit:false,review_evidence:null,
    });
    start();
    fireEvent.click(screen.getByRole("button",{name:/Check eligible reviewed jobs/}));
    expect(await screen.findByText(/No separately authorized employer API integration/)).toBeTruthy();
    expect(api.submitAuthorizedAutoApplyBatch).not.toHaveBeenCalled();
  });
  it("requires an actual document save before first-draft handoff",async () => {
    start({...workspace,revision:1});
    fireEvent.click(screen.getByRole("button",{name:/Check eligible reviewed jobs/}));
    expect(await screen.findByText(/save your reviewed CV and letter first/)).toBeTruthy();
    expect(api.getLeverPartnerReadiness).not.toHaveBeenCalled();
  });
  it("fails closed when document hashes change before POST",async () => {
    vi.mocked(api.getLeverPartnerReadiness)
      .mockResolvedValueOnce(eligible)
      .mockResolvedValueOnce({...eligible,review_evidence:{
        ...evidence,document_sha256:h("f"),
      }});
    start();
    fireEvent.click(screen.getByRole("button",{name:/Check eligible reviewed jobs/}));
    fireEvent.click(await screen.findByRole("checkbox"));
    fireEvent.click(screen.getByLabelText(/I personally reviewed each selected job/));
    fireEvent.click(screen.getByLabelText(/I authorize one real application submission/));
    fireEvent.click(screen.getByRole("button",{name:/Approve and AutoApply to 1 employer/}));
    expect(await screen.findByText(/A selected employer job or review changed/)).toBeTruthy();
    expect(api.submitAuthorizedAutoApplyBatch).not.toHaveBeenCalled();
  });
  it("requires verified account before any partner read",async () => {
    verify.mockRejectedValue(new Error("different subject"));
    start();
    fireEvent.click(screen.getByRole("button",{name:/Check eligible reviewed jobs/}));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(api.getLeverPartnerReadiness).not.toHaveBeenCalled();
    expect(api.submitAuthorizedAutoApplyBatch).not.toHaveBeenCalled();
  });
});
