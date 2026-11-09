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
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("SP21 application journey", () => {
  it("starts from an explicit mode and uploaded CV, then offers one-click manual employer link", async () => {
    const p = props();
    render(<ApplicationJourney {...p} />);
    const role = await screen.findByText("IT-suunnittelija");
    expect(role).toBeTruthy();
    expect(screen.getByText(/1 CV-text matches/i)).toBeTruthy();
    expect(screen.getByText(/Search cues detected in CV/i)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /apply on employer site/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /save application draft/i })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0].getAttribute("href"))
      .toBe("https://employer.example.invalid/planner");
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0].getAttribute("rel"))
      .toContain("noopener");
    fireEvent.click(screen.getAllByRole("button", { name: /save application draft/i })[0]);
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("current-planner"));
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
    expect(api.getCVJobMatches).toHaveBeenCalledTimes(1);
  });

  it("SP V4: only the current application step is visible, but completed setup can be reopened", async () => {
    const p = props();
    const view = render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    expect((document.getElementById("smartploy-flow-cv") as HTMLElement).hidden).toBe(true);
    expect((document.getElementById("smartploy-flow-choice") as HTMLElement).hidden).toBe(true);
    expect((document.getElementById("smartploy-flow-matches") as HTMLElement).hidden).toBe(false);
    expect((document.getElementById("smartploy-flow-next") as HTMLElement).hidden).toBe(true);
    expect(screen.queryByRole("button", { name: /selected job/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /change method/i }));
    expect((document.getElementById("smartploy-flow-choice") as HTMLElement).hidden).toBe(false);
    expect((document.getElementById("smartploy-flow-matches") as HTMLElement).hidden).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /apply with AI help/i }));
    expect(p.onMode).toHaveBeenCalledWith("assisted");
    view.rerender(<ApplicationJourney {...p} mode="assisted"/>);
    expect((document.getElementById("smartploy-flow-matches") as HTMLElement).hidden).toBe(false);
    expect(p.onPrepare).not.toHaveBeenCalled();
  });

  it("SP69: an already connected CV does not silently select Manual or unlock application actions", async () => {
    const p = { ...props(), mode: null };
    const view = render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByText("Your CV is connected. Choose a method to continue.")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Choose application method" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /save application draft/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /prepare CV & application/i })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /select for preparation/i })).toBeNull();
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /apply with AI help/i }));
    expect(p.onMode).toHaveBeenCalledWith("assisted");
    view.rerender(<ApplicationJourney {...p} mode="assisted"/>);
    fireEvent.click(screen.getByRole("button", { name: /change method/i }));
    expect(screen.getByRole("radio", { name: /match \+ tailored documents/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /apply with AI help/i }));
    expect(screen.queryByRole("button", { name: /prepare CV & application/i })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(screen.getByRole("button", { name: /prepare CV & application/i })).toBeTruthy();
    expect(p.onPrepare).not.toHaveBeenCalled();
  });

  it("SP69: start page shows a connected CV and never treats mode selection as employer consent", () => {
    const onMode = vi.fn(), onBrowse = vi.fn(), onUpload = vi.fn();
    const view = render(<StartChoices onMode={onMode} onBrowse={onBrowse}
      onUpload={onUpload} cvPresent/>);
    expect(screen.getByRole("status").textContent).toContain("CV connected.");
    expect(screen.queryByRole("button", { name: /Upload CV first/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Automatic.*AutoApply/i }));
    expect(onMode).toHaveBeenCalledWith("automatic");
    expect(onUpload).not.toHaveBeenCalled();
    view.rerender(<StartChoices onMode={onMode} onBrowse={onBrowse}
      onUpload={onUpload} cvPresent={false}/>);
    expect(screen.getByRole("group", { name: /Step 2/ })).toBeTruthy();
    expect((screen.getByRole("button", { name: /Automatic.*AutoApply/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Upload CV first/i }));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onMode).toHaveBeenCalledTimes(1);
  });

  it("SP V4 hides future steps until the CV is ready; upload and CV creator remain working", () => {
    const p = { ...props(), cv: { present: false }, mode: null };
    render(<ApplicationJourney {...p} />);
    expect(screen.getByRole("heading", { name: "Start with your CV" })).toBeTruthy();
    expect((document.getElementById("smartploy-flow-choice") as HTMLElement).hidden).toBe(true);
    expect((document.getElementById("smartploy-flow-matches") as HTMLElement).hidden).toBe(true);
    expect((document.getElementById("smartploy-flow-next") as HTMLElement).hidden).toBe(true);
    expect(screen.queryByRole("group", { name: "Choose application method" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /upload CV & find jobs/i }));
    expect(p.onUpload).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: /Create CV from scratch/i }));
    expect(p.onReviewCV).toHaveBeenCalledOnce();
    expect(p.onMode).not.toHaveBeenCalled();
    expect(api.getCVJobMatches).not.toHaveBeenCalled();
  });

  it("keeps assisted filtering separate from document preparation", async () => {
    const p = { ...props(), mode: "assisted" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("button", { name: /change method/i }));
    fireEvent.click(screen.getByRole("radio", { name: /filter jobs only/i }));
    fireEvent.click(screen.getByRole("button", { name: /apply with AI help/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(screen.queryByRole("button", { name: /prepare CV & application/i })).toBeNull();
    expect(screen.getAllByRole("link", { name: /apply on employer site/i })[0]).toBeTruthy();
    expect(screen.getByText(/it does not create an application case or track a submission/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /change method/i }));
    fireEvent.click(screen.getByRole("radio", { name: /match \+ tailored documents/i }));
    fireEvent.click(screen.getByRole("button", { name: /apply with AI help/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /prepare CV & application/i })[0]);
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("current-planner"));
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("SP70: job choice changes next step but never silently creates or submits a case", async () => {
    const p = props();
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByText(/Choose one job to continue/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /save application draft/i })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(screen.getByLabelText("Next step for IT-suunnittelija")).toBeTruthy();
    expect(screen.getByRole("button", { name: /save application draft/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /apply on employer site/i }).getAttribute("href"))
      .toBe("https://employer.example.invalid/planner");
    expect(screen.getByText(/opening the website alone does not create a case/i)).toBeTruthy();
    expect(screen.getByRole("list", { name: "Application steps" }).textContent).toContain("4 · Review documents");
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("SP70: switching out of AutoApply clears the old batch selection", async () => {
    const p = { ...props(), mode: "automatic" as const };
    const view = render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    const boxes = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    fireEvent.click(boxes[0]);
    expect((boxes[0] as HTMLInputElement).checked).toBe(true);
    view.rerender(<ApplicationJourney {...p} mode="manual" />);
    expect(screen.getAllByRole("button", { name: /choose this job/i }).length).toBeGreaterThan(0);
    view.rerender(<ApplicationJourney {...p} mode="automatic" />);
    const after = screen.getAllByRole("checkbox", { name: /select for preparation/i });
    expect((after[0] as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", { name: /prepare applications & start agents/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("SP70: selection from a previous query cannot prepare an absent job", async () => {
    const hidden: SearchJobCard = {
      ...listing, canonical_key: "elsewhere", lane: "recommended",
      job: { ...listing.job, role_title: "Elsewhere role" },
    };
    vi.mocked(api.getCVJobMatches).mockImplementation(async (options) =>
      options?.query === "Elsewhere" ? {
        ...data, recommended: [hidden], other_jobs: [],
        recommended_count: 1, other_jobs_count: 0,
      } : data);
    const p = { ...props(), mode: "assisted" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(screen.getByRole("button", { name: /prepare CV & application/i })).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: /filter matching jobs/i }),
      { target: { value: "Elsewhere" } });
    await screen.findByText("Elsewhere role");
    expect(screen.queryByRole("button", { name: /prepare CV & application/i })).toBeNull();
    expect(screen.getByText(/Choose one job to continue/i)).toBeTruthy();
    expect(p.onPrepare).not.toHaveBeenCalled();
  });

  it("SP75: select a CV-title-matched shortlist with one click, then explicitly prepare once", async () => {
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    const suggest = screen.getByRole("button", { name: /Select 1 CV-title matched job/i });
    expect((suggest as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: /prepare applications & start agents/i }) as HTMLButtonElement).disabled)
      .toBe(true);
    fireEvent.click(suggest);
    // The selected count and exact keys eventually sent to the existing
    // private preparation callback are more reliable than guessing an item
    // position in a recommendation + exploratory display.
    expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy();
    const selectedBox = screen.getByRole("checkbox", { name: "Selected" }) as HTMLInputElement;
    const exploratoryBox = screen.getByRole("checkbox", {
      name: "Select for preparation",
    }) as HTMLInputElement;
    expect(selectedBox.checked).toBe(true);
    expect(exploratoryBox.checked).toBe(false);
    const noMoreMatches = screen.getByRole("button", {
      name: /Select 0 CV-title matched jobs/i,
    }) as HTMLButtonElement;
    expect(noMoreMatches.disabled).toBe(true);
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText(/Review 1 selected job before preparing/i));
    expect(screen.getAllByText(/IT-suunnittelija/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["current-planner"], expect.any(Function), expect.any(Function), false,
    ));
    expect(screen.queryByRole("button", { name: /submit application to employer/i })).toBeNull();
  });

  it("SP94: quick private AutoApply preview requires exact-job confirmation and never sends on cancel", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    const quick = screen.getByRole("button", { name: "Prepare 1 private draft now" });
    expect((quick as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(quick);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("IT-suunnittelija · Public Sector Test Oy"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("NOT contact an employer"));
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
    expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy();
  });

  it("SP94: one confirmed click passes only safe CV-title keys through existing private per-job preparation", async () => {
    const driver: SearchJobCard = {
      ...listing, canonical_key: "driver-job", reasons: ["Keywords: Python"],
      job: { ...listing.job, role_title: "Courier Driver" },
    };
    const retired: SearchJobCard = {
      ...listing, canonical_key: "retired-job",
      job: { ...listing.job, source_current: false },
    };
    const badLink: SearchJobCard = {
      ...listing, canonical_key: "unsafe-link",
      job: { ...listing.job, application_url: "javascript:alert(1)" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, recommended: [listing, driver, retired, badLink],
      recommended_count: 4, other_jobs: [],
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("Courier Driver");
    fireEvent.click(screen.getByRole("button", { name: "Prepare 1 private draft now" }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(1));
    expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["current-planner"], expect.any(Function), expect.any(Function), false,
    );
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /submit application to employer/i })).toBeNull();
  });

  it("SP94: private quick action does not prepare skill-only or unlinked vacancies", async () => {
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data,
      recommended: [{
        ...listing, reasons: ["Keywords: Power BI"],
      }],
      other_jobs: [], recommended_count: 1,
    });
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    expect((screen.getByRole("button", { name: "Prepare 0 private drafts now" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(screen.getByText(/No safe title-matched vacancies are loaded/i)).toBeTruthy();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("SP75: adds up to 15 exact CV-title matches without drivers, stale or unrelated jobs", async () => {
    const extra = Array.from({ length: 18 }, (_, i): SearchJobCard => ({
      ...listing, canonical_key: "data-" + i,
      job: { ...listing.job, role_title: "Data Analyst " + i,
        application_url: "https://employer.example.invalid/data-" + i },
    }));
    const driver: SearchJobCard = {
      ...listing, canonical_key: "driver", reasons: ["Keywords: Python"],
      job: { ...listing.job, role_title: "Delivery Driver" },
    };
    const stale: SearchJobCard = {
      ...listing, canonical_key: "stale", job: { ...listing.job, source_current: false },
    };
    const invalid: SearchJobCard = {
      ...listing, canonical_key: "invalid",
      job: { ...listing.job, application_url: "javascript:alert(1)" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, recommended: [listing, driver, stale, invalid, ...extra],
      recommended_count: 22, other_jobs: [],
    });
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("Delivery Driver");
    fireEvent.click(screen.getByRole("button", { name: /Select 15 CV-title matched jobs/i }));
    expect(screen.getByText("15 of 15 vacancies selected")).toBeTruthy();
    expect((screen.getByRole("button", { name: /Select 0 CV-title matched jobs/i }) as HTMLButtonElement)
      .disabled).toBe(true);
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(1));
    const keys = p.onPrepareSelected.mock.calls[0][0];
    expect(keys).toHaveLength(15);
    expect(keys[0]).toBe("current-planner");
    expect(keys).not.toContain("driver");
    expect(keys).not.toContain("stale");
    expect(keys).not.toContain("invalid");
    expect(new Set(keys).size).toBe(15);
  });

  it("SP75: changed search discards queued keys even during the debounce boundary", async () => {
    const other: SearchJobCard = {
      ...listing, canonical_key: "other-job",
      job: { ...listing.job, role_title: "Other Analyst" },
    };
    vi.mocked(api.getCVJobMatches).mockImplementation(async (options) =>
      options?.query === "Other" ? {
        ...data, recommended: [other], recommended_count: 1,
        other_jobs: [], other_jobs_count: 0,
      } : data);
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("button", { name: /Select 1 CV-title matched job/i }));
    expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: /Filter matching jobs/i }),
      { target: { value: "Other" } });
    expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy();
    expect((screen.getByRole("button", { name: /prepare applications & start agents/i }) as HTMLButtonElement)
      .disabled).toBe(true);
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
    await screen.findByText("Other Analyst");
    fireEvent.click(screen.getByRole("button", { name: /Select 1 CV-title matched job/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["other-job"], expect.any(Function), expect.any(Function), false,
    ));
  });

  it("SP75: changing search during an active batch asks to stop after current job", async () => {
    const p = { ...props(), mode: "automatic" as const };
    let unblock!: (result: AutoApplyBatchOutcome) => void;
    let stopping: (() => boolean) | undefined;
    p.onPrepareSelected.mockImplementation(async (_keys, _progress, shouldStop) => {
      stopping = shouldStop;
      return await new Promise((resolve) => { unblock = resolve; });
    });
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getByRole("button", { name: /Select 1 CV-title matched job/i }));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(1));
    expect(stopping?.()).toBe(false);
    fireEvent.change(screen.getByRole("searchbox", { name: /Filter matching jobs/i }),
      { target: { value: "New vacancy" } });
    expect(stopping?.()).toBe(true);
    await act(async () => unblock({
      preparedKeys: ["current-planner"], failedKeys: [], agentsActive: 1,
      agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
    }));
    expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy();
    expect(p.onPrepareSelected).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
  });

  it("prepares explicitly selected automatic drafts without employer submission", async () => {
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByText(/Prepare a CV and letter for each selected job/i)).toBeTruthy();
    expect(document.getElementById("smartploy-flow-queue")).toBeTruthy();
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

  it("SP87 offers three non-submitting application modes only once a CV is connected", () => {
    const onMode = vi.fn(), onBrowse = vi.fn();
    render(<StartChoices onMode={onMode} onBrowse={onBrowse} cvPresent/>);
    fireEvent.click(screen.getByRole("button", { name: /apply manually/i }));
    expect(onMode).toHaveBeenLastCalledWith("manual");
    fireEvent.click(screen.getByRole("button", { name: /apply with AI/i }));
    expect(onMode).toHaveBeenLastCalledWith("assisted");
    fireEvent.click(screen.getByRole("button", { name: /autoapply/i }));
    expect(onMode).toHaveBeenLastCalledWith("automatic");
    fireEvent.click(screen.getByRole("button", { name: /just find jobs/i }));
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });

  it("SP93 first-time landing shows all three options locked until CV is connected", () => {
    const onMode = vi.fn(), onBrowse = vi.fn(), onUpload = vi.fn(), onCreateCV = vi.fn();
    render(<StartChoices onMode={onMode} onBrowse={onBrowse} cvPresent={false}
      onUpload={onUpload} onCreateCV={onCreateCV}/>);
    expect(screen.getByRole("heading", { name: "Start with your CV." })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Application journey steps" })).toBeTruthy();
    for (const mode of ["manual", "assisted", "automatic"]) {
      const card = document.querySelector(`button.flow-start-card[data-flow-mode="${mode}"]`);
      expect(card).toBeTruthy();
      expect((card as HTMLButtonElement).disabled).toBe(true);
    }
    expect(screen.getByText(/Upload a CV to unlock these options/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Upload CV first/i }));
    fireEvent.click(screen.getByRole("button", { name: /Create CV from scratch/i }));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onCreateCV).toHaveBeenCalledTimes(1);
    expect(onMode).not.toHaveBeenCalled();
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
    expect(screen.getAllByRole("button", { name: /choose this job/i })).toHaveLength(3);
    expect(screen.queryByRole("button", { name: /save application draft/i })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[2]);
    expect(screen.getByRole("button", { name: /save application draft/i })).toBeTruthy();
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
    expect(screen.getByLabelText("Next step for Selected vacancy on a later page")).toBeTruthy();
    expect(screen.getByRole("button", { name: /save application draft/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /save application draft/i }));
    await waitFor(() => expect(p.onPrepare).toHaveBeenCalledWith("selected-page-8"));
    expect(api.getCVJobMatches).toHaveBeenCalledWith({
      limit: 40, query: "", selected_job_key: "selected-page-8",
    });
  });


  it("V4: Jobs-card Automatic pins one verified exact vacancy and continues to its private workspace", async () => {
    const pinned: SearchJobCard = {
      ...listing, canonical_key: "chosen-source-job", lane: "broader",
      job: { ...listing.job, role_title: "Chosen source-verified employer role" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: pinned,
    });
    const p = { ...props(), mode: "automatic" as const, selectedJobKey: pinned.canonical_key };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("Chosen source-verified employer role");
    await waitFor(() => expect(
      (screen.getByRole("checkbox", { name: "Selected" }) as HTMLInputElement).checked
    ).toBe(true));
    expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy();
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
    // The primary next action now performs the same existing private batch
    // preparation for exactly one selected job, never a browser send.
    fireEvent.click(screen.getByRole("button", {
      name: "Prepare and open the selected job application",
    }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["chosen-source-job"], expect.any(Function), expect.any(Function), false,
    ));
    expect(p.onPrepareSelected).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /submit application to employer/i })).toBeNull();
  });

  it("V4: deselecting the Jobs-card vacancy or changing mode never reselects it silently", async () => {
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner" };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing,
    });
    const view = render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("checkbox", { name: "Selected" }));
    expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy();
    expect(screen.queryByRole("button", {
      name: "Prepare and open the selected job application",
    })).toBeNull();
    view.rerender(<ApplicationJourney {...p} mode="manual" />);
    view.rerender(<ApplicationJourney {...p} mode="automatic" />);
    await waitFor(() => expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy());
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("V4: returning to Apply after deselect cannot rearm an already consumed job shortcut", async () => {
    const onClearPinnedJob = vi.fn();
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner", onClearPinnedJob };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing,
    });
    const view = render(<ApplicationJourney {...p} />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("checkbox", { name: "Selected" }));
    expect(onClearPinnedJob).toHaveBeenCalledOnce();
    view.unmount();
    render(<ApplicationJourney {...p} selectedJobKey="" />);
    await waitFor(() => expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy());
    expect(screen.queryByRole("button", {
      name: "Prepare and open the selected job application",
    })).toBeNull();
  });

  it("V4: adding CV-title matches keeps the selected shortlist and never resets it", async () => {
    const second: SearchJobCard = {
      ...listing, canonical_key: "another-title-match",
      job: { ...listing.job, role_title: "Analyst role" },
      reasons: ["Job title matches Analyst"],
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing, recommended: [listing, second],
      recommended_count: 2,
    });
    const onClearPinnedJob = vi.fn();
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner", onClearPinnedJob };
    render(<ApplicationJourney {...p} />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", {name: /Select 1 CV-title matched job/i}));
    expect(screen.getByText("2 of 15 vacancies selected")).toBeTruthy();
    expect(onClearPinnedJob).not.toHaveBeenCalled();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("V4: a prepared pinned job is consumed so reopening Apply cannot rearm it", async () => {
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing,
    });
    const onClearPinnedJob = vi.fn();
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner", onClearPinnedJob };
    render(<ApplicationJourney {...p} />);
    const start = await screen.findByRole("button", {
      name: "Prepare and open the selected job application",
    });
    fireEvent.click(start);
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClearPinnedJob).toHaveBeenCalledOnce());
    expect(p.onPrepareSelected).toHaveBeenCalledWith(
      ["current-planner"], expect.any(Function), expect.any(Function), false,
    );
  });

  it("V4: clearing a consumed pin keeps the remaining title-matched shortlist", async () => {
    const second: SearchJobCard = {
      ...listing, canonical_key: "other-title-match",
      job: { ...listing.job, role_title: "Data Analyst" },
      reasons: ["Job title matches Analyst"],
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing, recommended: [listing, second],
      recommended_count: 2,
    });
    const onClearPinnedJob = vi.fn();
    const propsWithPin = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner", onClearPinnedJob };
    const view = render(<ApplicationJourney {...propsWithPin} />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Select 1 CV-title matched job/i }));
    expect(screen.getByText("2 of 15 vacancies selected")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("checkbox", { name: "Selected" })[0]);
    expect(onClearPinnedJob).toHaveBeenCalledTimes(1);
    view.rerender(<ApplicationJourney {...propsWithPin} selectedJobKey="" />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Prepare applications & start agents" })).toBeTruthy();
    expect(propsWithPin.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("V4: a partially prepared pinned job keeps other jobs and their retry history", async () => {
    const second: SearchJobCard = {
      ...listing, canonical_key: "remaining-title-match",
      job: { ...listing.job, role_title: "Data Analyst" },
      reasons: ["Job title matches Analyst"],
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: listing, recommended: [listing, second],
      recommended_count: 2,
    });
    const onClearPinnedJob = vi.fn();
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: "current-planner", onClearPinnedJob,
      onPrepareSelected: vi.fn(async (): Promise<AutoApplyBatchOutcome> => ({
        preparedKeys: ["current-planner"], failedKeys: ["remaining-title-match"],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      })),
    };
    const view = render(<ApplicationJourney {...p} />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", {name: /Select 1 CV-title matched job/i}));
    expect(screen.getByText("2 of 15 vacancies selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Prepare applications & start agents" }));
    await waitFor(() => expect(onClearPinnedJob).toHaveBeenCalledTimes(1));
    view.rerender(<ApplicationJourney {...p} selectedJobKey="" />);
    await waitFor(() => expect(screen.getByText("1 of 15 vacancies selected")).toBeTruthy());
    expect(screen.getByText(/1 private draft\(s\) ready;/)).toBeTruthy();
    expect(screen.getByText(/1 job\(s\) need a retry/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry 1 failed job" })).toBeTruthy();
    expect(p.onPrepareSelected).toHaveBeenCalledTimes(1);
  });

  it("V4: stale or invalid external Jobs-card links never enable the direct AutoApply action", async () => {
    const pinned: SearchJobCard = {
      ...listing, canonical_key: "stale-source", lane: "broader",
      job: { ...listing.job, role_title: "Unverified external job",
        source_current: false, application_url: "javascript:alert(1)" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, selected_job: pinned,
    });
    const p = { ...props(), mode: "automatic" as const,
      selectedJobKey: pinned.canonical_key };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("Unverified external job");
    expect(screen.getByText("0 of 15 vacancies selected")).toBeTruthy();
    expect(screen.queryByRole("button", {
      name: "Prepare and open the selected job application",
    })).toBeNull();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
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
    // Legacy/synthetic outcomes lacking server workspace IDs never invent one.
    fireEvent.click(screen.getByRole("button", { name: /open prepared applications/i }));
    expect(p.onOpenApplications).toHaveBeenCalledWith(undefined);
    fireEvent.click(screen.getByRole("button", { name: /retry 1 failed job/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenNthCalledWith(
      2, ["extra-role"], expect.any(Function), expect.any(Function), false));
    expect(p.onPrepareSelected).toHaveBeenNthCalledWith(
      1, ["current-planner", "extra-role"], expect.any(Function), expect.any(Function), false);
    await waitFor(() => expect((selectors[1] as HTMLInputElement).checked).toBe(false));
    expect(screen.queryByRole("button", { name: /submit application/i })).toBeNull();
  });

  it("SP56 targets the exact reviewed job and retains earlier IDs after subset retry", async () => {
    const p = { ...props(), mode: "automatic" as const };
    const third: SearchJobCard = {
      ...listing, canonical_key: "needs-source-review", lane: "broader",
      job: { ...listing.job, role_title: "Security Trainee" },
    };
    vi.mocked(api.getCVJobMatches).mockResolvedValue({
      ...data, other_jobs: [...data.other_jobs, third],
      current_jobs_count: 3, other_jobs_count: 2,
    });
    p.onPrepareSelected
      .mockResolvedValueOnce({
        preparedKeys: ["current-planner"],
        preparedWorkspaces: [{ canonicalKey: "current-planner", workspaceId: "exact-workspace-planner" }],
        failedKeys: ["extra-role", "needs-source-review"],
        issues: [
          { canonicalKey: "extra-role", kind: "service_busy", retryable: true,
            guidance: "The private preparation service is temporarily unavailable." },
          { canonicalKey: "needs-source-review", kind: "job_missing", retryable: false,
            guidance: "This posting is no longer current." },
        ],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      })
      .mockResolvedValueOnce({
        preparedKeys: ["extra-role"],
        preparedWorkspaces: [{ canonicalKey: "extra-role", workspaceId: "exact-workspace-support" }],
        failedKeys: [], issues: [],
        agentsActive: 1, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
      });
    render(<ApplicationJourney {...p}/>);
    await screen.findByText("IT-suunnittelija");
    screen.getAllByRole("checkbox", { name: /select for preparation/i })
      .forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: /prepare applications & start agents/i }));
    expect(await screen.findByRole("button", { name: /open prepared applications/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /open prepared applications/i }));
    expect(p.onOpenApplications).toHaveBeenLastCalledWith("exact-workspace-planner");
    fireEvent.click(screen.getByText(/Review each saved application individually/i));
    fireEvent.click(screen.getByRole("button", { name: /Review prepared IT-suunnittelija/i }));
    expect(p.onOpenApplications).toHaveBeenLastCalledWith("exact-workspace-planner");

    fireEvent.click(screen.getByRole("button", { name: /retry 1 failed job/i }));
    await waitFor(() => expect(p.onPrepareSelected).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: /review blocked jobs first/i })).toBeTruthy();
    const summary = screen.getByText(/Review each saved application individually/i);
    if (!(summary.closest("details") as HTMLDetailsElement)?.open) fireEvent.click(summary);
    fireEvent.click(screen.getByRole("button", { name: /Review prepared IT support/i }));
    expect(p.onOpenApplications).toHaveBeenLastCalledWith("exact-workspace-support");
    fireEvent.click(screen.getByRole("button", { name: /Review prepared IT-suunnittelija/i }));
    expect(p.onOpenApplications).toHaveBeenLastCalledWith("exact-workspace-planner");
    expect(p.onOpenApplications).toHaveBeenCalledTimes(4);
    expect(p.onPrepareSelected).toHaveBeenNthCalledWith(
      2, ["extra-role"], expect.any(Function), expect.any(Function), true,
    );
    expect(screen.queryByRole("button", { name: /Submit application to employer/i })).toBeNull();
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


describe("SP96: the applicant has one obvious next action at each gate", () => {
  it("shows a working upload action without silently choosing a method", () => {
    const p = { ...props(), cv: { present: false }, mode: null };
    render(<ApplicationJourney {...p} />);
    const current = screen.getByLabelText("Your next action");
    expect(current.textContent).toContain("Upload or create your CV");
    const upload = screen.getByRole("button", { name: /^Upload CV$/ });
    fireEvent.click(upload);
    expect(p.onUpload).toHaveBeenCalledOnce();
    expect(p.onMode).not.toHaveBeenCalled();
    expect(p.onPrepare).not.toHaveBeenCalled();
  });

  it("shows one unambiguous anchor for choosing the method after CV upload", async () => {
    const p = { ...props(), mode: null };
    render(<ApplicationJourney {...p} />);
    const link = screen.getByRole("link", { name: /^Choose application type$/ });
    expect(link.getAttribute("href")).toBe("#smartploy-flow-choice");
    expect(document.getElementById("smartploy-flow-choice")).toBeTruthy();
    await screen.findByText("IT-suunnittelija");
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("links an Automatic selection directly to the private draft preparation controls", async () => {
    const p = { ...props(), mode: "automatic" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    fireEvent.click(screen.getAllByRole("checkbox", { name: /select for preparation/i })[0]);
    expect(screen.getByRole("link", { name: /^Prepare selected applications$/ })
      .getAttribute("href")).toBe("#smartploy-flow-queue");
    expect(document.getElementById("smartploy-flow-queue")).toBeTruthy();
    expect(p.onPrepareSelected).not.toHaveBeenCalled();
  });

  it("moves the visible next step to matching jobs for a chosen mode", async () => {
    const p = { ...props(), mode: "assisted" as const };
    render(<ApplicationJourney {...p} />);
    await screen.findByText("IT-suunnittelija");
    expect(screen.getByRole("link", { name: /^Choose matching jobs$/ })
      .getAttribute("href")).toBe("#smartploy-flow-matches");
    fireEvent.click(screen.getAllByRole("button", { name: /choose this job/i })[0]);
    expect(screen.getByRole("link", { name: /^Continue selected job$/ })
      .getAttribute("href")).toBe("#smartploy-flow-matches");
    expect(p.onPrepare).not.toHaveBeenCalled();
    expect(api.getCVJobMatches).toHaveBeenCalledTimes(1);
  });
});
