// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as api from "./api";
import ApplicationAgentInbox from "./ApplicationAgentInbox";
import type {
  ApplicationAgentInboxItem, ApplicationAgentInboxPage,
} from "./types";

vi.mock("./api", () => ({ getApplicationAgentInbox: vi.fn() }));

const first: ApplicationAgentInboxItem = {
  agent_id: "agent-A", workspace_id: "workspace-A", canonical_key: "fictional-A",
  role_title: "Junior QA Tester", company: "Fictional Company A",
  state: "active", revision: 1, next_due_at: "2026-10-24T10:00:00Z",
  last_woke_at: "", created_at: "2026-10-20T12:00:00Z",
  updated_at: "2026-10-20T12:00:00Z", closed_at: "", close_reason: "",
  milestone: "none", milestone_source: "none", workspace_status: "draft",
  observed_workspace_status: "draft", followups_sent: 0, last_followup_at: "",
  followup_suggestion: "", external_actions_authorized: false,
  employer_contacted: false, notification_channel: "in_app_only",
  attention_state: "due_review",
};
const other: ApplicationAgentInboxItem = {
  ...first, agent_id: "agent-B", workspace_id: "workspace-B",
  role_title: "Junior Data Analyst", company: "Fictional Company B",
  attention_state: "awaiting_response",
  workspace_status: "self_reported_applied",
  observed_workspace_status: "self_reported_applied",
};
function page(
  items: ApplicationAgentInboxItem[], more = false, offset: number | null = null,
): ApplicationAgentInboxPage {
  return {
    items, count: items.length, has_more: more, next_offset: offset,
    background_worker_verified: false, external_actions_authorized: false,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getApplicationAgentInbox).mockResolvedValue(page([first]));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("SP35 owner-scoped agent action inbox", () => {
  it("shows the server-prioritized due case and opens its original workspace", async () => {
    const verifyAccount = vi.fn(async () => undefined);
    const onOpen = vi.fn();
    render(<ApplicationAgentInbox verifyAccount={verifyAccount} onOpen={onOpen}/>);
    const action = await screen.findByRole("button", {
      name: "Open Junior QA Tester at Fictional Company A application",
    });
    expect(screen.getByText("Review due · private reminder only")).toBeTruthy();
    expect(screen.getByText(/Background worker activation has not been verified/)).toBeTruthy();
    expect(screen.getByText(/not an employer inbox/i)).toBeTruthy();
    expect(api.getApplicationAgentInbox).toHaveBeenCalledWith(25, 0);
    expect(verifyAccount).toHaveBeenCalledTimes(2);
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(action);
    expect(onOpen).toHaveBeenCalledWith("workspace-A");
    expect(screen.queryByRole("button", { name: /submit/i })).toBeNull();
  });

  it("paginates the original owner-only queue and reload resets stale entries", async () => {
    vi.mocked(api.getApplicationAgentInbox).mockImplementation(
      async (_limit, offset) => offset === 25
        ? page([other], false, null)
        : page([first], true, 25),
    );
    const verify = vi.fn(async () => undefined);
    render(<ApplicationAgentInbox verifyAccount={verify} onOpen={vi.fn()}/>);
    expect(await screen.findByText("Junior QA Tester · Fictional Company A")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Load more application agents/i }));
    expect(await screen.findByText("Junior Data Analyst · Fictional Company B")).toBeTruthy();
    expect(screen.getByText(/personally reported sent, not employer-verified/)).toBeTruthy();
    expect(api.getApplicationAgentInbox).toHaveBeenCalledWith(25, 25);
    expect(screen.queryByRole("button", { name: /Load more application agents/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Refresh agent inbox/i }));
    await waitFor(() => expect(api.getApplicationAgentInbox).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByText(
      "Junior Data Analyst · Fictional Company B",
    )).toBeNull());
    expect(screen.getByText("Junior QA Tester · Fictional Company A")).toBeTruthy();
  });

  it("does not publish an old account's cases when identity changes during a GET", async () => {
    const pending = deferred<ApplicationAgentInboxPage>();
    vi.mocked(api.getApplicationAgentInbox).mockReturnValue(pending.promise);
    const verify = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValue(new Error("Different OIDC subject"));
    const onOpen = vi.fn();
    render(<ApplicationAgentInbox verifyAccount={verify} onOpen={onOpen}/>);
    await waitFor(() => expect(api.getApplicationAgentInbox).toHaveBeenCalledTimes(1));
    pending.resolve(page([first]));
    await waitFor(() => expect(verify).toHaveBeenCalledTimes(3));
    expect(screen.queryByText("Junior QA Tester · Fictional Company A")).toBeNull();
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("does not conflate failed agent storage with an empty inbox", async () => {
    vi.mocked(api.getApplicationAgentInbox).mockRejectedValue(
      new Error("Application agent inbox unavailable"),
    );
    render(<ApplicationAgentInbox verifyAccount={vi.fn(async () => {})}
      onOpen={vi.fn()}/>);
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent", "Application agent inbox unavailable",
    );
    expect(screen.queryByText(/No tracked application agents yet/)).toBeNull();
  });

  it("states when no private case exists without claiming an employer send", async () => {
    vi.mocked(api.getApplicationAgentInbox).mockResolvedValue(page([]));
    render(<ApplicationAgentInbox verifyAccount={vi.fn(async () => {})}
      onOpen={vi.fn()}/>);
    expect(await screen.findByText(/No tracked application agents yet/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /open.*application/i })).toBeNull();
  });
});
