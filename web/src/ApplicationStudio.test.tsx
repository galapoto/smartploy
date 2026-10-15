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
  vi.mocked(api.getBrowserReceipt).mockResolvedValue({ receipt: null });
});

afterEach(() => cleanup());

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
    const receipt = deferred<{ receipt: null }>();
    vi.mocked(api.getBrowserReceipt).mockImplementationOnce(() => receipt.promise);
    studio();
    expect(await screen.findByRole("heading", { name: "A private role" })).toBeTruthy();
    await waitFor(() => expect(api.getBrowserReceipt).toHaveBeenCalledTimes(1));
    activeUser = "usr-b";
    await act(async () => { receipt.resolve({ receipt: null }); });
    expect(await screen.findByRole("heading", { name: "Account verification required" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Editable CV text" })).toBeNull();
    expect(screen.queryByText("PRIVATE-LETTER-A")).toBeNull();
    expect(screen.queryByRole("button", { name: /copy approved autofill packet/i })).toBeNull();
  });
});
