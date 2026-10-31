// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import SearchResultsPanel from "./SearchResultsPanel";
import type { SearchResults, SearchJobCard } from "./types";

const baseJob = {
  company: "Example Oy", role_title: "Junior Data Analyst", location: "Helsinki",
  language: "English", work_mode: "remote",
  employer_sector: "private" as const, career_area: "it_data" as const,
  title_experience: "entry" as const, source_current: true, application_url: "https://jobs.example.fi/analyst",
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

  it("accurately distinguishes imported KEHA jobs from external search links", () => {
    render(<SearchResultsPanel {...common} data={general} />);
    expect(screen.getByText(/When the official KEHA connector is enabled/i)).toBeTruthy();
    expect(screen.getByText(/already counted in SmartPloy's listings/i)).toBeTruthy();
    expect(screen.queryByText(/doesn't yet ingest Duunitori, Työmarkkinatori/i)).toBeNull();
    expect(screen.getByRole("link", { name: /Työmarkkinatori/i })).toBeTruthy();
    expect(screen.getByText(/visiting them does not import more jobs/i)).toBeTruthy();
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

  it("routes manual and AI application cards to the shared journey without creating drafts", () => {
    const onChooseFlow = vi.fn();
    render(<SearchResultsPanel {...common} data={general} onChooseFlow={onChooseFlow} />);
    expect(screen.getAllByRole("button", { name: /Apply manually/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /Apply with AI/ })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Prepare documents/ })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /Apply manually/ })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: /Apply with AI/ })[0]);
    expect(onChooseFlow).toHaveBeenNthCalledWith(1, "lever-analyst", "manual");
    expect(onChooseFlow).toHaveBeenNthCalledWith(2, "lever-analyst", "assisted");
    expect(common.onPrepare).not.toHaveBeenCalled();
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


describe("automatic draft scheduling truthfulness", () => {
  it("does not claim a background service merely from the applicant opting in", () => {
    const onAutoDraft = vi.fn();
    render(<SearchResultsPanel {...common} data={personalized}
      autoDraftEnabled={true} autoDraftWorkerStatus="not_configured"
      onAutoDraft={onAutoDraft} />);
    expect(screen.getByText(/background scheduling is not confirmed/i)).toBeTruthy();
    expect(screen.queryByText(/background draft task is registered/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /find and prepare matching drafts now/i }));
    expect(onAutoDraft).toHaveBeenCalledOnce();
  });

  it("reports an actually registered background task and never implies employer submission", () => {
    render(<SearchResultsPanel {...common} data={personalized}
      autoDraftEnabled={true} autoDraftWorkerStatus="registered" onAutoDraft={vi.fn()} />);
    expect(screen.getByText(/background draft task is registered/i)).toBeTruthy();
    expect(screen.getByText(/No employer application is submitted automatically/i)).toBeTruthy();
  });

  it("shows a degraded worker warning without suppressing the direct prepare action", () => {
    const onAutoDraft = vi.fn();
    render(<SearchResultsPanel {...common} data={personalized}
      autoDraftEnabled={true} autoDraftWorkerStatus="degraded" onAutoDraft={onAutoDraft} />);
    expect(screen.getByRole("status").textContent).toMatch(/reported failures/i);
    fireEvent.click(screen.getByRole("button", { name: /find and prepare matching drafts now/i }));
    expect(onAutoDraft).toHaveBeenCalledOnce();
  });
});


describe("Finland-first IT, planning, and explicit all-jobs choice", () => {
  const focused: SearchResults = {
    ...general, available_count: 4, all_jobs: [
      {...job, canonical_key: "junior-fi", job: { ...baseJob,
        role_title: "Junior Data Engineer", location: "Rovaniemi",
        career_area: "it_data", title_experience: "entry" }},
      {...job, canonical_key: "planner-fi", job: { ...baseJob,
        role_title: "Suunnittelija", location: "Kuopio",
        career_area: "planning", title_experience: "unspecified" }},
      {...job, canonical_key: "driver-fi", job: { ...baseJob,
        role_title: "Delivery Driver", location: "Jyväskylä",
        career_area: "other", title_experience: "unspecified" }},
      {...job, canonical_key: "senior-fi", job: { ...baseJob,
        role_title: "Senior Software Engineer", location: "Oulu",
        career_area: "it_data", title_experience: "senior" }},
    ],
  };

  it("shows only IT/planning and junior-or-unknown titles by default", () => {
    render(<SearchResultsPanel {...common} data={focused} />);
    expect(screen.getByText("Junior Data Engineer")).toBeTruthy();
    expect(screen.getByText("Suunnittelija")).toBeTruthy();
    expect(screen.queryByText("Delivery Driver")).toBeNull();
    expect(screen.queryByText("Senior Software Engineer")).toBeNull();
    expect(screen.getByText(/Showing 2 of 4 current listings/i)).toBeTruthy();
    expect(screen.getByText(/missing experience labels are not treated as verified junior jobs/i)).toBeTruthy();
  });

  it("one explicit filter reveals other occupations and senior-labelled roles", () => {
    render(<SearchResultsPanel {...common} data={focused} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Career focus" }), {
      target: { value: "all" },
    });
    expect(screen.getByText("Delivery Driver")).toBeTruthy();
    expect(screen.queryByText("Senior Software Engineer")).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "Experience focus" }), {
      target: { value: "all" },
    });
    expect(screen.getByText("Senior Software Engineer")).toBeTruthy();
    expect(screen.getByText(/Showing 4 of 4 current listings/i)).toBeTruthy();
    expect(common.onChangeCriteria).not.toHaveBeenCalled();
    expect(common.onPrepare).not.toHaveBeenCalled();
  });

  it("links external Finnish boards without implying indexed or auto-applied postings", () => {
    render(<SearchResultsPanel {...common} data={focused} />);
    expect(screen.getByRole("region", { name: "Additional Finland job sources" }).textContent)
      .toMatch(/doesn't yet ingest/i);
    for (const label of ["Duunitori", "Työmarkkinatori", "LinkedIn"]) {
      const a = screen.getByRole("link", { name: new RegExp(label) });
      expect(a.getAttribute("href")).toMatch(/^https:\/\//);
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toContain("noopener");
    }
    expect(screen.getByText(/not counted above or used for unattended applications/i)).toBeTruthy();
  });
});


describe("source-backed traineeship discovery", () => {
  it("filters internship and graduate vacancies independently from training directories", () => {
    const withTrainees: SearchResults = {
      ...general,
      available_count: 4,
      all_jobs: [
        ...general.all_jobs,
        { ...job, canonical_key: "intern-role", job: {
          ...baseJob, role_title: "Intern Data Analyst", opportunity_kind: "internship",
        }},
        { ...job, canonical_key: "graduate-role", job: {
          ...baseJob, role_title: "Graduate Information Specialist", opportunity_kind: "graduate",
        }},
      ],
    };
    render(<SearchResultsPanel {...common} data={withTrainees} />);
    fireEvent.change(screen.getByRole("combobox", { name: /opportunity type/i }), {
      target: { value: "early_career" },
    });
    expect(screen.getByText("Intern Data Analyst")).toBeTruthy();
    expect(screen.getByText("Graduate Information Specialist")).toBeTruthy();
    expect(screen.queryByText("Software Tester")).toBeNull();
    expect(screen.getByText("Internship")).toBeTruthy();
    expect(screen.getByText("Graduate role")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: /opportunity type/i }), {
      target: { value: "all" },
    });
    expect(screen.getByText("Software Tester")).toBeTruthy();
  });
});
