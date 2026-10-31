// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReleaseStatus, { assessReleaseParity } from "./ReleaseStatus";

const A = "123456789abc";
const B = "abcdef123456";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mockManifest(revision = A) {
  const get = vi.fn().mockResolvedValue({
    ok: true,
    redirected: false,
    headers: {
      get: (name: string) => name === "content-type" ? "application/json" : null,
    },
    json: async () => ({ schema: "smartploy-web-release-v1", release_revision: revision }),
  });
  vi.stubGlobal("fetch", get);
  return get;
}

describe("SP90: in-app deployment provenance", () => {
  it("classifies exact three-way parity without treating it as GitHub freshness", () => {
    expect(assessReleaseParity(A, A, A)).toBe("aligned");
    expect(assessReleaseParity(A, B, B)).toBe("update_available");
    expect(assessReleaseParity(A, B, A)).toBe("mixed");
    expect(assessReleaseParity(A, undefined, A)).toBe("unverified");
    expect(assessReleaseParity(A, A, null)).toBe("unverified");
    expect(assessReleaseParity("dev", A, A)).toBe("development");
    expect(assessReleaseParity(A, A, undefined)).toBe("checking");
  });

  it("shows the deployed public revision when browser/static/API agree", async () => {
    const fetchMock = mockManifest();
    render(<ReleaseStatus buildRevision={A} apiRevision={A} />);
    expect(await screen.findByText(/UI and API match/)).toBeTruthy();
    expect(screen.getByText(A)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reload updated app" })).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith("/release.json", expect.objectContaining({
      method: "GET", cache: "no-store", credentials: "same-origin",
    }));
  });

  it("offers a manual reload, with unsaved-data warning, only for the newer matched web/API", async () => {
    mockManifest(B);
    const reload = vi.fn();
    render(<ReleaseStatus buildRevision={A} apiRevision={B} onReload={reload} />);
    const button = await screen.findByRole("button", { name: "Reload updated app" });
    expect(screen.getByText(/Save any unsaved CV or letter changes/)).toBeTruthy();
    expect(reload).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(reload).toHaveBeenCalledOnce();
  });

  it("keeps a mixed deployment explicit and refuses to advertise a simple refresh fix", async () => {
    mockManifest(A);
    render(<ReleaseStatus buildRevision={A} apiRevision={B} />);
    expect(await screen.findByText(/Release mismatch/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reload updated app" })).toBeNull();
  });

  it("does not claim parity against a legacy API lacking a release revision", async () => {
    mockManifest(A);
    render(<ReleaseStatus buildRevision={A} />);
    expect(await screen.findByText(/Running release cannot be verified/i)).toBeTruthy();
    expect(screen.queryByText(/UI and API match/)).toBeNull();
  });

  it("fails closed when the release route returns login HTML or an invalid schema", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, redirected: true,
      headers: { get: () => "text/html" },
    }));
    render(<ReleaseStatus buildRevision={A} apiRevision={A} />);
    expect(await screen.findByText(/Running release cannot be verified/i)).toBeTruthy();
    expect(screen.queryByText(/UI and API match/)).toBeNull();
  });

  it("fails closed on an invalid manifest even when the API matches", async () => {
    mockManifest("bad");
    render(<ReleaseStatus buildRevision={A} apiRevision={A} />);
    await waitFor(() => expect(screen.getByText(/Running release cannot be verified/i)).toBeTruthy());
  });

  it("does not imply a development preview is a production deployment", () => {
    mockManifest("dev");
    render(<ReleaseStatus buildRevision="dev" apiRevision={A} />);
    expect(screen.getByText(/Development preview/)).toBeTruthy();
  });
});
