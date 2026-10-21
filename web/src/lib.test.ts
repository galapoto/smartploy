import { describe, expect, it } from "vitest";
import {
  filterBySector,
  formatCadence,
  queueLabel,
  relativeFreshness,
  listingObservationLabels,
  relativeSchedule,
  safeExternalJobUrl,
  scoreBand
} from "./lib";
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


describe("worker schedule formatting", () => {
  it("formats future next-run values deterministically", () => {
    const now = new Date("2026-10-10T10:00:00Z");
    expect(relativeSchedule("2026-10-10T10:04:01Z", now)).toBe("in 5m");
    expect(relativeSchedule("2026-10-10T11:00:00Z", now)).toBe("in 1h");
    expect(relativeSchedule("2026-10-10T09:59:59Z", now)).toBe("Due now");
    expect(relativeSchedule("", now)).toBe("Schedule unknown");
  });

  it("formats worker cadences", () => {
    expect(formatCadence(60)).toBe("every 1m");
    expect(formatCadence(600)).toBe("every 10m");
    expect(formatCadence(3600)).toBe("every 1h");
    expect(formatCadence(15)).toBe("every 15s");
  });
});


describe("ObumAI product navigation contract", () => {
  it("keeps the canonical ObumAI workspace URL fixed", async () => {
    const source = await import("./App?raw");
    expect(source.default).toContain(
      '<a className="obumai-brand" href="https://app.obumai.com/" target="_self" title="Open ObumAI">'
    );
    expect(source.default).not.toContain("https://app.obumai.com/?token=");
  });
});

describe("job source observation truth", () => {
  const now = new Date("2026-10-12T12:00:00Z");

  it("keeps old publication dates distinct from a recent successful source observation", () => {
    expect(listingObservationLabels(
      "2026-09-20T12:00:00Z",
      "2026-09-21T12:00:00Z",
      "2026-10-12T11:00:00Z",
      now
    )).toEqual({
      origin: "Posted 22d ago",
      observation: "Last observed 1h ago",
      caution: null
    });
  });

  it("uses first discovery when no genuine publication date is provided", () => {
    const labels = listingObservationLabels(
      "", "2026-10-10T12:00:00Z", "2026-10-12T11:00:00Z", now
    );
    expect(labels.origin).toBe("First discovered 2d ago");
    expect(labels.observation).toBe("Last observed 1h ago");
    expect(labels.caution).toBeNull();
  });

  it("cautions at the same 48-hour point that background auto drafting stops", () => {
    const fortyNineHoursAgo = "2026-10-18T23:00:00Z";
    const labels = listingObservationLabels(
      "2026-09-01T00:00:00Z",
      "2026-09-01T00:00:00Z",
      fortyNineHoursAgo,
      new Date("2026-10-21T00:00:00Z")
    );
    expect(labels.caution).toMatch(/at least 48h ago/);
    const stillFresh = listingObservationLabels(
      "", "", "2026-10-19T23:00:00Z",
      new Date("2026-10-21T00:00:00Z")
    );
    expect(stillFresh.caution).toBeNull();
  });

  it("cautions rather than claiming still open when source observation is older than 48h", () => {
    const labels = listingObservationLabels(
      "2026-10-11T12:00:00Z", "2026-10-11T12:00:00Z",
      "2026-10-09T12:00:00Z", now
    );
    expect(labels.origin).toBe("Posted 1d ago");
    expect(labels.observation).toBe("Last observed 3d ago");
    expect(labels.caution).toMatch(/at least 48h ago/);
  });

  it("handles invalid, missing and future source timestamps conservatively", () => {
    const invalid = listingObservationLabels("", "invalid", "", now);
    expect(invalid.origin).toBe("Publication date unknown");
    expect(invalid.observation).toBe("Last source observation unknown");
    expect(invalid.caution).toMatch(/confirm on employer site/);
    const future = listingObservationLabels(
      "2026-11-01T12:00:00Z", "2026-10-12T11:00:00Z",
      "2026-10-20T12:00:00Z", now
    );
    expect(future.origin).toBe("First discovered 1h ago");
    expect(future.observation).toBe("Last source observation unknown");
    expect(future.caution).not.toBeNull();
  });
});

describe("safe external employer posting links", () => {
  it("keeps legitimate absolute HTTP(S) employer links navigable", () => {
    expect(safeExternalJobUrl("https://jobs.example.fi/jobs/analyst?ref=smartploy"))
      .toBe("https://jobs.example.fi/jobs/analyst?ref=smartploy");
    expect(safeExternalJobUrl("http://legacy.example.fi/role"))
      .toBe("http://legacy.example.fi/role");
  });

  it("refuses scripts, data URLs, relative redirects, embedded credentials and malformed links", () => {
    for (const candidate of [
      "", "javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,hello",
      "file:///etc/hosts", "/redirect?url=https://evil.invalid",
      "//evil.invalid/page", "https://user:pass@jobs.example.fi/",
      "https://jobs.example.fi/\nother", "https://example.fi\\@evil.invalid",
      "https://", "https://\u0000evil.invalid",
    ]) {
      expect(safeExternalJobUrl(candidate), candidate).toBe("");
    }
    expect(safeExternalJobUrl(null)).toBe("");
    expect(safeExternalJobUrl(undefined)).toBe("");
  });
});
