// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ApplicationJourney from "./ApplicationJourney";
import StartChoices from "./StartChoices";
import * as api from "./api";
import type { AutoApplyBatchOutcome, CVJobMatches, SearchJobCard } from "./types";

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
    onPrepare: vi.fn(async () => {}), onPrepareSelected: vi.fn(async (keys: string[],
      _onProgress: (completed: number, total: number) => void,
      _shouldStop?: () => boolean, _keepOnApply?: boolean): Promise<AutoApplyBatchOutcome> => ({
      preparedKeys: keys, failedKeys: [], agentsActive: keys.length,
      agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
    })),
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
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0].getAttribute("href"))
      .toBe("https://employer.example.invalid/planner");
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0].getAttribute("rel"))
      .toContain("noopener");
    fireEvent.click(screen.getAllByRole("button", { name: /save application draft/i })[0]);
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
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0]).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /match \+ tailored documents/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /prepare CV & application/i })[0]);
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("current-planner"));
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("prepares explicitly selected automatic drafts without employer submission", async () => {
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByText(/No email, call or employer application is sent/i)).toBeTruthy();
    expect(screen.getByText(/Each selected job gets its own private application draft and in-app agent/i)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("checkbox", { name: /select for preparation/i })[0]);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["current-planner"], expect.any(Function), expect.any(Function), false));
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

  it("loads later ranked vacancies instead of hiding everything beyond the first page", async () => {
    const later: SearchJobCard = {
      ...listing, canonical_key: "late-recommended",
      job: { ...listing.job, role_title: "Junior Data Analyst at distant employer" },
    };
    vi.mocked(api.getCVJobMatches)
      .mockResolvedValueOnce({ ...data, recommended_count: 2, other_jobs_count: 1 })
      .mockResolvedValueOnce({
        ...data, recommended: [later], other_jobs: [],
        recommended_count: 2, other_jobs_count: 1,
      });
    render(<ApplicationJourney {...props()} />);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("button", { name: /load more current jobs/i }));
    await screen.findByText("Junior Data Analyst at distant employer");
    expect(vi.mocked(api.getCVJobMatches)).toHaveBeenNthCalledWith(2, {
      limit: 40, query: "", selected_job_key: "",
      recommended_offset: 1, other_offset: 1,
    });
    expect(screen.getAllByRole("button", { name: /save application draft/i })).toHaveLength(3);
  });

  it("pins the exact job selected from main Search even when it is outside the first matching window", async () => {
    const pinned: SearchJobCard = {
      ...listing, canonical_key: "selected-page-8", lane: "broader",
      job: { ...listing.job, role_title: "Selected vacancy on a later page" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValueOnce({
      ...data, selected_job: pinned, other_jobs_count: 181,
    });
    const p = { ...props(), selectedJobKey: "selected-page-8" };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("Selected vacancy on a later page");
    expect(screen.getByText("IT-suunnittelija")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: /save application draft/i })[0]);
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("selected-page-8"));
    expect(api.getCVJobMatches).toHaveBeenCalledWith({
      limit: 40, query: "", selected_job_key: "selected-page-8",
    });
  });

  it("searches the complete backend ledger instead of filtering only already loaded rows", async () => {
    const hidden: SearchJobCard = {
      ...listing, canonical_key: "far-past-first-page",
      job: { ...listing.job, company: "UnseenEmployer", role_title: "Faraway QA Trainee" },
    };
    vi.mocked(api.getCVJobMatches).mockImplementation(async (options) =>
      options?.query === "UnseenEmployer" ? {
        ...data, recommended: [hidden], other_jobs: [],
        recommended_count: 1, other_jobs_count: 0,
      } : data);
    render(<ApplicationJourney {...props()}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.change(screen.getByRole("searchbox", { name: /filter matching jobs/i }),
      { target: { value: "UnseenEmployer" } });
    await screen.findByText("Faraway QA Trainee");
    expect(screen.queryByText("IT-suunnittelija")).toBeNull();
    expect(api.getCVJobMatches).toHaveBeenCalledWith({
      limit: 40, query: "UnseenEmployer", selected_job_key: "",
    });
  });

  it("never publishes a late page from another signed-in account", async () => {
    let release!: (value: CVJobMatches) => void;
    const delayed = new Promise<CVJobMatches>((resolve) => { release = resolve; });
    const late: SearchJobCard = {
      ...listing, canonical_key: "wrong-account-page",
      job: { ...listing.job, role_title: "Different account hidden vacancy" },
    };
    vi.mocked(api.getCVJobMatches)
      .mockResolvedValueOnce({ ...data, recommended_count: 2, other_jobs_count: 1 })
      .mockReturnValueOnce(delayed);
    render(<ApplicationJourney {...props()}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("button", { name: /load more current jobs/i }));
    await waitFor(() => expect(api.getCVJobMatches).toHaveBeenCalledTimes(2));
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated: true, user_id: "other-account", auth_source: "oidc",
    });
    release({ ...data, recommended: [late], other_jobs: [], recommended_count: 2 });
    expect((await screen.findByRole("alert")).textContent).toMatch(/signed-in account.*changed/i);
    expect(screen.queryByText("Different account hidden vacancy")).toBeNull();
  });


  it("keeps the whole-ledger search field focused while a debounced private read is pending", async () => {
    let release!: (value: CVJobMatches) => void;
    const delayed = new Promise<CVJobMatches>((resolve) => { release = resolve; });
    vi.mocked(api.getCVJobMatches).mockImplementation((options) =>
      options?.query === "Unseen" ? delayed : Promise.resolve(data));
    render(<ApplicationJourney {...props()}/>);
    await screen.findByText("IT-suunnittelija");
    const input = screen.getByRole("searchbox", { name: /filter matching jobs/i });
    input.focus();
    fireEvent.change(input, { target: { value: "Unseen" } });
    await waitFor(() => expect(api.getCVJobMatches).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("searchbox", { name: /filter matching jobs/i })).toBe(input);
    expect(document.activeElement).toBe(input);
    release(data);
    await screen.findByText("IT-suunnittelija");
  });


  it("shows partial progress, retains only failed exact jobs and retries without repeating successes", async () => {
    const p = { ...props(), mode: "automatic" as const };
    p.onPrepareSelected
      .mockResolvedValueOnce({
        preparedKeys: ["current-planner"], failedKeys: ["extra-role"],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      })
      .mockResolvedValueOnce({
        preparedKeys: ["extra-role"], failedKeys: [],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      });
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    fireEvent.click(selectors[0]);
    fireEvent.click(selectors[1]);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect((await screen.findByText(/1 private draft\(s\) ready/i)).textContent)
      .toMatch(/1 job\(s\) need a retry/i);
    await waitFor(() => {
      expect((selectors[0] as HTMLInputElement).checked).toBe(false);
      expect((selectors[1] as HTMLInputElement).checked).toBe(true);
    });
    expect(screen.getByRole("button", { name: /open prepared applications/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /retry 1 failed job/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenNthCalledWith(
      2, ["extra-role"], expect.any(Function), expect.any(Function), false));
    expect(p.onPrepareSelected).toHaveBeenNthCalledWith(
      1, ["current-planner", "extra-role"], expect.any(Function), expect.any(Function), false);
    await waitFor(() => expect((selectors[1] as HTMLInputElement).checked).toBe(false));
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
  });

  it("reports batch progress without submitting or creating jobs by itself", async () => {
    const p = { ...props(), mode: "automatic" as const };
    let complete!: (value: {
      preparedKeys: string[]; failedKeys: string[]; agentsActive: number;
      agentsPaused: number; agentsClosed: number; agentsUnavailable: number;
    }) => void;
    p.onPrepareSelected.mockImplementation((_keys, onProgress) => {
      onProgress(1, 1);
      return new Promise((resolve) => { complete = resolve; });
    });
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getAllByRole("checkbox", { name: /select for preparation/i })[0]);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByText(/Checked 1 of 1 selected jobs/i)).toBeTruthy();
    // This isolated component mock does not toggle the parent's queueBusy
    // prop. Clicking its still-visible label must nevertheless be ignored by
    // the component's synchronous local in-flight guard.
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(p.onPrepareSelected).toHaveBeenCalledTimes(1);
    await act(async () => {
      complete({
        preparedKeys: ["current-planner"], failedKeys: [],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      });
    });
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(1));
  });


  it("SP50 stops after in-flight job and leaves unstarted private jobs selected", async () => {
    const p = { ...props(), mode: "automatic" as const };
    let shouldStop!: () => boolean;
    let finish!: (value: AutoApplyBatchOutcome) => void;
    p.onPrepareSelected.mockImplementation((_keys, onProgress, stop) => {
      shouldStop = stop!;
      onProgress(0, 2);
      return new Promise<AutoApplyBatchOutcome>((resolve) => { finish = resolve; });
    });
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    selectors.forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByRole("button", { name: /^stop after current job$/i })).toBeTruthy();
    expect(shouldStop()).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /^stop after current job$/i }));
    expect(shouldStop()).toBe(true);
    expect(screen.getByText(/Stop requested; current job may still complete/i)).toBeTruthy();
    await act(async () => {
      finish({
        preparedKeys: ["current-planner"], failedKeys: [], skippedKeys: ["extra-role"],
        stopRequested: true, issues: [], agentsActive: 1,
        agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      });
    });
    expect(await screen.findByText(/1 job\(s\) were not started after Stop/i)).toBeTruthy();
    expect((selectors[0] as HTMLInputElement).checked).toBe(false);
    expect((selectors[1] as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("button", { name: /continue 1 remaining job/i })).toBeTruthy();
    expect(p.onPrepareSelected).toHaveBeenCalledTimes(1);
  });


});
