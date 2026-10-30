import { describe, expect, it } from "vitest";
import { summarizeApplicationReviewQueue } from "./applicationReviewQueue";
import type { ApplicationWorkspace } from "./types";

const example = (status: ApplicationWorkspace["status"], id: string) => ({
  workspace_id: id, status,
} as ApplicationWorkspace);

describe("SP72 owner-loaded application review queue", () => {
  const workspaces = [
    example("draft", "draft-1"),
    example("self_reported_applied", "reported-1"),
    example("draft", "draft-2"),
    example("provider_acknowledged", "provider-1"),
  ];
  it("shows exact counts by durable workspace status without pretending self-report is verified", () => {
    const result = summarizeApplicationReviewQueue(workspaces, "all");
    expect(result.totalLoaded).toBe(4);
    expect(result.drafts).toBe(2);
    expect(result.selfReported).toBe(1);
    expect(result.providerAcknowledged).toBe(1);
    expect(result.filtered.map((item) => item.workspace_id))
      .toEqual(["draft-1", "reported-1", "draft-2", "provider-1"]);
  });

  it.each([
    ["draft", ["draft-1", "draft-2"]],
    ["self_reported_applied", ["reported-1"]],
    ["provider_acknowledged", ["provider-1"]],
  ] as const)("filters %s without changing cases or their source order", (filter, expected) => {
    const before = workspaces.map((item) => item.workspace_id);
    const result = summarizeApplicationReviewQueue(workspaces, filter);
    expect(result.filtered.map((item) => item.workspace_id)).toEqual(expected);
    expect(workspaces.map((item) => item.workspace_id)).toEqual(before);
    expect(result.totalLoaded).toBe(4);
  });

  it("is empty and safe when no owner-scoped applications are loaded", () => {
    expect(summarizeApplicationReviewQueue([], "draft")).toEqual({
      totalLoaded: 0, drafts: 0, selfReported: 0, providerAcknowledged: 0,
      filtered: [],
    });
  });

  it("does not count a reported application as an employer-acknowledged submission", () => {
    const result = summarizeApplicationReviewQueue([
      example("self_reported_applied", "reported-only"),
    ], "provider_acknowledged");
    expect(result.providerAcknowledged).toBe(0);
    expect(result.selfReported).toBe(1);
    expect(result.filtered).toEqual([]);
  });

  it("treats an in-memory older case as loaded without inventing unseen account totals", () => {
    const loaded = [
      example("draft", "recent"),
      example("provider_acknowledged", "older-owned-case"),
    ];
    const result = summarizeApplicationReviewQueue(loaded, "all");
    expect(result.totalLoaded).toBe(2);
    expect(result.providerAcknowledged).toBe(1);
  });
});
