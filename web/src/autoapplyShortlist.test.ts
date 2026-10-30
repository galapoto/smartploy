import { describe, expect, it } from "vitest";
import { addCVShortlist, AUTOAPPLY_SELECTION_LIMIT,
  isSafeCVShortlistMatch, visibleCurrentKeys } from "./autoapplyShortlist";
import type { SearchJobCard } from "./types";

function vacancy(
  key: string, options: {
    lane?: SearchJobCard["lane"]; title?: string; current?: boolean;
    reason?: string; url?: string;
  } = {},
): SearchJobCard {
  return {
    canonical_key: key,
    lane: options.lane ?? "recommended",
    preference_score: 88,
    reasons: [options.reason ?? "Job title matches Data Analyst"],
    unknown_fields: [],
    job: {
      company: "Fictional IT Employer", role_title: options.title ?? "Junior Data Analyst",
      location: "Finland", career_area: "it_data", work_mode: "hybrid",
      employer_sector: "private", deadline: "", source_ids: ["fixture"],
      posted_at: "", first_seen_at: "", last_seen_at: "",
      source_current: options.current ?? true,
      source_attribution: "Synthetic public feed", ai_preparation_allowed: false,
      application_url: options.url ?? "https://employer.example.invalid/jobs/" + key,
    },
  };
}

describe("SP75 explicit CV-to-AutoApply shortlist", () => {
  it("selects matching current employer jobs without requiring per-card clicks", () => {
    const rows = [vacancy("first"), vacancy("second"), vacancy("third")];
    const selected = addCVShortlist([], rows);
    expect(selected.selected).toEqual(["first", "second", "third"]);
    expect(selected.added).toEqual(["first", "second", "third"]);
    expect(selected.eligible).toBe(3);
    expect(rows.map((row) => row.canonical_key)).toEqual(["first", "second", "third"]);
  });

  it("skips incidental skill text, retired jobs, outside lane, invalid employer URLs", () => {
    const rows = [
      vacancy("good"),
      vacancy("driver", {
        title: "Delivery Driver", reason: "Keywords: Python",
      }),
      vacancy("weak", { reason: "Job title overlaps with Analyst" }),
      vacancy("retired", { current: false }),
      vacancy("explore", { lane: "broader" }),
      vacancy("bad-url", { url: "javascript:alert(1)" }),
      vacancy("embedded-credentials", { url: "https://user:secret@jobs.invalid/a" }),
      vacancy("no-url", { url: "" }),
    ];
    expect(rows.map(isSafeCVShortlistMatch)).toEqual([
      true, false, false, false, false, false, false, false,
    ]);
    expect(addCVShortlist([], rows).selected).toEqual(["good"]);
  });

  it("preserves deliberately selected jobs first and never duplicates or exceeds 15", () => {
    const existing = ["explicit", "explicit", "broader"];
    const rows = [
      vacancy("explicit"), ...Array.from({ length: 20 }, (_, i) => vacancy("recommended-" + i)),
    ];
    const result = addCVShortlist(existing, rows);
    expect(result.selected.length).toBe(AUTOAPPLY_SELECTION_LIMIT);
    expect(result.selected.slice(0, 2)).toEqual(["explicit", "broader"]);
    expect(result.selected[2]).toBe("recommended-0");
    expect(result.selected[result.selected.length - 1]).toBe("recommended-12");
    expect(new Set(result.selected).size).toBe(15);
    expect(result.eligible).toBe(20);
  });

  it("returns no automatic candidates for keyword-only unrelated jobs", () => {
    const result = addCVShortlist([], [
      vacancy("skill-only", { reason: "Keywords: Power BI" }),
      vacancy("other", { lane: "broader" }),
    ]);
    expect(result.added).toEqual([]);
    expect(result.selected).toEqual([]);
  });

  it("rejects missing, stale or hidden selections before private preparation", () => {
    expect(visibleCurrentKeys(
      ["visible", "hidden", "retired", "invalid", "visible"],
      [
        vacancy("visible"),
        vacancy("retired", { current: false }),
        vacancy("invalid", { url: "data:text/html,test" }),
      ],
    )).toEqual(["visible"]);
  });
});
