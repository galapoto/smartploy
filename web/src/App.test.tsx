// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import App from "./App";
import type { PrivateSavedJob, SearchPreferences, SearchResults } from "./types";

vi.mock("./api", () => ({
  addManualJob: vi.fn(), approveFact: vi.fn(), createFact: vi.fn(),
  deletePrivateSavedJob: vi.fn(), getPrivateSavedJobs: vi.fn(),
  deleteCV: vi.fn(), deleteFact: vi.fn(), getApplications: vi.fn(),
  getCV: vi.fn(), getCVJobMatches: vi.fn(), getDashboard: vi.fn(), getHealth: vi.fn(),
  getJobs: vi.fn(), getProfileFacts: vi.fn(), getSession: vi.fn(),
  startApplicationWorkspace: vi.fn(), uploadCV: vi.fn(),
  getSearchPreferences: vi.fn(), updateSearchPreferences: vi.fn(),
  getSearchResults: vi.fn(), getLocalAIStatus: vi.fn(),
  prepareMyMatchingDrafts: vi.fn(),
  getJobAIConsents: vi.fn(), getJobAIConsentEvents: vi.fn(),
  grantJobAIConsent: vi.fn(), revokeJobAIConsent: vi.fn(),
}));
vi.mock("./ApplicationStudio", () => ({
  default: ({ focusId }: { focusId: string }) =>
    <div data-testid="application-editor" data-workspace={focusId}>Application editor</div>,
}));

const initial: SearchPreferences = {
  completed: false, mode: "personalized", roles: [], locations: [],
  languages: [], work_modes: [], keywords: [], skills: [],
  seniority: "any", revision: 0, updated_at: "", verified_qualification_fit: false,
};
const listing = {
  canonical_key: "test-analyst",
  job: {
    company: "Example Oy", role_title: "Junior Data Analyst", location: "Helsinki",
    language: "English", work_mode: "remote", employer_sector: "private" as const,
    career_area: "it_data" as const, title_experience: "entry" as const,
    source_current: true, application_url: "https://jobs.example.fi/analyst",
    source_ids: ["test-ats"], source_attribution: "Public ATS",
    posted_at: "2026-10-11T10:00:00Z", first_seen_at: "2026-10-11T10:00:00Z",
    last_seen_at: "2026-10-11T10:00:00Z", deadline: "",
    ai_preparation_allowed: true,
  },
  reasons: [], unknown_fields: [], lane: "all" as const, preference_score: null,
};
const setup: SearchResults = {
  mode: "setup_required", completed: false, recommendations: [], broader: [],
  all_jobs: [], available_count: 1, score_kind: "none", external_actions_authorized: false,
};
const general: SearchResults = {
  ...setup, mode: "general", completed: true, all_jobs: [listing],
};
const tailored: SearchResults = {
  ...setup, mode: "personalized", completed: true,
  score_kind: "preference_alignment_not_verified_qualification",
  recommendations: [{
    ...listing, lane: "recommended",
    reasons: ["Job title matches Data Analyst"], preference_score: 90,
  }],
};
let currentPrefs: SearchPreferences = initial;
let personalJobs: PrivateSavedJob[] = [];

beforeEach(() => {
  vi.resetAllMocks();
  currentPrefs = { ...initial };
  personalJobs = [];
  vi.mocked(api.getDashboard).mockResolvedValue({
    top_matches: [], possible_matches: [],
    source_health: [{
      source_id: "test-ats", status: "healthy", last_item_count: 1,
      last_success_at: "2026-10-11T10:00:00Z",
    }],
    worker: { ready: true, count: 1, tasks: [] },
    applications: { awaiting_review: 0, actually_submitted: 0 },
  } as never);
  vi.mocked(api.getSearchPreferences).mockImplementation(async () => ({...currentPrefs}));
  vi.mocked(api.getSearchResults).mockImplementation(async () =>
    !currentPrefs.completed ? setup : currentPrefs.mode === "general" ? general : tailored
  );
  vi.mocked(api.getSession).mockResolvedValue({
    authenticated: true, email: "test@smartploy.invalid",
    user_id: "usr-synthetic-1", profile_id: "profile-synthetic-1",
    auth_source: "fixture"
  });
  vi.mocked(api.getHealth).mockResolvedValue({ obumai_configured: false } as never);
  vi.mocked(api.getCV).mockResolvedValue({ present: false });
  vi.mocked(api.getCVJobMatches).mockResolvedValue({
    cv_present: true, cv_filename: "synthetic-CV.pdf", match_mode: "cv_text_signals",
    detected_roles: ["Data Analyst"], detected_topics: ["Python"],
    recommended: [tailored.recommendations[0]], other_jobs: [],
    current_jobs_count: 1, recommended_count: 1,
    matched_from: "local_cv_text_not_approved_evidence",
    qualifications_verified: false, employer_actions_performed: false,
  });
  vi.mocked(api.getProfileFacts).mockResolvedValue({ facts: [], count: 0 });
  vi.mocked(api.getApplications).mockResolvedValue({ applications: [], count: 0 });
  vi.mocked(api.getJobs).mockResolvedValue({ jobs: [], count: 0 });
  vi.mocked(api.getPrivateSavedJobs).mockImplementation(async () => ({
    jobs: [...personalJobs], count: personalJobs.length, private: true,
  }));
  vi.mocked(api.getJobAIConsents).mockResolvedValue({
    consents: [], count: 0, private: true, unattended_processing_enabled: false,
  });
  vi.mocked(api.getJobAIConsentEvents).mockResolvedValue({
    events: [], count: 0, private: true,
    history_type: "consent_grant_and_withdrawal_only",
  });
  vi.mocked(api.addManualJob).mockImplementation(async (payload) => {
    const item: PrivateSavedJob = {
      ...payload, saved_job_id: "saved-synthetic-" + (personalJobs.length + 1),
      created_at: "2026-10-12T10:00:00Z", private: true,
      employer_availability_verified: false, external_actions_authorized: false,
    };
    personalJobs = [item, ...personalJobs];
    return { status: "saved_private", job: item };
  });
  vi.mocked(api.deletePrivateSavedJob).mockImplementation(async (id) => {
    personalJobs = personalJobs.filter((item) => item.saved_job_id !== id);
    return { deleted: true };
  });
  vi.mocked(api.getLocalAIStatus).mockResolvedValue({
    configured: false, ready: false, provider: "disabled", model: "", external_ai_forwarding: false,
  });
  vi.mocked(api.updateSearchPreferences).mockImplementation(async (payload) => {
    currentPrefs = { ...currentPrefs, ...payload, completed: true,
      revision: payload.expected_revision + 1, verified_qualification_fit: false,
      updated_at: "2026-10-11T12:00:00Z",
    };
    return {...currentPrefs};
  });
  vi.mocked(api.startApplicationWorkspace).mockResolvedValue({
    created: true, workspace: { workspace_id: "kit-" + "a".repeat(30) },
  } as never);
  vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValue({
    status: "prepared", checked: 1, eligible: 1, created: 1, already_prepared: 0,
    stopped_on_opt_out: false, provider_calls: 0,
    employer_actions_performed: false, automatic_submission_authorized: false,
  });
});
afterEach(() => cleanup());

function switchableSession() {
  let account = "a";
  vi.mocked(api.getSession).mockImplementation(async () => ({
    authenticated: true, email: "shared@smartploy.invalid",
    user_id: "usr-account-" + account,
    profile_id: "profile-account-" + account,
    auth_source: "fixture",
  }));
  return () => { account = "b"; };
}

