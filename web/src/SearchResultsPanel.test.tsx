// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import SearchResultsPanel from "./SearchResultsPanel";
import type { SearchResults, SearchJobCard } from "./types";

const baseJob = {
  company: "Example Oy", role_title: "Junior Data Analyst", location: "Helsinki",
  language: "English", work_mode: "remote",
  employer_sector: "private" as const, source_current: true, application_url: "https://jobs.example.fi/analyst",
  source_ids: ["lever"], source_attribution: "Public ATS", posted_at: "2026-10-11T10:00:00Z",
  first_seen_at: "2026-10-11T10:00:00Z", last_seen_at: "2026-10-11T10:00:00Z",
  deadline: "", ai_preparation_allowed: true,
};

const job: SearchJobCard = {
  canonical_key: "lever-analyst", job: baseJob,
  preference_score: null, reasons: [], unknown_fields: [], lane: "all",
};
const general: SearchResults = {
  mode: "general", completed: true, available_count: 2,
  recommendations: [], broader: [], all_jobs: [
    job,
    {
      ...job, canonical_key: "lever-tester", lane: "all",
      job: { ...baseJob, role_title: "Software Tester", company: "Quality Oy", location: "Espoo" },
    },
  ],
  score_kind: "none", external_actions_authorized: false,
};
const personalized: SearchResults = {
  ...general, mode: "personalized", all_jobs: [],
  score_kind: "preference_alignment_not_verified_qualification",
  recommendations: [{
    ...job, lane: "recommended", preference_score: 87,
    reasons: ["Job title matches Data analyst", "Preferred location"],
    unknown_fields: ["Experience level not specified"],
  }],
  broader: [],
};

const common = {
  search: "", sector: "all" as const,
  onSector: vi.fn(), view: "top" as const,
  onView: vi.fn(), displayMode: "heatmap" as const,
  onToggleDisplay: vi.fn(), currentPage: "jobs" as const,
  busyKey: "", onPrepare: vi.fn(), onAllJobs: vi.fn(),
  onChangeCriteria: vi.fn(), onChangeMode: vi.fn(),
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("job discovery mode semantics", () => {
  it("renders all general listings without any score or inferred fit percentage", () => {
    render(<SearchResultsPanel {...common} data={general} />);
    expect(screen.getByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.getByText("Software Tester")).toBeTruthy();
    expect(screen.getByText(/2 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/87% search match/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /why shown/i })).toBeNull();
    expect(screen.getAllByText("General listing")).toHaveLength(2);
  });

  it("filters current listings client side without changing saved preferences", () => {
    render(<SearchResultsPanel {...common} data={general} search="tester" />);
    expect(screen.queryByText("Junior Data Analyst")).toBeNull();
    expect(screen.getByText("Software Tester")).toBeTruthy();
    expect(common.onChangeCriteria).not.toHaveBeenCalled();
  });

  it("explains preference scores and uncertainty, never claims eligibility verified", () => {
    render(<SearchResultsPanel {...common} data={personalized} />);
    expect(screen.getByText(/87% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /why shown/i }));
    expect(screen.getByText(/Job title matches Data analyst/i)).toBeTruthy();
    expect(screen.getByText(/Experience level not specified/i)).toBeTruthy();
    expect(screen.getByText(/not a verified skills or eligibility assessment/i)).toBeTruthy();
  });

  it("separates observed mismatches from unknown fields in the explanation", () => {
    const mismatch: SearchResults = {
      ...personalized,
      recommendations: [{
        ...personalized.recommendations[0],
        mismatched_fields: [
          "Listed senior role differs from your entry experience preference",
          "Work arrangement differs from preferred arrangements",
        ],
      }],
    };
    render(<SearchResultsPanel {...common} data={mismatch} />);
    fireEvent.click(screen.getByRole("button", { name: /why shown/i }));
    expect(screen.getByText(/Differences from your preferences:/i)).toBeTruthy();
    expect(screen.getByText(/Listed senior role differs/i)).toBeTruthy();
    expect(screen.getByText(/Not verified from the posting:/i)).toBeTruthy();
  });

  it("requires an explicit action to prepare or change search mode", () => {
    render(<SearchResultsPanel {...common} data={general} />);
    fireEvent.click(screen.getAllByRole("button", { name: /prepare documents/i })[0]);
    expect(common.onPrepare).toHaveBeenCalledOnce();
    expect(common.onPrepare).not.toHaveBeenCalledWith("anything else");
    fireEvent.click(screen.getByRole("button", { name: /personalized/i }));
    expect(common.onChangeMode).toHaveBeenCalledWith("personalized");
  });
});

