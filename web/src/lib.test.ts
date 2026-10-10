import { describe, expect, it } from "vitest";
import { filterBySector, queueLabel, relativeFreshness, scoreBand } from "./lib";
import type { RankingCard } from "./types";

function card(sector: "public" | "private" | "unknown"): RankingCard {
  return {
    canonical_key: sector,
    fit_score: 80,
    priority_score: 81,
    queue: "review",
    fit_breakdown: {},
    priority_breakdown: {},
    matched_evidence_ids: [],
    matched_requirements: [],
    mandatory_gaps: [],
    preferred_gaps: [],
    prepare_recommended: false,
    status: "scored",
    job: {
      company: "Example",
      role_title: "Analyst",
      location: "Helsinki",
      work_mode: "hybrid",
      deadline: "",
      application_url: "",
      employer_sector: sector,
      source_ids: [],
      posted_at: "",
      first_seen_at: "",
      last_seen_at: "",
      source_current: true,
      source_attribution: "",
      ai_preparation_allowed: true
    }
  };
}

describe("scoreBand", () => {
  it("uses the Smartploy heatmap thresholds", () => {
    expect(scoreBand(95)).toBe("exceptional");
    expect(scoreBand(84)).toBe("strong");
    expect(scoreBand(74)).toBe("worthwhile");
    expect(scoreBand(64)).toBe("possible");
    expect(scoreBand(50)).toBe("weak");
    expect(scoreBand(44)).toBe("poor");
  });
});

describe("sector filtering", () => {
  it("never guesses unknown jobs into public or private", () => {
    const items = [card("public"), card("private"), card("unknown")];
    expect(filterBySector(items, "public").map((item) => item.canonical_key)).toEqual(["public"]);
    expect(filterBySector(items, "private").map((item) => item.canonical_key)).toEqual(["private"]);
    expect(filterBySector(items, "unknown").map((item) => item.canonical_key)).toEqual(["unknown"]);
    expect(filterBySector(items, "all")).toHaveLength(3);
  });
});

describe("labels and freshness", () => {
  it("formats queue names and relative age", () => {
    expect(queueLabel("auto_prepare")).toBe("Auto prepare");
    expect(
      relativeFreshness("2026-10-10T09:30:00Z", new Date("2026-10-10T10:00:00Z"))
    ).toBe("Seen 30m ago");
  });
});
