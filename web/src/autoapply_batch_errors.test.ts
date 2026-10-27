import { describe, expect, it } from "vitest";
import { describeAutoApplyBatchIssue } from "./autoapply_batch_errors";

describe("SP50 owner-private preparation failure classification", () => {
  it.each([
    [404, "job_missing", false],
    [410, "job_missing", false],
    [409, "review_required", false],
    [422, "review_required", false],
    [400, "review_required", false],
    [401, "access_denied", false],
    [403, "access_denied", false],
    [429, "service_busy", true],
    [503, "service_busy", true],
    [504, "service_busy", true],
    [500, "outcome_unknown", true],
  ] as const)("does not retry HTTP %i without appropriate review", (status, kind, retryable) => {
    const issue = describeAutoApplyBatchIssue(
      "job-private-a", Object.assign(new Error("SECRET candidate profile"), { status }),
    );
    expect(issue).toMatchObject({
      canonicalKey: "job-private-a", kind, retryable,
    });
    expect(issue.guidance).not.toContain("SECRET");
    expect(issue.guidance.length).toBeGreaterThan(30);
    expect(issue.guidance.length).toBeLessThan(220);
  });

  it("never converts an unknown network outcome into employer consent or a verified submission", () => {
    const issue = describeAutoApplyBatchIssue(
      "job-private-b", new Error("Network request may have committed a draft"),
    );
    expect(issue).toMatchObject({
      kind: "outcome_unknown", retryable: true,
    });
    expect(issue.guidance).toMatch(/Check My applications/i);
    expect(issue.guidance).not.toMatch(/submitted|employer accepted/i);
  });

  it("does not trust malformed or fabricated status metadata", () => {
    for (const failure of [
      null, { status: "404" }, { status: -5 }, { status: 1000 },
      { status: true }, { status: 404.5 },
    ]) {
      const issue = describeAutoApplyBatchIssue("job-private", failure);
      expect(issue.kind).toBe("outcome_unknown");
    }
  });
});
