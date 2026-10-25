// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";

const USER = "usr-initiating-account-a";

function response(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
  } as Response;
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn(async () => response());
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("browser writes carry a stable initiating-account precondition", () => {
  it("sends the exact user ID for every browser-side mutation, including files and drafts", async () => {
    const cv = {
      name: "synthetic.pdf",
      size: 4,
      arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
    } as unknown as File;
    const changes: Array<() => Promise<unknown>> = [
      () => api.prepareJob("fictional-job", USER),
      () => api.uploadCV(cv, USER),
      () => api.deleteCV(USER),
      () => api.createFact("skill", "fictional", false, USER),
      () => api.approveFact("fact-fake", true, USER),
      () => api.deleteFact("fact-fake", USER),
      () => api.addManualJob({
        role_title: "Fictional Role", company: "Example Oy",
        location: "Helsinki", description: "Test", application_url: ""
      }, USER),
      () => api.deletePrivateSavedJob("saved-synthetic", USER),
      () => api.startApplicationWorkspace("fictional-job", USER),
      () => api.checkApplicationAgentNow("agent-synthetic-a", USER),
      () => api.checkDueApplicationAgentInbox(USER),
      () => api.editApplicationWorkspace("draft-fake", 1, "fictional cv", "fictional letter", USER),
      () => api.markApplicationManuallySent("draft-fake", 1, "fictional-ref", USER),
      () => api.deleteApplicationWorkspace("draft-fake", USER),
      () => api.requestLocalAISuggestions("draft-fake", 1, USER),
      () => api.createBrowserHandoffPacket("draft-fake", 1, USER),
      () => api.importBrowserReceipt("draft-fake", {
        schema: "smartploy.browser_receipt.v1",
        workspace_id: "draft-fake",
        document_revision: 1,
        confirmed_visible: true,
      } as never, USER),
      () => api.updateSearchPreferences({
        mode: "general", roles: [], locations: [], languages: [],
        work_modes: [], keywords: [], skills: [], seniority: "any",
        expected_revision: 0
      }, USER),
    ];

    for (const perform of changes) {
      await perform();
      const [url, init] = fetchSpy.mock.calls[fetchSpy.mock.calls.length - 1] as
        [string, RequestInit];
      expect(url).toContain("/api/");
      expect(["POST", "PUT", "PATCH", "DELETE"]).toContain(init.method);
      expect(init.headers).toMatchObject({
        "X-Smartploy-Expected-User-Id": USER,
      });
    }
    expect(fetchSpy).toHaveBeenCalledTimes(changes.length);
  });

  it("uses a first-party no-body POST with original expected user for ten-case inbox check", async () => {
    await api.checkDueApplicationAgentInbox(USER);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/application-agents/inbox/check-due");
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
    expect(init.headers).toMatchObject({
      "X-Smartploy-Expected-User-Id": USER,
    });
    await expect(api.checkDueApplicationAgentInbox("")).rejects.toThrow(
      /verified SmartPloy account/,
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("only creates a per-job agent after an explicit AutoApply selection", async () => {
    await api.startApplicationWorkspace("synthetic-job", USER);
    const [, manual] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(manual.body).toBeUndefined();

    await api.startApplicationWorkspace("synthetic-job", USER, true);
    const [url, automatic] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/api/v1/jobs/synthetic-job/application-workspace");
    expect(automatic.method).toBe("POST");
    expect(JSON.parse(String(automatic.body))).toEqual({
      start_private_agent: true,
      confirm_in_app_tracking_only: true,
    });
    expect(automatic.headers).toMatchObject({
      "X-Smartploy-Expected-User-Id": USER,
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("posts one owner-bound in-app check without employer data or outgoing payload", async () => {
    await api.checkApplicationAgentNow("agent-synthetic-a", USER);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/application-agents/agent-synthetic-a/check-now");
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
    expect(init.headers).toMatchObject({
      "X-Smartploy-Expected-User-Id": USER,
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await expect(api.checkApplicationAgentNow("agent-other", "")).rejects.toThrow(
      /verified SmartPloy account/
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("reads the paged case inbox and older workspace through private GETs only", async () => {
    await api.getApplicationAgentInbox(25, 50);
    const [inboxUrl, inboxOptions] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(inboxUrl).toContain("/api/v1/application-agents/inbox?limit=25&offset=50");
    expect(inboxOptions.method).toBeUndefined();
    expect(inboxOptions.headers).not.toHaveProperty("X-Smartploy-Expected-User-Id");

    await api.getApplicationWorkspaceById("kit-old/private");
    const [workspaceUrl, workspaceOptions] = fetchSpy.mock.calls[1] as
      [string, RequestInit];
    expect(workspaceUrl).toContain("/api/v1/application-workspaces/kit-old%2Fprivate");
    expect(workspaceOptions.method).toBeUndefined();
    expect(workspaceOptions.headers).not.toHaveProperty(
      "X-Smartploy-Expected-User-Id",
    );

    await expect(api.getApplicationAgentInbox(0, 0)).rejects.toThrow(/Invalid private agent inbox page/);
    await expect(api.getApplicationAgentInbox(25, -1)).rejects.toThrow(/Invalid private agent inbox page/);
    await expect(api.getApplicationAgentInbox(101, 0)).rejects.toThrow(/Invalid private agent inbox page/);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("fails closed before fetch when the initiating account is missing", async () => {
    await expect(api.deleteCV("")).rejects.toThrow(/verified SmartPloy account/);
    await expect(api.deleteCV("   ")).rejects.toThrow(/verified SmartPloy account/);
    await expect(api.startApplicationWorkspace("fictional-job", "")).rejects.toThrow(
      /verified SmartPloy account/
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("never treats a read request as an account write", async () => {
    await api.getSession();
    await api.getSearchPreferences();
    await api.getApplicationWorkspaces();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    for (const [, init] of fetchSpy.mock.calls as Array<[string, RequestInit]>) {
      expect(init.headers).not.toHaveProperty("X-Smartploy-Expected-User-Id");
    }
  });

  it("captures A's user ID in the outgoing request even if cookies are now B's", async () => {
    // The server-side OIDC/Cloudflare regression tests prove B rejects A's
    // expected user ID. This unit test ensures the HTTP client sends A, not
    // a late global account value, when a mutation dispatches.
    await api.createFact("skill", "synthetic text", false, USER);
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({
      "X-Smartploy-Expected-User-Id": "usr-initiating-account-a",
    });
  });
});
