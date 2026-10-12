// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import App from "./App";
import type { SearchPreferences, SearchResults } from "./types";

vi.mock("./api", () => ({
  addManualJob: vi.fn(), approveFact: vi.fn(), createFact: vi.fn(),
  deleteCV: vi.fn(), deleteFact: vi.fn(), getApplications: vi.fn(),
  getCV: vi.fn(), getDashboard: vi.fn(), getHealth: vi.fn(),
  getJobs: vi.fn(), getProfileFacts: vi.fn(), getSession: vi.fn(),
  startApplicationWorkspace: vi.fn(), uploadCV: vi.fn(),
  getSearchPreferences: vi.fn(), updateSearchPreferences: vi.fn(),
  getSearchResults: vi.fn(), getLocalAIStatus: vi.fn(),
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

beforeEach(() => {
  vi.resetAllMocks();
  currentPrefs = { ...initial };
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
  vi.mocked(api.getProfileFacts).mockResolvedValue({ facts: [], count: 0 });
  vi.mocked(api.getApplications).mockResolvedValue({ applications: [], count: 0 });
  vi.mocked(api.getJobs).mockResolvedValue({ jobs: [], count: 0 });
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
});
afterEach(() => cleanup());

describe("actual SmartPloy App first-use and application handoff", () => {
  it("renders the first-use chooser even if optional AI status never returns", async () => {
    vi.mocked(api.getLocalAIStatus).mockImplementation(
      () => new Promise(() => { /* simulate stalled private model */ })
    );
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Find work that fits your goals." })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /general job search/i })).toBeTruthy();
    expect(vi.mocked(api.getSearchResults)).toHaveBeenCalled();
  });

  it("supports general browsing and opens an application without personalized criteria", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("radio", { name: /general job search/i }));
    fireEvent.click(await screen.findByRole("button", { name: /browse all jobs/i }));
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(screen.getByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /prepare documents/i }));
    await waitFor(() => expect(api.startApplicationWorkspace).toHaveBeenCalledWith("test-analyst"));
    expect(await screen.findByTestId("application-editor")).toBeTruthy();
    expect(screen.getByTestId("application-editor").getAttribute("data-workspace")).toMatch(/^kit-/);
  });

  it("keeps General selected while optional user-profile requests finish in the background", async () => {
    let finishCV = () => {};
    vi.mocked(api.getCV).mockImplementationOnce(() => new Promise((resolve) => {
      finishCV = () => resolve({ present: false });
    }));

    render(<App />);
    const generalRadio = await screen.findByRole("radio", { name: /general job search/i });
    fireEvent.click(generalRadio);
    expect((generalRadio as HTMLInputElement).checked).toBe(true);

    // This is the async first-use hydration race observed intermittently
    // under CI load. No CV or model is required for General search.
    await act(async () => { finishCV(); });
    expect((screen.getByRole("radio", { name: /general job search/i }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /browse all jobs/i }));
    await waitFor(() => expect(api.updateSearchPreferences).toHaveBeenCalledWith(
      expect.objectContaining({ mode: "general", expected_revision: 0 })
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
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    expect(screen.getByRole("button", { name: /saving/i }).hasAttribute("disabled")).toBe(true);

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
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
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
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
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

  it("saves new personalized settings and transparently changes ranked results", async () => {
    render(<App />);
    fireEvent.change(await screen.findByPlaceholderText(/Data analyst, Junior software tester/), {
      target: { value: "Data Analyst" },
    });
    fireEvent.click(screen.getByRole("button", { name: /show my matched jobs/i }));
    expect(await screen.findByText(/90% search match/i)).toBeTruthy();
    expect(currentPrefs.mode).toBe("personalized");

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByRole("heading", { name: "Job search preferences" })).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    await waitFor(() => expect(currentPrefs.mode).toBe("general"));
    expect(await screen.findByText(/1 current job listings/i)).toBeTruthy();
    expect(screen.queryByText(/90% search match/i)).toBeNull();
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
    expect(screen.getByRole("button", { name: "Dashboard", exact: true })).toBeTruthy();
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

  it("isolates a failed optional profile API without locking out jobs", async () => {
    currentPrefs = { ...initial, completed: true, mode: "general", revision: 1 };
    vi.mocked(api.getProfileFacts).mockRejectedValue(new Error("profile temporarily unavailable"));
    vi.mocked(api.getLocalAIStatus).mockRejectedValue(new Error("Ollama unavailable"));
    render(<App />);
    expect(await screen.findByText("Junior Data Analyst")).toBeTruthy();
    expect(await screen.findByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /prepare documents/i })).toBeTruthy();
  });
});
