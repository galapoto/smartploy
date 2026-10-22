// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ApplicationAgentCard from "./ApplicationAgentCard";
import * as api from "./api";
import type { ApplicationAgent } from "./types";

vi.mock("./api", () => ({
  getApplicationAgents: vi.fn(),
  getApplicationAgent: vi.fn(),
  createApplicationAgent: vi.fn(),
  changeApplicationAgent: vi.fn(),
}));

const caseAgent: ApplicationAgent = {
  agent_id: "agent-fixture-a", workspace_id: "workspace-A",
  canonical_key: "synthetic-job", role_title: "Junior QA", company: "Example Oy",
  state: "active", revision: 1, next_due_at: "2026-10-22T14:00:00Z",
  last_woke_at: "", created_at: "2026-10-22T14:00:00Z",
  updated_at: "2026-10-22T14:00:00Z", closed_at: "", close_reason: "",
  external_actions_authorized: false, employer_contacted: false,
  notification_channel: "in_app_only",
};

const response = (agents: ApplicationAgent[]) => ({
  agents, count: agents.length, external_actions_authorized: false as const,
});

const events = [{
  sequence: 1, event_type: "case_created" as const,
  occurred_at: "2026-10-22T14:00:00Z",
  message: "A private application agent was created.",
  external_actions_performed: 0 as const,
}];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getApplicationAgents).mockResolvedValue(response([]));
  vi.mocked(api.getApplicationAgent).mockResolvedValue({
    agent: caseAgent, events, count: 1, next_cursor: 1,
    external_actions_authorized: false,
  });
  vi.mocked(api.createApplicationAgent).mockResolvedValue({
    agent: caseAgent, created: true, external_actions_performed: 0,
  });
  vi.mocked(api.changeApplicationAgent).mockResolvedValue({
    agent: { ...caseAgent, state: "paused", revision: 2 },
    external_actions_performed: 0,
  });
});
afterEach(cleanup);

describe("Agent Zero in the existing application studio", () => {
  it("creates one case on explicit click without dispatching an employer action", async () => {
    vi.mocked(api.getApplicationAgents)
      .mockResolvedValueOnce(response([]))
      .mockResolvedValue(response([caseAgent]));
    const verifyAccount = vi.fn(async () => {});
    render(<ApplicationAgentCard workspaceId="workspace-A"
      expectedUserId="user-a" verifyAccount={verifyAccount}/>);
    fireEvent.click(await screen.findByRole("button", {
      name: /start tracking this application/i,
    }));
    await waitFor(() => expect(api.createApplicationAgent).toHaveBeenCalledWith(
      "workspace-A", "user-a"
    ));
    expect(await screen.findByText(/A private application agent was created/)).toBeTruthy();
    expect(api.getApplicationAgent).toHaveBeenCalledWith("agent-fixture-a");
    const card = screen.getByLabelText("Your job application agent");
    expect(card.textContent).toContain("No emails, calls or employer applications");
    expect(card.textContent).toContain("model calls and external actions are disabled");
    expect(verifyAccount).toHaveBeenCalled();
  });

  it("sends one expected-revision pause, never a silent employer message", async () => {
    vi.mocked(api.getApplicationAgents).mockResolvedValue(response([caseAgent]));
    const verifyAccount = vi.fn(async () => {});
    render(<ApplicationAgentCard workspaceId="workspace-A"
      expectedUserId="user-a" verifyAccount={verifyAccount}/>);
    fireEvent.click(await screen.findByRole("button", { name: /^pause$/i }));
    await waitFor(() => expect(api.changeApplicationAgent).toHaveBeenCalledWith(
      "agent-fixture-a", "pause", 1, "user-a"
    ));
    expect(api.createApplicationAgent).not.toHaveBeenCalled();
  });

  it("does not dispatch a mutation when identity verification fails", async () => {
    const verifyAccount = vi.fn(async () => {});
    render(<ApplicationAgentCard workspaceId="workspace-A"
      expectedUserId="user-a" verifyAccount={verifyAccount}/>);
    const button = await screen.findByRole("button", {
      name: /start tracking this application/i,
    });
    verifyAccount.mockRejectedValueOnce(new Error("Signed-in account changed"));
    fireEvent.click(button);
    await screen.findByRole("alert");
    expect(api.createApplicationAgent).not.toHaveBeenCalled();
  });

  it("fails closed when durable application agent storage is unavailable", async () => {
    vi.mocked(api.getApplicationAgents).mockRejectedValueOnce(
      new Error("No migrated PostgreSQL agent ledger")
    );
    render(<ApplicationAgentCard workspaceId="workspace-A"
      expectedUserId="user-a" verifyAccount={vi.fn(async () => {})}/>);
    expect(await screen.findByText(/Agent tracking requires the durable-agent/i)).toBeTruthy();
    expect(screen.queryByRole("button", {
      name: /start tracking this application/i,
    })).toBeNull();
  });
});
