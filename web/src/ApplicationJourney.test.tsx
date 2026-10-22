// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ApplicationJourney from "./ApplicationJourney";
import StartChoices from "./StartChoices";
import * as api from "./api";
import type { CVJobMatches, SearchJobCard } from "./types";

vi.mock("./api", () => ({ getCVJobMatches: vi.fn(), getSession: vi.fn() }));

const listing: SearchJobCard = {
  canonical_key: "current-planner",
  job: {
    company: "Public Sector Test Oy", role_title: "IT-suunnittelija",
    location: "Vantaa", application_url: "https://employer.example.invalid/planner",
    career_area: "planning", work_mode: "hybrid", deadline: "",
    employer_sector: "public", source_ids: ["synthetic"],
    posted_at: "2026-10-22T07:00:00Z", first_seen_at: "2026-10-22T07:00:00Z",
    last_seen_at: "2026-10-22T07:00:00Z", source_current: true,
    source_attribution: "Synthetic official source", ai_preparation_allowed: false,
  },
  lane: "recommended", preference_score: 88,
  reasons: ["Job title matches Suunnittelija"], unknown_fields: [],
};
const data: CVJobMatches = {
  cv_present: true, cv_filename: "MyCV.pdf", match_mode: "cv_text_signals",
  detected_roles: ["Suunnittelija"], detected_topics: ["Power BI"],
  recommended: [listing], other_jobs: [{
    ...listing, canonical_key: "extra-role", lane: "broader",
    job: { ...listing.job, role_title: "IT support" },
  }],
  current_jobs_count: 2, recommended_count: 1,
  matched_from: "local_cv_text_not_approved_evidence",
  qualifications_verified: false, employer_actions_performed: false,
};

function props() {
  return {
    userId: "synthetic-account-a", cv: { present: true, filename: "MyCV.pdf", sha256: "abc" },
    mode: "manual" as const, selectedJobKey: "", uploading: false,
    preparing: "", queueBusy: false, onMode: vi.fn(), onUpload: vi.fn(),
    onReviewCV: vi.fn(), onFindJobs: vi.fn(), onOpenApplications: vi.fn(),
    onPrepare: vi.fn(async () => {}), onPrepareSelected: vi.fn(async (_keys: string[]) => {}),
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getSession).mockResolvedValue({
    authenticated: true, user_id: "synthetic-account-a", auth_source: "oidc",
  });
  vi.mocked(api.getCVJobMatches).mockResolvedValue(data);
});
afterEach(cleanup);

describe("SP21 application journey", () => {
  it("starts from an explicit mode and uploaded CV, then offers one-click manual employer link", async () => {
    const p = props();
    render(<ApplicationJourney {...p} />);
    const role = await screen.findByText("IT-suunnittelija");
    expect(role).toBeTruthy();
    expect(screen.getByText(/1 CV-text matches/i)).toBeTruthy();
    expect(screen.getByText(/Search cues detected in CV/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /apply on employer site/i }).getAttribute("href"))
      .toBe("https://employer.example.invalid/planner");
    expect(screen.getByRole("link", { name: /apply on employer site/i }).getAttribute("rel"))
      .toContain("noopener");
    fireEvent.click(screen.getByRole("button", { name: /save application draft/i }));
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("current-planner"));
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
    expect(api.getCVJobMatches).toHaveBeenCalledTimes(1);
  });

  it("does not require CV before mode selection, and CV upload button actually responds", () => {
    const p = { ...props(), cv: { present: false } };
    render(<ApplicationJourney {...p} />);
    expect(screen.getByRole("heading", { name: /matching jobs appear here/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /upload CV & find jobs/i }));
    expect(p.onUpload).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /browse all jobs/i }));
    expect(p.onFindJobs).toHaveBeenCalledTimes(1);
    expect(api.getCVJobMatches).not.toHaveBeenCalled();
  });

  it("keeps assisted filtering separate from document preparation", async () => {
    const p = { ...props(), mode: "assisted" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("radio", { name: /filter jobs only/i }));
    expect(screen.queryByRole("button", { name: /prepare CV & application/i })).toBeNull();
    expect(screen.getByRole("link", { name: /apply on employer site/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /match \+ tailored documents/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare CV & application/i }));
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("current-planner"));
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("prepares explicitly selected automatic drafts without employer submission", async () => {
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByText(/does not send applications to employers/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: /select for preparation/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare selected applications/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledWith(["current-planner"]));
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
  });

  it("never renders another account's private CV-derived matches", async () => {
    vi.mocked(api.getSession).mockResolvedValueOnce({
      authenticated: true, user_id: "other-account", auth_source: "oidc",
    });
    render(<ApplicationJourney {...props()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("IT-suunnittelija")).toBeNull();
    expect(screen.getByText(/signed-in account changed/i)).toBeTruthy();
  });

  it("offers four clear non-submitting starting choices", () => {
    const onMode = vi.fn(), onBrowse = vi.fn();
    render(<StartChoices onMode={onMode} onBrowse={onBrowse}/>);
    fireEvent.click(screen.getByRole("button", { name: /apply manually/i }));
    expect(onMode).toHaveBeenLastCalledWith("manual");
    fireEvent.click(screen.getByRole("button", { name: /apply with AI/i }));
    expect(onMode).toHaveBeenLastCalledWith("assisted");
    fireEvent.click(screen.getByRole("button", { name: /autoapply/i }));
    expect(onMode).toHaveBeenLastCalledWith("automatic");
    fireEvent.click(screen.getByRole("button", { name: /just find jobs/i }));
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });
});