describe("actual SmartPloy App first-use and application handoff", () => {
  it("renders the first-use chooser even if optional AI status never returns", async () => {
    vi.mocked(api.getLocalAIStatus).mockImplementation(
      () => new Promise(() => { /* simulate stalled private model */ })
    );
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Apply for jobs in four simple steps." })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Apply manually/i })).toBeTruthy();
    fireEvent.click(screen.getByText(/Advanced: customize search preferences/i));
    expect(screen.getByRole("radio", { name: /general job search/i })).toBeTruthy();
    expect(vi.mocked(api.getSearchResults)).toHaveBeenCalled();
  });

  it("offers deliberate sign-out to OIDC users without logging out from navigation", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated: true, email: "oidc@example.invalid",
      user_id: "usr-oidc-synthetic", profile_id: "profile-oidc-synthetic",
      auth_source: "oidc",
    });
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    const signOut = await screen.findByRole("link", { name: /Sign out securely/i });
    expect(signOut.getAttribute("href")).toBe("/auth/logout");
    // Navigation to GET only displays a confirmation; no client-side
    // automatic logout fetch or redirect to an unsafe external origin.
    expect(vi.mocked(api.getSession)).toHaveBeenCalled();
  });

  it("does not offer an OIDC logout action for Cloudflare-only sessions", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated: true, email: "access@example.invalid",
      user_id: "usr-cf-synthetic", profile_id: "profile-cf-synthetic",
      auth_source: "cloudflare_access",
    });
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    expect(screen.queryByRole("link", { name: /Sign out securely/i })).toBeNull();
  });

  it("supports general browsing and CV-first applications without personalized search criteria", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic-CV.pdf", sha256: "test-cv-only"
    });
    render(<App />);
    fireEvent.click(await screen.findByText(/Advanced: customize search preferences/i));
    fireEvent.click(await screen.findByRole("radio", { name: /general job search/i }));
    fireEvent.click(await screen.findByRole("button", { name: /browse all jobs/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.getByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^Apply manually$/ }));
    expect(await screen.findByRole("heading", { name: "Jobs from your CV" })).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Save application draft" }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledWith("test-analyst", "usr-synthetic-1"));
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByTestId("application-editor").getAttribute("data-workspace")).toMatch(/^kit-/);
  });

  it("creates a private per-job agent only after explicit AutoApply batch selection", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic-CV.pdf", sha256: "test-cv-only"
    });
    vi.mocked(api.startApplicationWorkspace).mockResolvedValue({
      workspace: { workspace_id: "kit-private-analyst" },
      created: true,
      agent_tracking: {
        requested: true, state: "active", created: true,
        external_actions_performed: 0, worker_wake_verified: false,
      },
    } as never);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Automatic.*AutoApply/i }));
    expect(await screen.findByRole("heading", { name: "Jobs from your CV" })).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: /select for preparation/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledWith(
      "test-analyst", "usr-synthetic-1", true
    ));
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(await screen.findByText(/1 private per-job agent\(s\) ready/)).toBeTruthy();
    expect(screen.getByText(/No applications were sent to employers/i)).toBeTruthy();
  });

  it("keeps an AutoApply draft usable when the durable agent worker is unavailable", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic-CV.pdf", sha256: "test-cv-only"
    });
    vi.mocked(api.startApplicationWorkspace).mockResolvedValue({
      workspace: { workspace_id: "kit-private-analyst" },
      created: true,
      agent_tracking: {
        requested: true, state: "unavailable", created: false,
        external_actions_performed: 0, worker_wake_verified: false,
      },
    } as never);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Automatic.*AutoApply/i }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    fireEvent.click(screen.getByRole("checkbox", { name: /select for preparation/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByText(/1 case\(s\) not actively tracking/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).toHaveBeenCalledWith(
      "test-analyst", "usr-synthetic-1", true
    );
  });

  it("continues past a retired job and retries only failed selections while preserving successful private agents", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic-CV.pdf", sha256: "batch-cv",
    });
    const lateRows = ["job-retired", "job-current", "job-unavailable"].map((key, index) => ({
      ...tailored.recommendations[0],
      canonical_key: key,
      job: { ...listing.job, role_title: ["Retired IT trainee", "Current QA Tester", "Uncertain Data Engineer"][index] },
    }));
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic-CV.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Data Analyst"], detected_topics: [],
      recommended: lateRows, other_jobs: [], current_jobs_count: 3,
      recommended_count: 3, other_jobs_count: 0,
      selected_job: null,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    vi.mocked(api.startApplicationWorkspace)
      .mockRejectedValueOnce(new Error("Retired posting"))
      .mockResolvedValueOnce({
        workspace: { workspace_id: "kit-current" }, created: true,
        agent_tracking: { requested: true, state: "active", created: true,
          external_actions_performed: 0, worker_wake_verified: false },
      } as never)
      .mockRejectedValueOnce(new Error("Provider source unavailable"))
      .mockResolvedValueOnce({
        workspace: { workspace_id: "kit-retired-reconciled" }, created: false,
        agent_tracking: { requested: true, state: "paused", created: false,
          external_actions_performed: 0, worker_wake_verified: false },
      } as never)
      .mockResolvedValueOnce({
        workspace: { workspace_id: "kit-unavailable" }, created: true,
        agent_tracking: { requested: true, state: "unavailable", created: false,
          external_actions_performed: 0, worker_wake_verified: false },
      } as never);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Automatic.*AutoApply/i }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    expect(selectors).toHaveLength(3);
    for (const checkbox of selectors) fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByRole("button", { name: /retry 2 failed jobs/i })).toBeTruthy());
    expect((selectors[0] as HTMLInputElement).checked).toBe(true);
    expect((selectors[1] as HTMLInputElement).checked).toBe(false);
    expect((selectors[2] as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
    expect(screen.getByRole("button", { name: /open prepared applications/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /retry 2 failed jobs/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(5));
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(1, "job-retired", "usr-synthetic-1", true);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(2, "job-current", "usr-synthetic-1", true);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(3, "job-unavailable", "usr-synthetic-1", true);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(4, "job-retired", "usr-synthetic-1", true);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(5, "job-unavailable", "usr-synthetic-1", true);
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByText(/1 case\(s\) paused/i)).toBeTruthy();
    expect(screen.getByText(/1 case\(s\) not actively tracking/i)).toBeTruthy();
    expect(screen.getByText(/No applications were sent to employers/i)).toBeTruthy();
  });

  it("stops an AutoApply batch on a same-email identity switch before trying the next job", async () => {
    const changeAccount = switchableSession();
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic-CV.pdf", sha256: "batch-account-cv",
    });
    const twoRows = ["first-job", "second-job"].map((key, index) => ({
      ...tailored.recommendations[0],
      canonical_key: key,
      job: { ...listing.job, role_title: ["Junior Business Analyst", "Junior Software Tester"][index] },
    }));
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic-CV.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Business Analyst"], detected_topics: [],
      recommended: twoRows, other_jobs: [], current_jobs_count: 2,
      recommended_count: 2, other_jobs_count: 0,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    let finishFirst!: (result: unknown) => void;
    vi.mocked(api.startApplicationWorkspace).mockImplementationOnce(
      () => new Promise((resolve) => { finishFirst = resolve; }) as never
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Automatic.*AutoApply/i }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    fireEvent.click(selectors[0]);
    fireEvent.click(selectors[1]);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1));
    changeAccount();
    await act(async () => {
      finishFirst({
        workspace: { workspace_id: "kit-first-other-account" }, created: true,
        agent_tracking: { requested: true, state: "active", created: true,
          external_actions_performed: 0, worker_wake_verified: false },
      });
    });
    await waitFor(() => expect(screen.getByText(/signed-in account changed or could not be verified/i)).toBeTruthy());
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });

  it("SP50 Stop honors the current private request but skips every later selected job", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic.pdf", sha256: "sp50-stop",
    });
    const candidates = ["one", "two", "three"].map((key) => ({
      ...tailored.recommendations[0],
      canonical_key: "job-" + key,
      job: { ...listing.job, role_title: "Junior Data Analyst " + key },
    }));
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Data Analyst"], detected_topics: [],
      recommended: candidates, other_jobs: [], current_jobs_count: 3,
      recommended_count: 3, other_jobs_count: 0,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    let finishFirst!: (value: unknown) => void;
    vi.mocked(api.startApplicationWorkspace).mockImplementationOnce(
      () => new Promise((resolve) => { finishFirst = resolve; }) as never
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", {
      name: /Automatic.*AutoApply/i,
    }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    selectors.forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /^stop after current job$/i }));
    expect(screen.getByText(/Stop requested; current job may still complete/i)).toBeTruthy();
    await act(async () => {
      finishFirst({
        workspace: { workspace_id: "kit-first" }, created: true,
        agent_tracking: { requested: true, state: "active", created: true,
          external_actions_performed: 0, worker_wake_verified: false },
      });
    });
    expect(await screen.findByText(/2 job\(s\) were not started after Stop/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1);
    expect((selectors[0] as HTMLInputElement).checked).toBe(false);
    expect((selectors[1] as HTMLInputElement).checked).toBe(true);
    expect((selectors[2] as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /continue 2 remaining jobs/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(3));
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(
      2, "job-two", "usr-synthetic-1", true,
    );
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(
      3, "job-three", "usr-synthetic-1", true,
    );
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByText(/No applications were sent to employers/i)).toBeTruthy();
  });

  it("SP50 retries only transient failures; 404 remains review-required across retries", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic.pdf", sha256: "sp50-error",
    });
    const candidates = ["missing", "busy"].map((key) => ({
      ...tailored.recommendations[0],
      canonical_key: "job-" + key,
      job: { ...listing.job, role_title: "Junior QA " + key },
    }));
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Software Tester"], detected_topics: [],
      recommended: candidates, other_jobs: [], current_jobs_count: 2,
      recommended_count: 2, other_jobs_count: 0,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    vi.mocked(api.startApplicationWorkspace)
      .mockRejectedValueOnce(Object.assign(new Error("RAW_JOB_SECRET"), { status: 404 }))
      .mockRejectedValueOnce(Object.assign(new Error("RAW_SERVER_SECRET"), { status: 503 }))
      .mockResolvedValueOnce({
        workspace: { workspace_id: "kit-busy-ready" }, created: true,
        agent_tracking: { requested: true, state: "active", created: true,
          external_actions_performed: 0, worker_wake_verified: false },
      } as never);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", {
      name: /Automatic.*AutoApply/i,
    }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    screen.getAllByRole("checkbox", { name: /select for preparation/i })
      .forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByText(/This posting could not be found/i)).toBeTruthy();
    expect(screen.getByText(/private preparation service is temporarily unavailable/i)).toBeTruthy();
    expect(screen.queryByText(/RAW_JOB_SECRET/)).toBeNull();
    expect(screen.queryByText(/RAW_SERVER_SECRET/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /retry 1 failed job/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(3));
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(
      3, "job-busy", "usr-synthetic-1", true,
    );
    expect(await screen.findByRole("button", { name: /review blocked jobs first/i })).toBeTruthy();
    expect(screen.getByText(/This posting could not be found/i)).toBeTruthy();
    expect(screen.queryByTestId("application-editor")).toBeNull();
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("button", { name: /open prepared applications/i })).toBeTruthy();
  });

  it("SP50 stops on a general 403 authorization failure without attempting later jobs", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic.pdf", sha256: "sp50-denied",
    });
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Data Analyst"], detected_topics: [],
      recommended: [
        { ...tailored.recommendations[0], canonical_key: "denied-1" },
        { ...tailored.recommendations[0], canonical_key: "denied-2" },
      ], other_jobs: [], current_jobs_count: 2,
      recommended_count: 2, other_jobs_count: 0,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    vi.mocked(api.startApplicationWorkspace).mockRejectedValueOnce(
      Object.assign(new Error("privileged error not disclosed"), { status: 403 }),
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", {
      name: /Automatic.*AutoApply/i,
    }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    screen.getAllByRole("checkbox", { name: /select for preparation/i })
      .forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByText(/Private preparation access is unavailable/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/privileged error not disclosed/i)).toBeNull();
  });

  it("SP55 retains private draft progress after a later 403 and never attempts subsequent jobs", async () => {
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "synthetic.pdf", sha256: "sp55-partial-access",
    });
    const candidates = ["permitted", "denied", "unstarted"].map((key) => ({
      ...tailored.recommendations[0],
      canonical_key: "job-" + key,
      job: { ...listing.job, role_title: "Junior Analyst " + key },
    }));
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      cv_present: true, cv_filename: "synthetic.pdf", match_mode: "cv_text_signals",
      detected_roles: ["Data Analyst"], detected_topics: [],
      recommended: candidates, other_jobs: [], current_jobs_count: 3,
      recommended_count: 3, other_jobs_count: 0,
      matched_from: "local_cv_text_not_approved_evidence",
      qualifications_verified: false, employer_actions_performed: false,
    });
    vi.mocked(api.startApplicationWorkspace)
      .mockResolvedValueOnce({
        workspace: { workspace_id: "sp55-first-owner-draft" }, created: true,
        agent_tracking: { requested: true, state: "active", created: true,
          external_actions_performed: 0, worker_wake_verified: false },
      } as never)
      .mockRejectedValueOnce(
        Object.assign(new Error("PRIVATE_PROVIDER_SECRET"), { status: 403 }),
      );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", {
      name: /Automatic.*AutoApply/i,
    }));
    await screen.findByRole("heading", { name: "Jobs from your CV" });
    const selectors = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    selectors.forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByText(/Access was denied during private preparation/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(2);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(1, "job-permitted", "usr-synthetic-1", true);
    expect(api.startApplicationWorkspace).toHaveBeenNthCalledWith(2, "job-denied", "usr-synthetic-1", true);
    expect((selectors[0] as HTMLInputElement).checked).toBe(false);
    expect((selectors[1] as HTMLInputElement).checked).toBe(true);
    expect((selectors[2] as HTMLInputElement).checked).toBe(true);
    expect((selectors[1] as HTMLInputElement).disabled).toBe(true);
    expect((selectors[2] as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: /access denied.*reload to continue/i }))
      .toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: /open prepared applications/i })).toBeTruthy();
    expect(screen.queryByText(/PRIVATE_PROVIDER_SECRET/)).toBeNull();
    expect(screen.getByText(/1 private draft\(s\) remain saved/i)).toBeTruthy();
    expect(screen.getByText(/No applications were sent to employers/i)).toBeTruthy();
    // SP56: partial success must focus the exact newly prepared workspace,
    // not the oldest or first unrelated application in the private ledger.
    fireEvent.click(screen.getByRole("button", { name: /open prepared applications/i }));
    expect(screen.getByTestId("application-editor").getAttribute("data-workspace"))
      .toBe("sp55-first-owner-draft");
    expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(2);
  });

  it("keeps General selected while optional user-profile requests finish in the background", async () => {
    let finishCV = () => {};
    vi.mocked(api.getCV).mockImplementationOnce(() => new Promise((resolve) => {
      finishCV = () => resolve({ present: false });
    }));

    render(<App />);
    fireEvent.click(await screen.findByText(/Advanced: customize search preferences/i));
    const generalRadio = await screen.findByRole("radio", { name: /general job search/i });
    fireEvent.click(generalRadio);
    expect((generalRadio as HTMLInputElement).checked).toBe(true);

    // This is the async first-use hydration race observed intermittently
    // under CI load. No CV or model is required for General search.
    await act(async () => { finishCV(); });
    expect((screen.getByRole("radio", { name: /general job search/i }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /browse all jobs/i }));
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledWith(
      expect.objectContaining({ mode: "general", expected_revision: 0 }), "usr-synthetic-1"
    ));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
  });

  it("prevents manual refresh from replacing an in-flight General-mode save", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    let finishSave: (value: SearchPreferences) => void = () => {
      throw new Error("Expected pending preference save");
    };
    vi.mocked(api.updateSearchPreferences).mockImplementationOnce(() =>
      new Promise<SearchPreferences>((resolve) => { finishSave = resolve; })
    );

    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    expect(screen.getByRole("button", { name: /saving/i }).hasAttribute("disabled")).toBe(true);
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledTimes(1));

    const dashboardReadsBefore = vi.mocked(api.getDashboard).mock.calls.length;
    const preferencesReadsBefore = vi.mocked(api.getSearchPreferences).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    expect(api.getDashboard).toHaveBeenCalledTimes(dashboardReadsBefore);
    expect(api.getSearchPreferences).toHaveBeenCalledTimes(preferencesReadsBefore);

    await act(async () => {
      currentPrefs = {
        ...currentPrefs, completed: true, mode: "general",
        revision: 2, updated_at: "2026-10-12T06:00:00Z",
      };
      finishSave(currentPrefs);
    });
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
    expect(currentPrefs.mode).toBe("general");

    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(api.getSearchPreferences).toHaveBeenCalledTimes(
      preferencesReadsBefore + 1
    ));
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
  });

  it("ignores an earlier unresolved preference GET completed after saving new criteria", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();

    const staleSnapshot = { ...currentPrefs };
    let finishOldRead: (value: SearchPreferences) => void = () => {
      throw new Error("Expected earlier pending preference read");
    };
    let oldReadStarted = false;
    vi.mocked(api.getSearchPreferences).mockImplementationOnce(() =>
      new Promise<SearchPreferences>((resolve) => {
        finishOldRead = resolve;
        oldReadStarted = true;
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(oldReadStarted).toBe(true));

    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
    expect(currentPrefs.mode).toBe("general");

    await act(async () => { finishOldRead(staleSnapshot); });
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
    expect(currentPrefs.mode).toBe("general");
  });

  it("releases the refresh lock after a failed preference save", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    vi.mocked(api.updateSearchPreferences).mockRejectedValueOnce(
      new Error("Synthetic revision conflict")
    );
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Synthetic revision conflict/);
    const priorReads = vi.mocked(api.getSearchPreferences).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(api.getSearchPreferences).toHaveBeenCalledTimes(
      priorReads + 1
    ));
    expect((screen.getByRole("radio", { name: /general job search/i }) as HTMLInputElement).checked)
      .toBe(true);
    expect(currentPrefs.mode).toBe("personalized");
  });

  it("does not send preference changes when the current session cannot be verified", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    vi.mocked(api.getSession).mockRejectedValueOnce(new Error("Synthetic authentication expiry"));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));

    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.getByText(/signed-in account changed or could not be verified/i)).toBeTruthy();
    expect(api.updateSearchPreferences).not.toHaveBeenCalled();
    expect(currentPrefs.mode).toBe("personalized");
  });

  it("fails closed when a different account takes over during a preference PUT", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    let currentUser = "usr-account-a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@smartploy.invalid",
      user_id: currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture",
    }));
    let finishSave: (value: SearchPreferences) => void = () => {
      throw new Error("Expected pending save");
    };
    vi.mocked(api.updateSearchPreferences).mockImplementationOnce(() =>
      new Promise<SearchPreferences>((resolve) => { finishSave = resolve; })
    );
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledTimes(1));
    currentUser = "usr-account-b";
    await act(async () => {
      finishSave({
        ...currentPrefs, mode: "general", revision: 2,
        updated_at: "2026-10-12T08:00:00Z",
      });
    });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.getByText(/signed-in account changed or could not be verified/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
    expect(api.getSearchResults).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
  });

  it("does not publish stale discovery when identity flips after the preference PUT", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1,
    };
    let currentUser = "usr-account-a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@smartploy.invalid",
      user_id: currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture",
    }));
    let finishResults: (value: SearchResults) => void = () => {
      throw new Error("Expected pending results");
    };
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    vi.mocked(api.getSearchResults).mockImplementationOnce(() =>
      new Promise<SearchResults>((resolve) => { finishResults = resolve; })
    );
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledTimes(1));
    currentUser = "usr-account-b";
    await act(async () => { finishResults(general); });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText(/1 current job listings/i)).toBeNull();
  });

  it("saves new personalized settings and transparently changes ranked results", async () => {
    render(<App />);
    fireEvent.click(await screen.findByText(/Advanced: customize search preferences/i));
    fireEvent.change(await screen.findByPlaceholderText(/Data analyst, Junior software tester/), {
      target: { value: "Data Analyst" },
    });
    fireEvent.click(screen.getByRole("button", { name: /show my matched jobs/i }));
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    expect(currentPrefs.mode).toBe("personalized");

    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    expect(screen.getByRole("heading", { name: "Job search preferences" })).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    await waitFor(() => expect(currentPrefs.mode).toBe("general"));
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
  });

  it("discards an old CV upload response after the account changes", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    const switchToB = switchableSession();
    let complete: (value: Awaited<ReturnType<typeof api.uploadCV>>) => void = () => {
      throw new Error("Upload did not start");
    };
    vi.mocked(api.uploadCV).mockImplementationOnce(() =>
      new Promise(resolve => { complete = resolve; })
    );
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Select CV to upload"), { target: {
      files: [new File(["synthetic"], "PRIVATE-ACCOUNT-A.pdf", { type: "application/pdf" })],
    } });
    await waitFor(() => expect(api.uploadCV).toHaveBeenCalledTimes(1));
    switchToB();
    await act(async () => {
      complete({ present: true, filename: "PRIVATE-ACCOUNT-A.pdf",
        text_preview: "ACCOUNT-A-PRIVATE-CV-TEXT" });
    });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-ACCOUNT-A.pdf")).toBeNull();
    expect(screen.getByText(/could not be verified during a private action/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.queryByText("PRIVATE-ACCOUNT-A.pdf")).toBeNull();
  });

  it("does not open a delayed account A application workspace for account B", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getCV).mockResolvedValue({ present: true, filename: "PRIVATE-ACCOUNT-A.pdf",
      sha256: "synthetic-owner-a-only" });
    const switchToB = switchableSession();
    let complete: (value: Awaited<ReturnType<typeof api.startApplicationWorkspace>>) => void = () => {
      throw new Error("Workspace did not start");
    };
    vi.mocked(api.startApplicationWorkspace).mockImplementationOnce(() =>
      new Promise(resolve => { complete = resolve; })
    );
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Apply manually$/ }));
    await screen.findByRole("button", { name: "Choose this job" });
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByRole("button", { name: "Choose this job" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Save application draft" }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledTimes(1));
    switchToB();
    await act(async () => {
      complete({ workspace: { workspace_id: "PRIVATE-A-DRAFT" }, created: true } as never);
    });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByTestId("application-editor")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My applications" }));
    expect((await screen.findByTestId("application-editor")).getAttribute("data-workspace")).toBe("");
  });

  it("clears an old-account fact entry when a save finishes after account switching", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    const switchToB = switchableSession();
    let complete: (value: Awaited<ReturnType<typeof api.createFact>>) => void = () => {
      throw new Error("Fact save did not start");
    };
    vi.mocked(api.createFact).mockImplementationOnce(() =>
      new Promise(resolve => { complete = resolve; })
    );
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My CV & documents" }));
    fireEvent.change(screen.getByPlaceholderText(/Python, Finnish B2, data analytics/i), {
      target: { value: "PRIVATE-ACCOUNT-A-FACT" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save for review" }));
    await waitFor(() => expect(api.createFact).toHaveBeenCalledTimes(1));
    switchToB();
    await act(async () => { complete({ fact: { value: "PRIVATE-ACCOUNT-A-FACT" } } as never); });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-ACCOUNT-A-FACT")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My CV & documents" }));
    expect((screen.getByPlaceholderText(/Python, Finnish B2, data analytics/i) as HTMLInputElement).value).toBe("");
  });


  it("shows a CV and private saved job even if the optional local AI endpoint never replies", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getLocalAIStatus).mockImplementation(
      () => new Promise(() => { /* synthetic non-responding local model */ })
    );
    vi.mocked(api.getCV).mockResolvedValue({
      present: true, filename: "SYNTHETIC-READY-CV.pdf",
      size_bytes: 1024, text_preview: "Synthetic CV contents",
    } as never);
    personalJobs = [{
      saved_job_id: "fixture-saved-1", created_at: "2026-10-17T08:00:00Z",
      company: "Fictional Employer Oy", role_title: "Private saved QA opportunity",
      location: "Helsinki", description: "Testing only",
      application_url: "https://jobs.example.fi/qa",
      private: true, employer_availability_verified: false,
      external_actions_authorized: false,
    }];
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My CV & documents" }));
    expect((await screen.findAllByText("SYNTHETIC-READY-CV.pdf")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(await screen.findByText("Private saved QA opportunity")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Check posting/ }).getAttribute("href"))
      .toBe("https://jobs.example.fi/qa");
  });

  it("does not show an executable posting link from untrusted private bookmark data", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    personalJobs = [{
      saved_job_id: "fixture-unsafe-1", created_at: "2026-10-17T08:00:00Z",
      company: "Fictional Employer Oy", role_title: "Untrusted saved job",
      location: "Helsinki", description: "Testing only",
      application_url: "javascript:alert('synthetic')",
      private: true, employer_availability_verified: false,
      external_actions_authorized: false,
    }];
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(await screen.findByText("Untrusted saved job")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Check posting/ })).toBeNull();
    expect(screen.getByText("Posting link unavailable")).toBeTruthy();
  });

  it("discards an old account's delayed optional AI status after a newer workspace refresh", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    const switchToB = switchableSession();
    let finishOld: (value: Awaited<ReturnType<typeof api.getLocalAIStatus>>) => void = () => {
      throw new Error("First optional status never started");
    };
    vi.mocked(api.getLocalAIStatus).mockImplementationOnce(() =>
      new Promise(resolve => { finishOld = resolve; })
    );
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    await waitFor(() => expect(api.getLocalAIStatus).toHaveBeenCalledTimes(1));
    switchToB();
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(api.getLocalAIStatus).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Refresh workspace" }).hasAttribute("disabled")).toBe(false)
    );
    fireEvent.click(screen.getByRole("button", { name: "CV & AI tools" }));
    expect(await screen.findByText(/ObumAI service integration is not configured/i)).toBeTruthy();
    await act(async () => {
      finishOld({
        configured: true, ready: true, provider: "local_obumai_ollama",
        model: "SYNTHETIC-A-ONLY-MODEL", external_ai_forwarding: false,
      });
    });
    expect(screen.getByText(/ObumAI service integration is not configured/i)).toBeTruthy();
  });

  it("saves a job privately, shows it separately, and removes it without shared ingestion", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(screen.getByRole("heading", { name: "Your saved opportunities" })).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Save job" })[0]);
    fireEvent.change(screen.getByPlaceholderText("e.g. Junior Data Analyst"), {
      target: { value: "Private UX Researcher" },
    });
    fireEvent.change(screen.getByPlaceholderText("Employer name"), {
      target: { value: "Fictional Studio Oy" },
    });
    fireEvent.change(screen.getByPlaceholderText("Paste the responsibilities and key requirements here."), {
      target: { value: "Design private research studies" },
    });
    const form = screen.getByRole("dialog").querySelector("form");
    if (!form) throw new Error("Private bookmark form missing");
    fireEvent.submit(form);

    expect(await screen.findByText("Private UX Researcher")).toBeTruthy();
    expect(api.addManualJob).toHaveBeenCalledWith(expect.objectContaining({
      role_title: "Private UX Researcher", company: "Fictional Studio Oy",
    }), "usr-synthetic-1");
    expect(personalJobs).toHaveLength(1);
    expect(personalJobs[0].private).toBe(true);
    expect(screen.getByText(/Private bookmarks, not employer-verified/i)).toBeTruthy();
    expect(screen.queryByText(/87% search match/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Remove saved job Private UX Researcher" }));
    await waitFor(() => expect(api.deletePrivateSavedJob).toHaveBeenCalledWith(
      "saved-synthetic-1", "usr-synthetic-1"
    ));
    await waitFor(() => expect(screen.queryByText("Private UX Researcher")).toBeNull());
    expect(personalJobs).toHaveLength(0);
  });

  it("does not show an old-account saved-job success notice after refresh changes account", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    let currentUser = "a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@example.invalid",
      user_id: "user-" + currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture",
    }));
    vi.mocked(api.getPrivateSavedJobs).mockImplementation(async () => ({
      jobs: currentUser === "a" ? [...personalJobs] : [],
      count: currentUser === "a" ? personalJobs.length : 0, private: true,
    }));
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    const originalReads = vi.mocked(api.getSearchPreferences).mock.calls.length;

    let finishReload: (value: SearchPreferences) => void = () => {
      throw new Error("Expected pending search-preference read");
    };
    vi.mocked(api.getSearchPreferences).mockImplementationOnce(() =>
      new Promise<SearchPreferences>((resolve) => { finishReload = resolve; })
    );
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Save job" })[0]);
    fireEvent.change(screen.getByPlaceholderText("e.g. Junior Data Analyst"), {
      target: { value: "PRIVATE-ACCOUNT-A-JOB" },
    });
    fireEvent.change(screen.getByPlaceholderText("Employer name"), {
      target: { value: "Synthetic Studio" },
    });
    fireEvent.change(screen.getByPlaceholderText("Paste the responsibilities and key requirements here."), {
      target: { value: "Private fictional work only" },
    });
    const form = screen.getByRole("dialog").querySelector("form");
    if (!form) throw new Error("Bookmark modal missing");
    fireEvent.submit(form);
    await waitFor(() => expect(api.getSearchPreferences).toHaveBeenCalledTimes(
      originalReads + 1
    ));
    currentUser = "b";
    await act(async () => { finishReload({ ...currentPrefs }); });

    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.queryByText(/Job saved privately to your account/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(screen.queryByText("PRIVATE-ACCOUNT-A-JOB")).toBeNull();
    expect(screen.getByText(/No private saved jobs yet/i)).toBeTruthy();
  });

  it("clears private saved jobs when same-email account identity changes", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    const accountA: PrivateSavedJob = {
      saved_job_id: "saved-a", company: "Example A", role_title: "SECRET-A-BOOKMARK",
      location: "Helsinki", description: "A only", application_url: "",
      created_at: "2026-10-12T10:00:00Z", private: true,
      employer_availability_verified: false, external_actions_authorized: false,
    };
    let currentUser = "a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@example.invalid",
      user_id: "user-" + currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture",
    }));
    vi.mocked(api.getPrivateSavedJobs).mockImplementation(async () => ({
      jobs: currentUser === "a" ? [accountA] : [],
      count: currentUser === "a" ? 1 : 0, private: true,
    }));
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(await screen.findByText("SECRET-A-BOOKMARK")).toBeTruthy();

    currentUser = "b";
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(screen.queryByText("SECRET-A-BOOKMARK")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Find jobs" }));
    expect(screen.getByText(/No private saved jobs yet/i)).toBeTruthy();
    expect(screen.queryByText("SECRET-A-BOOKMARK")).toBeNull();
  });

  it("clears same-email account A's private CV and facts before showing account B", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    let currentUser = "usr-account-a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@smartploy.invalid",
      user_id: currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture"
    }));
    vi.mocked(api.getCV)
      .mockResolvedValueOnce({ present: true, filename: "PRIVATE-OLD-ACCOUNT-CV.docx" })
      .mockRejectedValueOnce(new Error("new account CV API unavailable"));
    vi.mocked(api.getProfileFacts)
      .mockResolvedValueOnce({ facts: [{
        fact_id: "old-fact", fact_type: "skill", value: "PRIVATE-OLD-ACCOUNT-FACT",
        approved: true, source: "user-entered", confidence: 1,
        created_at: "2026-10-11T10:00:00Z",
      }], count: 1 })
      .mockRejectedValueOnce(new Error("new account profile unavailable"));

    render(<App />);
    expect(await screen.findByText("PRIVATE-OLD-ACCOUNT-CV.docx")).toBeTruthy();
    expect(screen.getByText("PRIVATE-OLD-ACCOUNT-FACT")).toBeTruthy();
    currentUser = "usr-account-b";
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));

    await waitFor(() => expect(screen.queryByText("PRIVATE-OLD-ACCOUNT-CV.docx")).toBeNull());
    expect(screen.queryByText("PRIVATE-OLD-ACCOUNT-FACT")).toBeNull();
    expect(await screen.findByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Start here$/i })).toBeTruthy();
  });

  it("fails closed when the signed-in identity flips during essential workspace reads", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    let currentUser = "usr-account-a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@smartploy.invalid",
      user_id: currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture"
    }));
    vi.mocked(api.getCV).mockImplementation(async () => ({
      present: true, filename: currentUser === "usr-account-a"
        ? "PRIVATE-OLD-A.pdf" : "PRIVATE-NEW-B.pdf"
    }));
    render(<App />);
    expect(await screen.findByText("PRIVATE-OLD-A.pdf")).toBeTruthy();

    let finishRead: (value: SearchPreferences) => void = () => {
      throw new Error("Expected pending preference read");
    };
    let started = false;
    vi.mocked(api.getSearchPreferences).mockImplementationOnce(
      () => new Promise<SearchPreferences>((resolve) => {
        finishRead = resolve;
        started = true;
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(started).toBe(true));
    currentUser = "usr-account-b";
    await act(async () => { finishRead({ ...currentPrefs }); });

    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-OLD-A.pdf")).toBeNull();
    expect(screen.getByText(/signed-in account changed during refresh/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("PRIVATE-NEW-B.pdf")).toBeTruthy();
    expect(screen.queryByText("PRIVATE-OLD-A.pdf")).toBeNull();
  });

  it("rejects an old-account CV response if identity changes during optional loading", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    let currentUser = "usr-account-a";
    vi.mocked(api.getSession).mockImplementation(async () => ({
      authenticated: true, email: "shared@smartploy.invalid",
      user_id: currentUser, profile_id: "profile-" + currentUser,
      auth_source: "fixture"
    }));
    vi.mocked(api.getCV).mockResolvedValueOnce({
      present: true, filename: "PRIVATE-OLD-A.pdf"
    });
    render(<App />);
    expect(await screen.findByText("PRIVATE-OLD-A.pdf")).toBeTruthy();

    let finishCV: (value: { present: boolean; filename: string }) => void = () => {
      throw new Error("Expected pending CV request");
    };
    let started = false;
    vi.mocked(api.getCV).mockImplementationOnce(
      () => new Promise((resolve) => { finishCV = resolve; started = true; })
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    await waitFor(() => expect(started).toBe(true));
    currentUser = "usr-account-b";
    await act(async () => {
      finishCV({ present: true, filename: "STALE-PRIVATE-A-RESPONSE.pdf" });
    });

    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-OLD-A.pdf")).toBeNull();
    expect(screen.queryByText("STALE-PRIVATE-A-RESPONSE.pdf")).toBeNull();
    expect(screen.getByText(/signed-in account changed during profile loading/i)).toBeTruthy();
  });

  it("rejects email-only session responses without stable server identity", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated: true, email: "shared@smartploy.invalid", auth_source: "fixture"
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.getByText(/Authenticated account identity is unavailable/i)).toBeTruthy();
    expect(api.getCV).not.toHaveBeenCalled();
    expect(api.getSearchPreferences).not.toHaveBeenCalled();
  });

  it("removes stale private dashboard content when essential authentication fails", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getDashboard)
      .mockResolvedValueOnce({
        top_matches: [], possible_matches: [], source_health: [],
        worker: { ready: true, count: 0, tasks: [] },
        applications: { awaiting_review: 0, actually_submitted: 0 },
      } as never)
      .mockRejectedValueOnce(new Error("Session expired"));
    vi.mocked(api.getCV).mockResolvedValueOnce({
      present: true, filename: "PRIVATE-OLD-CV.pdf",
    });

    render(<App />);
    expect(await screen.findByText("PRIVATE-OLD-CV.pdf")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh workspace" }));
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText("PRIVATE-OLD-CV.pdf")).toBeNull();
    expect(screen.getByText("Session expired")).toBeTruthy();
  });


  it("requires explicit per-job consent in Settings and supports account-bound withdrawal", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getJobs).mockResolvedValue({
      jobs: [{
        canonical_key: "test-analyst", source_current: true,
        source_ids: ["test-ats"], posted_at: "2026-10-11T10:00:00Z",
        first_seen_at: "2026-10-11T10:00:00Z", job: listing.job,
      }], count: 1,
    });
    const consents: Array<import("./types").JobAIProcessingConsent> = [];
    vi.mocked(api.getJobAIConsents).mockImplementation(async () => ({
      consents: [...consents], count: consents.length, private: true,
      unattended_processing_enabled: false,
    }));
    vi.mocked(api.grantJobAIConsent).mockImplementation(async (key, userId) => {
      expect(key).toBe("test-analyst");
      expect(userId).toBe("usr-synthetic-1");
      const item: import("./types").JobAIProcessingConsent = {
        consent_id: "consent-fixture", canonical_key: key, processor: "obumai",
        purpose: "application_draft", mode: "unattended",
        job_snapshot_sha256: "a".repeat(64), evidence_sha256: "b".repeat(64),
        revision: 1, granted_at: "2026-10-17T10:00:00Z", revoked_at: "",
        active: true, processing_started: false,
        employer_actions_authorized: false,
      };
      consents.push(item);
      return { consent: item, created_or_updated: true,
        processing_started: false, external_actions_authorized: false };
    });
    vi.mocked(api.revokeJobAIConsent).mockImplementation(async (id, userId) => {
      expect(id).toBe("consent-fixture");
      expect(userId).toBe("usr-synthetic-1");
      const revoked = { ...consents[0], revision: 2, active: false,
        revoked_at: "2026-10-17T10:05:00Z" };
      consents[0] = revoked;
      return { consent: revoked, revoked: true };
    });

    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    const jobOption = await screen.findByRole("option", {
      name: /Junior Data Analyst — Example Oy/i,
    });
    const jobSelect = screen.getByRole("combobox", {
      name: /choose a currently approved job/i,
    });
    fireEvent.change(jobSelect, { target: { value: (jobOption as HTMLOptionElement).value } });
    const savePermission = screen.getByRole("button", {
      name: /save job-specific permission/i,
    }) as HTMLButtonElement;
    expect(savePermission.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: /i explicitly allow obumai/i }));
    fireEvent.click(savePermission);
    await waitFor(() => expect(api.grantJobAIConsent).toHaveBeenCalledWith(
      "test-analyst", "usr-synthetic-1",
    ));
    await waitFor(() => expect(screen.getByRole("button", {
      name: /withdraw permission/i,
    })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /withdraw permission/i }));
    await waitFor(() => expect(api.revokeJobAIConsent).toHaveBeenCalledWith(
      "consent-fixture", "usr-synthetic-1",
    ));
    await waitFor(() => expect(screen.getByText("Withdrawn")).toBeTruthy());
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("isolates a failed optional profile API without locking out jobs", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getProfileFacts).mockRejectedValue(new Error("profile temporarily unavailable"));
    vi.mocked(api.getLocalAIStatus).mockRejectedValue(new Error("Ollama unavailable"));
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(await screen.findByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Apply manually$/ })).toBeTruthy();
  });
});


