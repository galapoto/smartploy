// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import ApplicationStudio from "./ApplicationStudio";
import type { ApplicationWorkspace, ApplicationWorkspacesResponse, SessionInfo } from "./types";

vi.mock("./api", () => ({
  getSession: vi.fn(),
  getApplicationWorkspaces: vi.fn(),
  getLocalAIStatus: vi.fn(),
  getBrowserHandoffReadiness: vi.fn(),
  getBrowserReceipt: vi.fn(),
  editApplicationWorkspace: vi.fn(),
  deleteApplicationWorkspace: vi.fn(),
  markApplicationManuallySent: vi.fn(),
  requestLocalAISuggestions: vi.fn(),
  createBrowserHandoffPacket: vi.fn(),
  importBrowserReceipt: vi.fn(),
  applicationDownloadUrl: vi.fn(() => "/synthetic-download"),
}));

function job(tag: string): ApplicationWorkspace {
  return {
    workspace_id: "workspace-" + tag, canonical_key: "fictional-" + tag,
    role_title: tag + " private role", company: "Fictional Employer",
    application_url: "https://example.invalid/job-" + tag,
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
  vi.mocked(api.editApplicationWorkspace).mockImplementation(async (_, __, cvText, coverLetterText) =>
    ({ workspace: { ...job("A"), cv_text: cvText, cover_letter_text: coverLetterText, revision: 2 } })
  );
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
        schema: "smartploy.browser_handoff.v1",
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
      schema: "smartploy.browser_handoff.v1",
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
    fireEvent.click(screen.getByRole("button", { name: /Delete this private draft/ }));
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
        schema: "smartploy.browser_handoff.v1",
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
    fireEvent.click(screen.getByRole("button", { name: /Delete this private draft/ }));
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
});
