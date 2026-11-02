// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://smartploy.komplyint.fi/"}
/** SP111: real UI interactions, fake loopback service, no network/employers. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { getBrowserHandoffReadiness, getSession } from "./api";
import LocalPlaywrightAssist from "./LocalPlaywrightAssist";
import { localBridgeOriginAllowed } from "./localPlaywrightBridge";

vi.mock("./api", () => ({ getSession: vi.fn(), getBrowserHandoffReadiness: vi.fn() }));

const pairing = "synthetic-review-only-pairing-code";
const localToken = "L".repeat(43);
const planId = "P".repeat(22);
const packet = JSON.stringify({
  schema: "smartploy.browser_handoff.v2",
  workspace_id: "workspace-A", revision: 2,
  cv_pdf_sha256: "a".repeat(64), cv_pdf_size: 33,
  company: "Synthetic Employer", role_title: "QA Engineer",
  application_url: "https://jobs.lever.co/example/role",
  fields: { full_name: "Private Applicant", email: "private@example.invalid" },
});
const session = {
  authenticated: true, user_id: "user-A", profile_id: "profile-A",
  auth_source: "oidc", email: "same@example.invalid",
};

function mockReply(stage: "opened" | "inspected" | "filled" | "attached" | "stopped") {
  const values = {
    opened: {
      ok: true, stage: "opened", token: localToken,
      company: "Synthetic Employer", role_title: "QA Engineer",
      submitted: false, uploaded: false,
    },
    inspected: {
      ok: true, stage: "inspected", plan_id: planId, total_controls: 3,
      approved_fields: [{ key: "full_name", label: "Full Name" },
        { key: "email", label: "Email" }],
      cv_attachment: { available: true, label: "Résumé", attach_id: "Q".repeat(22) },
      submitted: false, uploaded: false,
    },
    filled: {
      ok: true, stage: "filled", filled: 2, planned: 2,
      stopped_on_change: false, submitted: false, uploaded: false,
    },
    attached: { ok: true, stage: "attached",
      attached_locally: true, employer_upload_confirmed: false,
      submitted: false, uploaded: true },
    stopped: { ok: true, stage: "stopped", submitted: false, uploaded: false },
  };
  return { ok: true, status: 200, json: async () => values[stage] };
}

const component = (enabled = true) => render(<LocalPlaywrightAssist
  packetText={packet} enabled={enabled}
  expectedUserId="user-A" expectedAuthSource="oidc"
  expectedWorkspaceId="workspace-A" expectedRevision={2}
/>);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getSession).mockResolvedValue(session);
  vi.mocked(getBrowserHandoffReadiness).mockResolvedValue({
    ready: true, document_revision: 2, blockers: [],
    contact_fields_ready: true, employer_submission_performed: false,
    will_require_manual_review: true, files_attached: false,
  });
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/v1/prepare")) return mockReply("opened");
    if (url.endsWith("/v1/inspect")) return mockReply("inspected");
    if (url.endsWith("/v1/fill")) return mockReply("filled");
    if (url.endsWith("/v1/attach")) return mockReply("attached");
    if (url.endsWith("/v1/stop")) return mockReply("stopped");
    throw new Error("Unexpected route");
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("SP111 paired browser review-first UI", () => {
  it("only approved origins can connect, no hidden GET or unrelated website", () => {
    expect(localBridgeOriginAllowed("https://smartploy.komplyint.fi")).toBe(true);
    expect(localBridgeOriginAllowed("https://smartploy.obumai.com")).toBe(true);
    expect(localBridgeOriginAllowed("https://evil.invalid")).toBe(false);
    expect(localBridgeOriginAllowed("http://localhost:3000")).toBe(false);
    component();
    expect(screen.getByRole("region", { name: "Paired local Playwright browser" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open reviewed employer form" })
      .hasAttribute("disabled")).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("pairs only with explicit consent, previews safe fields and fills once", async () => {
    component();
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open reviewed employer form" }));
    expect(await screen.findByRole("button", { name: "Inspect current employer form" })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, args] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:48741/v1/prepare");
    expect(args.method).toBe("POST");
    expect(args.credentials).toBe("omit");
    expect(args.redirect).toBe("error");
    expect(args.referrerPolicy).toBe("no-referrer");
    expect((args as RequestInit & { targetAddressSpace: "loopback" }).targetAddressSpace)
      .toBe("loopback");
    expect(args.headers).not.toHaveProperty("Authorization");
    expect(JSON.parse(String(args.body))).toEqual({ pairing_code: pairing, packet: JSON.parse(packet) });
    expect(document.body.textContent).not.toContain("private@example.invalid");
    expect(document.body.textContent).not.toContain(localToken);
    expect(document.body.textContent).not.toContain(pairing);

    fireEvent.click(screen.getByRole("button", { name: "Inspect current employer form" }));
    expect(await screen.findByText("Full Name")).toBeTruthy();
    expect(screen.getByText("Email")).toBeTruthy();
    expect(screen.getByRole("button", {name:"Attach exact saved CV PDF once"})).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2);
    const inspected = vi.mocked(fetch).mock.calls[1] as [string, RequestInit];
    expect(inspected[0]).toBe("http://127.0.0.1:48741/v1/inspect");
    expect((inspected[1].headers as Record<string, string>).Authorization).toBe(
      "Bearer " + localToken
    );
    expect(screen.getByRole("button", { name: "Fill reviewed fields once (never submit)" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Fill reviewed fields once (never submit)" }));
    expect(await screen.findByText(/Field-fill action completed/)).toBeTruthy();
    const filled = vi.mocked(fetch).mock.calls[2] as [string, RequestInit];
    expect(filled[0]).toBe("http://127.0.0.1:48741/v1/fill");
    expect(JSON.parse(String(filled[1].body))).toEqual({
      plan_id: planId, confirmation: "FILL REVIEWED FIELDS",
    });
    expect(screen.queryByRole("button", {
      name: "Fill reviewed fields once (never submit)",
    })).toBeNull();
    expect(screen.getByText(/application is NOT submitted/)).toBeTruthy();
    expect(window.confirm).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Stop local browser session" }));
    expect(await screen.findByText(/Restart the helper for another job/)).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(4);
    expect((vi.mocked(fetch).mock.calls[3][0] as string).endsWith("/v1/stop")).toBe(true);
  });

  it("blocks cross-account login changes before any local data transfer", async () => {
    vi.mocked(getSession).mockResolvedValue({ ...session, user_id: "different-subject" });
    component();
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open reviewed employer form" }));
    const errors = await screen.findAllByRole("alert");
    expect(errors.some((node) => node.textContent?.includes("sign-in changed"))).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps unsafe/unsaved applications disabled without local requests", () => {
    component(false);
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    const button = screen.getByRole("button", { name: "Open reviewed employer form" });
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(fetch).not.toHaveBeenCalled();
  });


  it("rejects stale application revisions before sending to the helper", async () => {
    vi.mocked(getBrowserHandoffReadiness).mockResolvedValue({
      ready: false, document_revision: 3,
      blockers: ["CV changed in another tab"],
      contact_fields_ready: true, employer_submission_performed: false,
      will_require_manual_review: true, files_attached: false,
    });
    component();
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open reviewed employer form" }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("CV/letter changed"))).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
    expect(getBrowserHandoffReadiness).toHaveBeenCalledWith("workspace-A");
  });

  it("fails closed on local-network denial; no fallback sends applicant data elsewhere", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("local network blocked"); }));
    component();
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open reviewed employer form" }));
    const errors = await screen.findAllByRole("alert");
    expect(errors.some((node) => node.textContent?.includes("local-network permission denied"))).toBe(true);
    expect(vi.mocked(fetch).mock.calls.every((call) =>
      String(call[0]).startsWith("http://127.0.0.1:48741/")
    )).toBe(true);
    expect(screen.queryByRole("button", { name: "Inspect current employer form" })).toBeNull();
  });

  it("SP112 attaches the saved exact PDF only after separate confirmation", async () => {
    const pdf = new TextEncoder().encode("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");
    const digest = new Uint8Array(32).fill(0xaa);
    const sha = "aa".repeat(32);
    vi.mocked(getBrowserHandoffReadiness).mockResolvedValue({
      ready: true, document_revision: 2, blockers: [],
      contact_fields_ready: true, employer_submission_performed: false,
      will_require_manual_review: true, files_attached: false,
    });
    const fromServer = packet.replace('"cv_pdf_sha256":"'+ "a".repeat(64) + '"',
       '"cv_pdf_sha256":"' + sha + '"').replace('"cv_pdf_size":33',
       '"cv_pdf_size":' + pdf.byteLength);
    // The packet is synthetic. The digest function is deterministic only in
    // this unit test: real Chromium uses the browser's native SubtleCrypto.
    Object.defineProperty(window.crypto, "subtle", {
      configurable: true, value: { digest: vi.fn(async () => digest.buffer) },
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/download/cv/pdf")) return {
        ok: true, status: 200, headers: { get: () => String(pdf.length) },
        arrayBuffer: async () => pdf.buffer,
      };
      if (url.endsWith("/v1/prepare")) return mockReply("opened");
      if (url.endsWith("/v1/inspect")) return mockReply("inspected");
      if (url.endsWith("/v1/attach")) return mockReply("attached");
      if (url.endsWith("/v1/stop")) return mockReply("stopped");
      throw new Error("Unexpected route");
    }));
    const ui = render(<LocalPlaywrightAssist
      packetText={fromServer} enabled={true}
      expectedUserId="user-A" expectedAuthSource="oidc"
      expectedWorkspaceId="workspace-A" expectedRevision={2}
    />);
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: {value: pairing},
    });
    fireEvent.click(screen.getByRole("button",{name:"Open reviewed employer form"}));
    await screen.findByRole("button",{name:"Inspect current employer form"});
    fireEvent.click(screen.getByRole("button",{name:"Inspect current employer form"}));
    const attach = await screen.findByRole("button",{name:"Attach exact saved CV PDF once"});
    expect(attach.hasAttribute("disabled")).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(2);
    fireEvent.click(attach);
    expect(await screen.findByText(/CV placed in the employer file input/)).toBeTruthy();
    const urls = vi.mocked(fetch).mock.calls.map(c=>String(c[0]));
    expect(urls.filter(u=>u.includes("/download/cv/pdf"))).toHaveLength(1);
    expect(urls.filter(u=>u.endsWith("/v1/attach"))).toHaveLength(1);
    const pdfReq = vi.mocked(fetch).mock.calls.find(c=>String(c[0]).endsWith("/v1/attach"))!;
    const init = pdfReq[1] as RequestInit & {targetAddressSpace:string};
    expect(init.targetAddressSpace).toBe("loopback");
    expect(init.credentials).toBe("omit");
    expect(init.redirect).toBe("error");
    expect(init.body).toEqual(pdf.buffer);
    expect((init.headers as Record<string,string>)["X-Smartploy-Attach-Confirmation"])
      .toBe("ATTACH REVIEWED CV");
    expect(screen.getByRole("button",{name:"Attach exact saved CV PDF once"})
      .hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/server acceptance is/)).toBeTruthy();
    expect(urls.every(u=>u.startsWith("http://127.0.0.1:48741/") ||
      u.includes("/api/v1/application-workspaces/"))).toBe(true);
    expect(ui.container.textContent).not.toContain("private@example.invalid");
    expect(window.confirm).toHaveBeenCalledTimes(2);
  });

  it("never retries a fill whose browser outcome is uncertain", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/v1/fill")) throw new Error("network disconnected after input");
      if (url.endsWith("/v1/prepare")) return mockReply("opened");
      if (url.endsWith("/v1/inspect")) return mockReply("inspected");
      if (url.endsWith("/v1/stop")) return mockReply("stopped");
      throw new Error("Unexpected route");
    }));
    component();
    fireEvent.change(screen.getByLabelText("Temporary local pairing code"), {
      target: { value: pairing },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open reviewed employer form" }));
    await screen.findByRole("button", { name: "Inspect current employer form" });
    fireEvent.click(screen.getByRole("button", { name: "Inspect current employer form" }));
    await screen.findByRole("button", { name: "Fill reviewed fields once (never submit)" });
    fireEvent.click(screen.getByRole("button", { name: "Fill reviewed fields once (never submit)" }));
    expect(await screen.findByText(/The fill attempt may have changed/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/Local helper unavailable or local-network permission denied/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Fill reviewed fields once (never submit)" })).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(3);
  });
});