describe("job-date and source observation accuracy", () => {
  it("shows old publication and fresh source observation as different facts", () => {
    const now = Date.now();
    const old = new Date(now - 25 * 86_400_000).toISOString();
    const recent = new Date(now - 3_600_000).toISOString();
    const one: SearchResults = {
      ...general, available_count: 1,
      all_jobs: [{ ...job, job: {
        ...baseJob, posted_at: old, first_seen_at: old, last_seen_at: recent
      } }]
    };

    render(<SearchResultsPanel {...common} data={one} />);
    expect(screen.getByText(/Posted 25d ago/)).toBeTruthy();
    expect(screen.getByText(/Last observed 1h ago/)).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText(/search match/i)).toBeNull();
  });

  it("warns without hiding an old-source job or pretending to verify employer availability", () => {
    const old = new Date(Date.now() - 7 * 86_400_000).toISOString();
    const one: SearchResults = {
      ...personalized,
      recommendations: [{ ...personalized.recommendations[0], job: {
        ...baseJob, posted_at: "", first_seen_at: old, last_seen_at: old
      } }]
    };
    render(<SearchResultsPanel {...common} data={one} />);
    expect(screen.getByText(/First discovered 7d ago/)).toBeTruthy();
    expect(screen.getByText(/Last observed 7d ago/)).toBeTruthy();
    expect(screen.getByRole("note").textContent).toMatch(/confirm on employer site/);
    expect(screen.getByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.getByRole("button", { name: /prepare documents/i }).hasAttribute("disabled")).toBe(false);
  });

  it("marks unavailable observation timestamps unknown in unprofiled General mode", () => {
    const one: SearchResults = {
      ...general, available_count: 1,
      all_jobs: [{ ...job, job: {
        ...baseJob, posted_at: "", first_seen_at: "", last_seen_at: ""
      } }]
    };
    render(<SearchResultsPanel {...common} data={one} />);
    expect(screen.getByText("Publication date unknown")).toBeTruthy();
    expect(screen.getByText("Last source observation unknown")).toBeTruthy();
    expect(screen.getByRole("note").textContent).toMatch(/time is unknown/);
    expect(screen.queryByText(/search match/i)).toBeNull();
  });
});

describe("job posting link safety", () => {
  it("keeps real employer links clickable without changing their target", () => {
    render(<SearchResultsPanel {...common} data={general} />);
    const anchors = screen.getAllByRole("link", { name: /Job posting/i });
    expect(anchors).toHaveLength(2);
    expect(anchors[0].getAttribute("href")).toBe("https://jobs.example.fi/analyst");
    expect(anchors[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(anchors[0].getAttribute("target")).toBe("_blank");
  });

  it("never creates a clickable executable or credentialed link from untrusted source data", () => {
    const unsafe = [
      "javascript:alert('unsafe')", "data:text/html,unsafe",
      "//untrusted.invalid/redirect", "https://person:secret@jobs.example.fi/posting",
    ];
    const records: SearchResults = {
      ...general, available_count: unsafe.length,
      all_jobs: unsafe.map((application_url, index) => ({
        ...job, canonical_key: "unsafe-" + index,
        job: { ...baseJob, role_title: "Unsafe synthetic " + index, application_url },
      })),
    };
    render(<SearchResultsPanel {...common} data={records} />);
    expect(screen.queryByRole("link", { name: /Job posting/ })).toBeNull();
    expect(screen.getAllByText(/Employer link unavailable/)).toHaveLength(unsafe.length);
    expect(screen.getAllByRole("button", { name: /Prepare documents/ })).toHaveLength(unsafe.length);
    expect(common.onPrepare).not.toHaveBeenCalled();
  });
});