describe("first opt-in creates private IT applications immediately", () => {
  const openOptIn = async () => {
    render(<App />);
    fireEvent.click(await screen.findByText(/Advanced: customize search preferences/i));
    fireEvent.click(await screen.findByRole("button", { name: /Use nationwide junior IT & planning targets/i }));
    fireEvent.click(screen.getByRole("checkbox", {
      name: /Automatically prepare suitable job drafts/i,
    }));
    fireEvent.click(screen.getByRole("button", { name: /Show my matched jobs/i }));
  };


  it("runs the existing private draft scan immediately when an opted-in role changes", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.change(screen.getByPlaceholderText(/Data analyst, Junior software tester/i), {
      target: { value: "Junior Software Tester" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save search preferences/i }));
    await waitFor(() => expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1));
    expect(api.prepareMyMatchingDrafts).toHaveBeenCalledWith("usr-synthetic-1");
    expect(currentPrefs.roles).toEqual(["Junior Software Tester"]);
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("SP58 opens the exact new owner kit after first opt-in, not a prior default", async () => {
    const kit = "kit-" + "a".repeat(30);
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "prepared", checked: 1, eligible: 1, created: 1,
      created_workspace_ids: [kit], already_prepared: 0, stopped_on_opt_out: false,
      provider_calls: 0, employer_actions_performed: false,
      automatic_submission_authorized: false,
    });
    await openOptIn();
    const editor = await screen.findByTestId("application-editor");
    expect(editor.getAttribute("data-workspace")).toBe(kit);
    expect(screen.getByText(/Opened the first new draft for review/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
    expect(api.grantJobAIConsent).not.toHaveBeenCalled();
  });

  it("SP58 direct opt-in rescan focuses the exact created kit after private POST", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    const kit = "kit-" + "b".repeat(30);
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "prepared", checked: 1, eligible: 1, created: 1,
      created_workspace_ids: [kit], already_prepared: 0, stopped_on_opt_out: false,
      provider_calls: 0, employer_actions_performed: false,
      automatic_submission_authorized: false,
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {
      name: /Find and prepare matching drafts now/i,
    }));
    const editor = await screen.findByTestId("application-editor");
    expect(editor.getAttribute("data-workspace")).toBe(kit);
    expect(screen.getByText(/Opened the first new draft for review/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("SP58 never guesses a workspace from legacy or contradictory scan results", async () => {
    const older = "kit-" + "c".repeat(30);
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "prepared", checked: 2, eligible: 2, created: 2,
      created_workspace_ids: [older], already_prepared: 0, stopped_on_opt_out: false,
      provider_calls: 0, employer_actions_performed: false,
      automatic_submission_authorized: false,
    });
    await openOptIn();
    const editor = await screen.findByTestId("application-editor");
    expect(editor.getAttribute("data-workspace")).toBe("");
    expect(screen.getByText(/Find your new drafts in My applications/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("SP58 shows a saved draft made before revocation, without restarting automation", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    const kit = "kit-" + "d".repeat(30);
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "disabled_after_revocation", checked: 2, eligible: 2, created: 1,
      created_workspace_ids: [kit], already_prepared: 0, stopped_on_opt_out: true,
      provider_calls: 0, employer_actions_performed: false,
      automatic_submission_authorized: false,
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {
      name: /Find and prepare matching drafts now/i,
    }));
    const editor = await screen.findByTestId("application-editor");
    expect(editor.getAttribute("data-workspace")).toBe(kit);
    expect(screen.getByText(/Automatic preparation stopped after you withdrew permission/i))
      .toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("never starts an automatic draft after saving search settings without opt-in", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: false,
    };
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Advanced settings" }));
    fireEvent.change(screen.getByPlaceholderText(/Data analyst, Junior software tester/i), {
      target: { value: "Junior Software Tester" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save search preferences/i }));
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Your search targets were saved/i)).toBeTruthy();
    expect(api.prepareMyMatchingDrafts).not.toHaveBeenCalled();
  });

  it("prepares matched drafts as soon as the user approves an existing career fact", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    const fact = {
      fact_id: "synthetic-fact-1", fact_type: "skill", value: "SQL",
      approved: false,
    };
    vi.mocked(api.getProfileFacts).mockImplementation(async () => ({
      facts: [{ ...fact }], count: 1,
    } as never));
    vi.mocked(api.approveFact).mockImplementation(async (_id, approved) => {
      fact.approved = approved;
      return { ...fact } as never;
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My CV & documents" }));
    expect(await screen.findByText("SQL")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.approveFact).toHaveBeenCalledWith(
      "synthetic-fact-1", true, "usr-synthetic-1"
    ));
    await waitFor(() => expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1));
    expect(api.prepareMyMatchingDrafts).toHaveBeenCalledWith("usr-synthetic-1");
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByText(/new matched IT application draft/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("prepares on newly approved evidence, never on unapproved evidence", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    const facts: Array<{fact_id:string;fact_type:string;value:string;approved:boolean}> = [];
    vi.mocked(api.getProfileFacts).mockImplementation(async () => ({
      facts: [...facts], count: facts.length,
    } as never));
    vi.mocked(api.createFact).mockImplementation(async (type, value, approved) => {
      const item = {
        fact_id: "fact-" + (facts.length + 1),
        fact_type: type, value, approved,
      };
      facts.push(item);
      return item as never;
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "My CV & documents" }));
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. Python, Finnish B2/i), {
      target: { value: "SQL" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save for review" }));
    await waitFor(() => expect(api.createFact).toHaveBeenCalledTimes(1));
    expect(api.prepareMyMatchingDrafts).not.toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. Python, Finnish B2/i), {
      target: { value: "Python" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /I confirm this information is accurate/i }));
    fireEvent.click(screen.getByRole("button", { name: "Save approved fact" }));
    await waitFor(() => expect(api.createFact).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });


  it("opens CV-first job matches after upload without silently submitting or starting drafts", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    vi.mocked(api.getProfileFacts).mockResolvedValue({
      facts: [{
        fact_id: "approved-skill-1", fact_type: "skill", value: "Python",
        approved: true, source: "user-entered", confidence: 1,
        created_at: "2026-10-20T10:00:00Z",
      }], count: 1,
    });
    const updatedCV = { present: true, filename: "synthetic-CV.pdf",
      size_bytes: 128, text_preview: "The user's CV for review" };
    vi.mocked(api.uploadCV).mockResolvedValue(updatedCV);
    vi.mocked(api.getCV).mockResolvedValue(updatedCV);
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Select CV to upload"), {
      target: { files: [new File(["fictional PDF"], "synthetic-CV.pdf", {
        type: "application/pdf",
      })] },
    });
    await waitFor(() => expect(api.uploadCV).toHaveBeenCalledWith(
      expect.objectContaining({ name: "synthetic-CV.pdf" }), "usr-synthetic-1"
    ));
    expect(await screen.findByRole("heading", { name: "Jobs from your CV" })).toBeTruthy();
    expect(screen.getByText("Your CV is connected. Choose a method to continue.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /save application draft/i })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /select for preparation/i })).toBeNull();
    await waitFor(() => expect(api.getCVJobMatches).toHaveBeenCalledTimes(1));
    expect(api.prepareMyMatchingDrafts).not.toHaveBeenCalled();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("never mistakes uploading an unreviewed CV for approval to AutoApply", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    const updatedCV = { present: true, filename: "unreviewed-CV.pdf",
      size_bytes: 128, text_preview: "Unapproved content only" };
    vi.mocked(api.uploadCV).mockResolvedValue(updatedCV);
    vi.mocked(api.getCV).mockResolvedValue(updatedCV);
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Select CV to upload"), {
      target: { files: [new File(["fictional PDF"], "unreviewed-CV.pdf", {
        type: "application/pdf",
      })] },
    });
    await waitFor(() => expect(api.uploadCV).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/CV uploaded\. Matching your CV against current jobs now/i)).toBeTruthy();
    expect(api.prepareMyMatchingDrafts).not.toHaveBeenCalled();
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });

  it("connects saved opt-in to the existing private draft engine with no second click", async () => {
    await openOptIn();
    await waitFor(() => expect(api.prepareMyMatchingDrafts).toHaveBeenCalledWith(
      "usr-synthetic-1"
    ));
    expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1);
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByText(/matched IT application draft\(s\) prepared privately/i)).toBeTruthy();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
    expect(api.grantJobAIConsent).not.toHaveBeenCalled();
  });

  it("keeps the saved preference and directs users without approved facts to their profile", async () => {
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "needs_approved_profile", checked: 0, eligible: 0, created: 0,
      already_prepared: 0, stopped_on_opt_out: false, provider_calls: 0,
      employer_actions_performed: false, automatic_submission_authorized: false,
    });
    await openOptIn();
    expect(await screen.findByText(/Approve your career facts to prepare your first applications/i)).toBeTruthy();
    expect(currentPrefs.auto_draft_enabled).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });

  it("saves opt-in even if the immediate scan fails, without pretending drafts exist", async () => {
    vi.mocked(api.prepareMyMatchingDrafts).mockRejectedValueOnce(new Error("PRIVATE-DATABASE-ERROR"));
    await openOptIn();
    expect(await screen.findByText(/first draft scan could not finish/i)).toBeTruthy();
    expect(screen.queryByText(/PRIVATE-DATABASE-ERROR/i)).toBeNull();
    expect(currentPrefs.auto_draft_enabled).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });

  it("never creates an application from a stale ATS cache on first opt-in", async () => {
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "needs_source_refresh", checked: 1, eligible: 0,
      created: 0, already_prepared: 0, stale_skipped: 1,
      stopped_on_opt_out: false, provider_calls: 0,
      employer_actions_performed: false, automatic_submission_authorized: false,
    });
    await openOptIn();
    expect(await screen.findByText(/have not been checked recently/i)).toBeTruthy();
    expect(currentPrefs.auto_draft_enabled).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("allows direct rescan only after newly verified source data is available", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "needs_source_refresh", checked: 1, eligible: 0,
      created: 0, already_prepared: 0, stale_skipped: 1,
      stopped_on_opt_out: false, provider_calls: 0,
      employer_actions_performed: false, automatic_submission_authorized: false,
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {
      name: /Find and prepare matching drafts now/i,
    }));
    expect(await screen.findByText(/source worker must refresh those postings/i)).toBeTruthy();
    expect(screen.queryByTestId("application-editor")).toBeNull();
    expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1);
  });

  it("never presents manual or unknown-source jobs as automatically prepared", async () => {
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "needs_trusted_source", checked: 1, eligible: 0,
      created: 0, already_prepared: 0, stale_skipped: 0,
      unverified_source_skipped: 1,
      stopped_on_opt_out: false, provider_calls: 0,
      employer_actions_performed: false, automatic_submission_authorized: false,
    });
    await openOptIn();
    expect(await screen.findByText(/manual or unverified sources/i)).toBeTruthy();
    expect(currentPrefs.auto_draft_enabled).toBe(true);
    expect(screen.queryByTestId("application-editor")).toBeNull();
    expect(api.startApplicationWorkspace).not.toHaveBeenCalled();
  });

  it("gives specific source-approval guidance on manual rescan", async () => {
    currentPrefs = {
      ...initial, completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 1, auto_draft_enabled: true,
    };
    vi.mocked(api.prepareMyMatchingDrafts).mockResolvedValueOnce({
      status: "needs_trusted_source", checked: 1, eligible: 0,
      created: 0, already_prepared: 0, stale_skipped: 0,
      unverified_source_skipped: 1,
      stopped_on_opt_out: false, provider_calls: 0,
      employer_actions_performed: false, automatic_submission_authorized: false,
    });
    render(<App />);
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {
      name: /Find and prepare matching drafts now/i,
    }));
    expect(await screen.findByText(/Automatic drafts require a recently refreshed, reviewed employer/i)).toBeTruthy();
    expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });

  it("discards an old account's in-flight first scan after session switch", async () => {
    const switchToB = switchableSession();
    let finish: (value: Awaited<ReturnType<typeof api.prepareMyMatchingDrafts>>) => void =
      () => { throw new Error("Expected a pending first scan"); };
    vi.mocked(api.prepareMyMatchingDrafts).mockImplementationOnce(
      () => new Promise(resolve => { finish = resolve; })
    );
    await openOptIn();
    await waitFor(() => expect(api.prepareMyMatchingDrafts).toHaveBeenCalledTimes(1));
    switchToB();
    await act(async () => {
      finish({
        status: "prepared", checked: 1, eligible: 1, created: 1,
        created_workspace_ids: ["kit-" + "e".repeat(30)],
        already_prepared: 0, stopped_on_opt_out: false, provider_calls: 0,
        employer_actions_performed: false, automatic_submission_authorized: false,
      });
    });
    expect(await screen.findByRole("heading", { name: /SmartPloy isn't available/i })).toBeTruthy();
    expect(screen.queryByText(/matched IT application draft\(s\)/i)).toBeNull();
    expect(screen.queryByTestId("application-editor")).toBeNull();
  });
});
