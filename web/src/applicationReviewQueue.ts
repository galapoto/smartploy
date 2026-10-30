import type { ApplicationWorkspace } from "./types";

/**
 * Candidate-only presentation of the already authenticated owner-scoped
 * workspace response. No case, employer attempt, external action or
 * permission is created here.
 *
 * Workspaces can be a bounded listing (plus a selected older case). All
 * counts are therefore explicitly "loaded", never a total across the account.
 */
export type ApplicationReviewFilter =
  "all" | "draft" | "self_reported_applied" | "provider_acknowledged";

export type ApplicationReviewSummary = {
  totalLoaded: number;
  drafts: number;
  selfReported: number;
  providerAcknowledged: number;
  filtered: ApplicationWorkspace[];
};

export function summarizeApplicationReviewQueue(
  workspaces: readonly ApplicationWorkspace[],
  filter: ApplicationReviewFilter,
): ApplicationReviewSummary {
  const drafts = workspaces.filter((item) => item.status === "draft").length;
  const selfReported = workspaces.filter((item) =>
    item.status === "self_reported_applied").length;
  const providerAcknowledged = workspaces.filter((item) =>
    item.status === "provider_acknowledged").length;
  return {
    totalLoaded: workspaces.length,
    drafts,
    selfReported,
    providerAcknowledged,
    filtered: workspaces.filter((item) =>
      filter === "all" || item.status === filter),
  };
}
