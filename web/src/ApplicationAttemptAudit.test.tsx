// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import ApplicationAttemptAudit from "./ApplicationAttemptAudit";
import * as api from "./api";
import type { ApplicationWorkspace } from "./types";

vi.mock("./api", () => ({ getEmployerAttemptStatus: vi.fn() }));
const job = (id: string, revision = 1, status: ApplicationWorkspace["status"] = "draft") => ({
  workspace_id: id, revision, status,
  role_title: id + " planner", company: "Fictional Employer",
  updated_at: "2026-10-30T08:00:00Z", canonical_key: "fictional-" + id,
} as ApplicationWorkspace);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const noAttempt = {
  previous_attempt_reserved: false, state: "not_reserved",
  requires_human_reconciliation: false,
  automatic_employer_submit_authorized: false,
  external_confirmation_verified: false,
  cross_device_server_claim_required: true,
} as const;
const reserved = {
  ...noAttempt, previous_attempt_reserved: true, state: "uncertain",
  requires_human_reconciliation: true,
} as const;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getEmployerAttemptStatus).mockResolvedValue(noAttempt);
});
afterEach(() => cleanup());

describe("SP73 browser-only employer attempt audit", () => {
  it("does not read/send anything before the owner requests a bounded check", async () => {
    const verifyAccount = vi.fn().mockResolvedValue(undefined);
    const onOpen = vi.fn();
    render(<ApplicationAttemptAudit workspaces={[job("A"), job("B")]}
      verifyAccount={verifyAccount} onOpen={onOpen}/>);
    const audit = screen.getByRole("region", { name: "Previous employer attempt checks" });
    expect(audit.textContent).toContain("0 of 2 loaded private drafts checked");
    expect(api.getEmployerAttemptStatus).not.toHaveBeenCalled();
    expect(verifyAccount).not.toHaveBeenCalled();
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("flags reserved claims before a second employer attempt and opens exact existing job", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockImplementation(async (id) =>
      id === "A" ? reserved : noAttempt);
    const verifyAccount = vi.fn().mockResolvedValue(undefined);
    const onOpen = vi.fn();
    render(<ApplicationAttemptAudit workspaces={[job("A"), job("B")]}
      verifyAccount={verifyAccount} onOpen={onOpen}/>);
    fireEvent.click(screen.getByRole("button", { name: "Check next 2 draft attempts" }));
    const audit = screen.getByRole("region", { name: "Previous employer attempt checks" });
    await waitFor(() => expect(audit.textContent).toContain("2 of 2 loaded private drafts checked"));
    expect(audit.textContent).toContain("1 need previous-attempt reconciliation");
    expect(screen.getByText(/Do not submit these jobs again/i)).toBeTruthy();
    const review = screen.getByRole("button", {
      name: "Review A planner at Fictional Employer",
    });
    fireEvent.click(review);
    expect(onOpen).toHaveBeenCalledWith("A");
    expect(verifyAccount).toHaveBeenCalledTimes(4);
    const details = within(audit).getByText("View per-application attempt checks");
    fireEvent.click(details);
    expect(audit.textContent).toContain("Previous attempt reserved — review, never retry");
    expect(audit.textContent).toContain("No previous attempt recorded at check time — not send permission");
  });

  it("reports a failed attempt-status read as unverified and never safe to retry", async () => {
    vi.mocked(api.getEmployerAttemptStatus).mockRejectedValue(new Error("synthetic 503"));
    const verifyAccount = vi.fn().mockResolvedValue(undefined);
    render(<ApplicationAttemptAudit workspaces={[job("A")]}
      verifyAccount={verifyAccount} onOpen={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button", { name: "Check next 1 draft attempt" }));
    const audit = screen.getByRole("region", { name: "Previous employer attempt checks" });
    await waitFor(() => expect(audit.textContent).toContain("1 could not be verified"));
    expect(screen.getByRole("alert").textContent).toContain("Do not retry");
    fireEvent.click(screen.getByText("View per-application attempt checks"));
    expect(audit.textContent).toContain("Attempt status unavailable — do not retry");
    expect(screen.getByRole("button", { name: "Recheck 1 unavailable status" })).toBeTruthy();
  });

  it("does not publish an old account's claim after an OIDC switch", async () => {
    const pending = deferred<typeof reserved>();
    vi.mocked(api.getEmployerAttemptStatus).mockReturnValue(pending.promise);
    const verifyAccount = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValue(new Error("new account"));
    render(<ApplicationAttemptAudit workspaces={[job("A")]}
      verifyAccount={verifyAccount} onOpen={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button", { name: "Check next 1 draft attempt" }));
    await waitFor(() => expect(api.getEmployerAttemptStatus).toHaveBeenCalledWith("A"));
    await act(async () => pending.resolve(reserved));
    expect(screen.getByRole("region", { name: "Previous employer attempt checks" })
      .textContent).toContain("0 of 1 loaded private drafts checked");
    expect(screen.queryByText(/previously reserved employer attempt/i)).toBeNull();
  });

  it("cancels stale status when document revision changes during the original check", async () => {
    const pending = deferred<typeof noAttempt>();
    vi.mocked(api.getEmployerAttemptStatus).mockReturnValue(pending.promise);
    const verifyAccount = vi.fn().mockResolvedValue(undefined);
    const onOpen = vi.fn();
    const view = render(<ApplicationAttemptAudit workspaces={[job("A")]}
      verifyAccount={verifyAccount} onOpen={onOpen}/>);
    fireEvent.click(screen.getByRole("button", { name: "Check next 1 draft attempt" }));
    await waitFor(() => expect(api.getEmployerAttemptStatus).toHaveBeenCalledWith("A"));
    view.rerender(<ApplicationAttemptAudit workspaces={[job("A", 2)]}
      verifyAccount={verifyAccount} onOpen={onOpen}/>);
    await act(async () => pending.resolve(noAttempt));
    const audit = screen.getByRole("region", { name: "Previous employer attempt checks" });
    expect(audit.textContent).toContain("0 of 1 loaded private drafts checked");
    expect(audit.textContent).not.toContain("No previous attempt recorded");
  });

  it("never fetches more than ten draft statuses per explicit batch", async () => {
    const verifyAccount = vi.fn().mockResolvedValue(undefined);
    const workspaces = Array.from({ length: 12 }, (_, i) => job("A" + i));
    render(<ApplicationAttemptAudit workspaces={workspaces}
      verifyAccount={verifyAccount} onOpen={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button", { name: "Check next 10 draft attempts" }));
    await waitFor(() => expect(screen.getByRole("region", {
      name: "Previous employer attempt checks",
    }).textContent).toContain("10 of 12 loaded private drafts checked"));
    expect(api.getEmployerAttemptStatus).toHaveBeenCalledTimes(10);
    fireEvent.click(screen.getByRole("button", { name: "Check next 2 draft attempts" }));
    await waitFor(() => expect(screen.getByRole("region", {
      name: "Previous employer attempt checks",
    }).textContent).toContain("12 of 12 loaded private drafts checked"));
    expect(api.getEmployerAttemptStatus).toHaveBeenCalledTimes(12);
  });

  it("does not expose the check on an owner with no draft workspaces", () => {
    const verifyAccount = vi.fn();
    const view = render(<ApplicationAttemptAudit
      workspaces={[job("B", 1, "provider_acknowledged")]}
      verifyAccount={verifyAccount} onOpen={vi.fn()}/>);
    expect(view.container.firstChild).toBeNull();
    expect(api.getEmployerAttemptStatus).not.toHaveBeenCalled();
  });
});
