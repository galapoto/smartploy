/** Synthetic browser acceptance of the BUILT SmartPloy frontend.
 *
 * No production user account, CV, employer form, job API, Cloudflare bypass,
 * or application submission is involved. Every backend response is a private
 * in-test fixture; the actual Vite production preview is rendered by Chromium.
 */
import { mkdir } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { PrivateSavedJob, SearchJobCard, SearchPreferences, SearchResults } from "../src/types";

const EMPTY_PREFERENCES: SearchPreferences = {
  completed: false, mode: "personalized", roles: [], locations: [],
  languages: [], work_modes: [], keywords: [], skills: [],
  seniority: "any", revision: 0, updated_at: "",
  verified_qualification_fit: false,
};

const analyst: SearchJobCard = {
  canonical_key: "synthetic-analyst",
  job: {
    company: "Example Oy", role_title: "Junior Data Analyst",
    location: "Helsinki", language: "English", work_mode: "remote",
    employer_sector: "private", source_current: true,
    application_url: "https://jobs.example.invalid/analyst",
    source_ids: ["synthetic-lever"], source_attribution: "Synthetic ATS",
    posted_at: "2026-10-10T10:00:00Z",
    first_seen_at: "2026-10-10T10:00:00Z",
    last_seen_at: "2026-10-11T10:00:00Z", deadline: "",
    ai_preparation_allowed: false,
  },
  preference_score: null, reasons: [], unknown_fields: [], lane: "all",
};
const tester: SearchJobCard = {
  ...analyst,
  canonical_key: "synthetic-tester",
  job: {
    ...analyst.job, role_title: "Software Tester",
    company: "Quality Example Oy", location: "Espoo",
    application_url: "https://jobs.example.invalid/tester",
  },
};

type MockState = {
  userId: string;
  cvFilename: string;
  preferences: SearchPreferences;
  lastSave: Record<string, unknown> | null;
  unavailableAI: boolean;
  privateSavedJobs: Record<string, PrivateSavedJob[]>;
};

function discovery(state: MockState): SearchResults {
  const common = {
    completed: state.preferences.completed,
    available_count: 2,
    external_actions_authorized: false as const,
  };
  if (!state.preferences.completed) {
    return { ...common, mode: "setup_required", score_kind: "none",
      recommendations: [], broader: [], all_jobs: [] };
  }
  if (state.preferences.mode === "general") {
    return { ...common, mode: "general", score_kind: "none",
      recommendations: [], broader: [], all_jobs: [analyst, tester] };
  }
  return {
    ...common, mode: "personalized",
    score_kind: "preference_alignment_not_verified_qualification",
    recommendations: [{
      ...analyst, lane: "recommended", preference_score: 87,
      reasons: ["Job title matches Data Analyst", "Preferred location"],
      unknown_fields: ["Experience level not specified"],
      mismatched_fields: [],
    }],
    broader: [{
      ...tester, lane: "broader", preference_score: 35,
      reasons: [], unknown_fields: ["Job language not specified"],
      mismatched_fields: [],
    }],
    all_jobs: [],
  };
}

async function installSyntheticApi(page: Page, options: {
  initial?: Partial<SearchPreferences>;
  cvFilename?: string;
  unavailableAI?: boolean;
} = {}): Promise<MockState> {
  const state: MockState = {
    userId: "synthetic-user-a",
    cvFilename: options.cvFilename || "",
    preferences: { ...EMPTY_PREFERENCES, ...options.initial },
    lastSave: null,
    unavailableAI: Boolean(options.unavailableAI),
    privateSavedJobs: {},
  };
  const response = async (
    route: import("@playwright/test").Route,
    body: unknown, status = 200,
  ) => route.fulfill({
    status, contentType: "application/json", body: JSON.stringify(body),
    headers: { "Cache-Control": "no-store" },
  });

  await page.route("**/healthz", async (route) => response(route, {
    ok: true, storage: { mode: "synthetic", ready: true },
    obumai_configured: false,
  }));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/private-jobs" && request.method() === "POST") {
      const payload = JSON.parse(request.postData() || "{}") as Record<string, string>;
      const item: PrivateSavedJob = {
        saved_job_id: "saved-synthetic-" + state.userId + "-" + ((state.privateSavedJobs[state.userId] || []).length + 1),
        company: payload.company || "", role_title: payload.role_title || "",
        description: payload.description || "", location: payload.location || "",
        application_url: payload.application_url || "",
        created_at: "2026-10-12T10:00:00Z", private: true,
        employer_availability_verified: false, external_actions_authorized: false,
      };
      state.privateSavedJobs[state.userId] = [
        item, ...(state.privateSavedJobs[state.userId] || []),
      ];
      await response(route, { status: "saved_private", job: item }, 201);
      return;
    }
    if (path.startsWith("/api/v1/private-jobs/") && request.method() === "DELETE") {
      const savedId = decodeURIComponent(path.slice("/api/v1/private-jobs/".length));
      const current = state.privateSavedJobs[state.userId] || [];
      const remainder = current.filter((item) => item.saved_job_id !== savedId);
      if (remainder.length === current.length) {
        await response(route, { detail: "Private saved job not found" }, 404);
      } else {
        state.privateSavedJobs[state.userId] = remainder;
        await response(route, { deleted: true });
      }
      return;
    }

    if (path === "/api/v1/search-preferences" && request.method() === "PUT") {
      const input = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      if (input.expected_revision !== state.preferences.revision) {
        await response(route, { detail: "Concurrent edit: reload before saving" }, 409);
        return;
      }
      state.lastSave = input;
      state.preferences = {
        ...state.preferences, ...input, completed: true,
        revision: state.preferences.revision + 1,
        updated_at: new Date().toISOString(),
        verified_qualification_fit: false,
      } as SearchPreferences;
      await response(route, state.preferences);
      return;
    }

    const fixtures: Record<string, unknown> = {
      "/api/v1/session": {
        authenticated: true, user_id: state.userId,
        profile_id: "profile-" + state.userId,
        email: "synthetic@example.invalid", auth_source: "fixture",
      },
      "/api/v1/search-preferences": state.preferences,
      "/api/v1/search-results": discovery(state),
      "/api/v1/dashboard": {
        top_matches: [], possible_matches: [],
        preparation_counts: {},
        profile: { ready: false },
        applications: {
          total_records: 0, state_counts: {},
          preparing: 0, awaiting_review: 0, preparation_blocked: 0,
          actually_submitted: 0, interviews: 0, offers: 0, rejections: 0,
        },
        worker: { ready: true, configured: true, count: 1, tasks: [], error: "" },
        source_health: [{
          source_id: "synthetic-lever", status: "healthy",
          last_success_at: "2026-10-11T10:00:00Z",
          last_item_count: 2,
        }],
        external_actions_authorized: false,
      },
      "/api/v1/profile/cv": state.cvFilename
        ? { present: true, filename: state.cvFilename, size_bytes: 1200 }
        : { present: false },
      "/api/v1/profile/facts": { facts: [], count: 0 },
      "/api/v1/applications": { applications: [], count: 0 },
      "/api/v1/jobs": { jobs: [], count: 0 },
      "/api/v1/private-jobs": {
        jobs: state.privateSavedJobs[state.userId] || [],
        count: (state.privateSavedJobs[state.userId] || []).length,
        private: true,
      },
      "/api/v1/local-ai/status": {
        configured: false, ready: false, provider: "disabled",
        model: "", external_ai_forwarding: false,
      },
    };
    if (state.unavailableAI && path === "/api/v1/local-ai/status") {
      await response(route, { detail: "Synthetic optional model outage" }, 503);
      return;
    }
    if (!(path in fixtures)) {
      await response(route, { detail: "Unexpected synthetic API: " + path }, 404);
      return;
    }
    await response(route, fixtures[path]);
  });
  return state;
}

async function evidence(page: Page, filename: string) {
  await mkdir("browser-evidence", { recursive: true });
  await page.screenshot({ path: "browser-evidence/" + filename, fullPage: true });
}

test("production build renders inline SmartPloy logo and a working first-use chooser", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Find work that fits your goals." })).toBeVisible();
  const logo = page.locator("svg[aria-label='SmartPloy turquoise and navy mark']");
  await expect(logo).toBeVisible();
  const bounds = await logo.boundingBox();
  expect(bounds?.width).toBeGreaterThan(20);
  expect(bounds?.height).toBeGreaterThan(20);
  await expect(page.getByRole("radio", { name: /Personalized jobs/i })).toBeChecked();
  await expect(page.getByRole("radio", { name: /General job search/i })).toBeVisible();

  const icon = page.locator("link[rel='icon'][type='image/svg+xml']");
  await expect(icon).toHaveAttribute("href", "/smartploy-mark-v2.svg?v=2");
  const favicon = await page.request.get("/smartploy-mark-v2.svg?v=2");
  expect(favicon.ok()).toBe(true);
  expect(await favicon.text()).toContain("#06D9E8");
  await evidence(page, "synthetic-first-use-desktop.png");
});

test("general browsing needs no CV; Settings switches into and out of personalized matching", async ({ page }) => {
  const state = await installSyntheticApi(page);
  await page.goto("/");
  await page.getByRole("radio", { name: /General job search/i }).check();
  await page.getByRole("button", { name: /Browse all jobs/i }).click();
  await expect(page.getByRole("heading", { name: "Latest jobs in Finland" })).toBeVisible();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText("Software Tester")).toBeVisible();
  await expect(page.getByText("General listing")).toHaveCount(2);
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  expect(state.lastSave?.mode).toBe("general");
  expect(state.lastSave?.roles).toEqual([]);
  await evidence(page, "synthetic-general-search.png");

  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await page.getByPlaceholder(/Data analyst, Junior software tester/i).fill("Data Analyst");
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await expect(page.getByText("87% search match")).toBeVisible();
  await page.getByRole("button", { name: "Why shown" }).click();
  await expect(page.getByText(/not a verified skills or eligibility assessment/i)).toBeVisible();
  expect(state.preferences.roles).toEqual(["Data Analyst"]);
  await evidence(page, "synthetic-personalized-search.png");

  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("radio", { name: /General job search/i }).check();
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await expect(page.getByText("General listing")).toHaveCount(2);
  await expect(page.getByText(/search match/i)).toHaveCount(0);
});

test("Settings save is not overwritten by a manual refresh during an in-flight write", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: {
      completed: true, mode: "personalized",
      roles: ["Data Analyst"], revision: 2,
    },
  });
  let preferenceReads = 0;
  let notifySaveStarted: () => void = () => {};
  const saveStarted = new Promise<void>((resolve) => { notifySaveStarted = resolve; });
  let finishSave: () => void = () => {};
  const saveGate = new Promise<void>((resolve) => { finishSave = resolve; });

  // Route.fallback retains the approved in-test synthetic API handler;
  // no real employer/production requests or user data are involved.
  await page.route("**/api/v1/search-preferences", async (route) => {
    if (route.request().method() === "PUT") {
      notifySaveStarted();
      await saveGate;
    } else {
      preferenceReads += 1;
    }
    await route.fallback();
  });

  await page.goto("/");
  await expect(page.getByText("87% search match")).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("radio", { name: /General job search/i }).check();
  const readsBeforeSave = preferenceReads;
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await saveStarted;
  await expect(page.getByRole("button", { name: /Saving/i })).toBeDisabled();

  await page.getByRole("button", { name: "Refresh workspace" }).click();
  expect(preferenceReads).toBe(readsBeforeSave);
  expect(state.preferences.mode).toBe("personalized");

  finishSave();
  await expect(page.getByRole("heading", { name: "Latest jobs in Finland" })).toBeVisible();
  await expect(page.getByText("General listing")).toHaveCount(2);
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  expect(state.preferences.mode).toBe("general");

  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect.poll(() => preferenceReads).toBe(readsBeforeSave + 1);
  await expect(page.getByText("General listing")).toHaveCount(2);
});

test("identity switch while search Settings PUT is in flight fails closed in the real SPA", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: {
      completed: true, mode: "personalized",
      roles: ["Account A role"], revision: 2,
    },
  });
  let finishSave: () => void = () => {};
  const saveGate = new Promise<void>((resolve) => { finishSave = resolve; });
  let notifySaveStarted: () => void = () => {};
  const saveStarted = new Promise<void>((resolve) => { notifySaveStarted = resolve; });
  let interceptedSaves = 0;

  // Hold account A's original PUT response. A synthetic switch to account B
  // must not publish it, even when the visible email is unchanged.
  await page.route("**/api/v1/search-preferences", async (route) => {
    if (route.request().method() !== "PUT") {
      await route.fallback();
      return;
    }
    interceptedSaves += 1;
    const payload = JSON.parse(route.request().postData() || "{}") as Record<string, unknown>;
    expect(payload.mode).toBe("general");
    expect(payload.expected_revision).toBe(2);
    notifySaveStarted();
    await saveGate;
    await route.fulfill({
      status: 200, contentType: "application/json",
      headers: { "Cache-Control": "no-store" },
      body: JSON.stringify({
        ...EMPTY_PREFERENCES, completed: true, mode: "general",
        roles: ["Account A role"], revision: 3,
        updated_at: "2026-10-12T08:00:00Z",
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByText("87% search match")).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("radio", { name: /General job search/i }).check();
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await saveStarted;
  await expect(page.getByRole("button", { name: /Saving/i })).toBeDisabled();

  state.userId = "synthetic-user-b"; // the synthetic email stays identical
  state.preferences = {
    ...EMPTY_PREFERENCES, completed: true, mode: "personalized",
    roles: ["Account B role"], revision: 7,
  };
  finishSave();

  await expect(page.getByRole("heading", { name: /SmartPloy isn't available/i })).toBeVisible();
  await expect(page.getByText(/signed-in account changed or could not be verified while saving/i))
    .toBeVisible();
  await expect(page.getByText("General listing")).toHaveCount(0);
  expect(interceptedSaves).toBe(1);
  expect(state.preferences.roles).toEqual(["Account B role"]);

  // A deliberate reload of the private workspace retrieves account B's own
  // preferences; no stale account A save result can switch B into General.
  await page.getByRole("button", { name: /Try again/i }).click();
  await expect(page.getByText("87% search match")).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("radio", { name: /Personalized jobs/i })).toBeChecked();
  await expect(page.getByPlaceholder(/Data analyst, Junior software tester/i))
    .toHaveValue("Account B role");
});

test("saved private jobs do not enter ATS discovery and vanish after account switching", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
  });
  await page.goto("/");
  await expect(page.getByText("General listing")).toHaveCount(2);
  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(page.getByRole("heading", { name: "Your saved opportunities" })).toBeVisible();
  await page.getByRole("button", { name: "Save job" }).first().click();
  const modal = page.getByRole("dialog", { name: "Save an opportunity" });
  await modal.getByPlaceholder("e.g. Junior Data Analyst").fill("PRIVATE-BOOKMARK-A");
  await modal.getByPlaceholder("Employer name").fill("Fictional Private Company");
  await modal.getByPlaceholder("Paste the responsibilities and key requirements here.")
    .fill("User-saved reference, not a verified posting");
  await modal.getByRole("button", { name: "Save job" }).click();

  await expect(page.getByText("PRIVATE-BOOKMARK-A")).toBeVisible();
  expect(state.privateSavedJobs["synthetic-user-a"]).toHaveLength(1);
  await expect(page.getByText("General listing")).toHaveCount(2);
  await expect(page.getByText(/search match/i)).toHaveCount(0);

  state.userId = "synthetic-user-b"; // same email, different authenticated ID
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect(page.getByRole("heading", { name: /Make your next move/i })).toBeVisible();
  await page.getByRole("button", { name: "Find jobs" }).click();
  await expect(page.getByText("PRIVATE-BOOKMARK-A")).toHaveCount(0);
  await expect(page.getByText(/No private saved jobs yet/i)).toBeVisible();
  expect(state.privateSavedJobs["synthetic-user-b"]).toBeUndefined();
});

test("a same-email account change resets unsaved criteria and private CV details", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: {
      completed: true, mode: "general", roles: ["Account A role"],
      revision: 3,
    },
    cvFilename: "PRIVATE-ACCOUNT-A.pdf",
  });
  await page.goto("/");
  await expect(page.getByText("PRIVATE-ACCOUNT-A.pdf")).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await page.getByPlaceholder(/Data analyst, Junior software tester/i).fill("UNSAVED ACCOUNT A ONLY");
  state.userId = "synthetic-user-b";
  state.cvFilename = "ACCOUNT-B.pdf";
  state.preferences = {
    ...EMPTY_PREFERENCES, completed: true, mode: "general",
    roles: ["Account B role"], revision: 3,
  };
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  // Switching signed-in accounts always closes the previous account's
  // editor/Settings and returns to the new user's clean dashboard.
  await expect(page.getByRole("heading", { name: /Make your next move/i })).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("radio", { name: /General job search/i })).toBeChecked();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await expect(page.getByPlaceholder(/Data analyst, Junior software tester/i))
    .toHaveValue("Account B role");
  await page.getByRole("button", { name: "Dashboard", exact: true }).click();
  await expect(page.getByText("PRIVATE-ACCOUNT-A.pdf")).toHaveCount(0);
  await expect(page.getByText("ACCOUNT-B.pdf")).toBeVisible();
});

test("a delayed application-draft response is discarded after same-email account switch", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
  });
  let release: () => void = () => {};
  const pending = new Promise<void>(resolve => { release = resolve; });
  let notifyStarted: () => void = () => {};
  const started = new Promise<void>(resolve => { notifyStarted = resolve; });
  let calls = 0;

  // All data is fictional and requests stay inside the Playwright router.
  await page.route("**/api/v1/jobs/*/application-workspace", async route => {
    calls += 1;
    notifyStarted();
    await pending;
    await route.fulfill({
      status: 200, contentType: "application/json",
      headers: { "Cache-Control": "no-store" },
      body: JSON.stringify({
        created: true, workspace: {
          workspace_id: "PRIVATE-ACCOUNT-A-DRAFT-NEVER-RENDER",
          canonical_key: "synthetic-analyst",
        },
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await page.getByRole("button", { name: /Prepare documents/i }).first().click();
  await started;
  state.userId = "synthetic-user-b"; // email intentionally stays the same
  release();

  await expect(page.getByRole("heading", { name: /SmartPloy isn't available/i })).toBeVisible();
  await expect(page.getByText(/could not be verified during a private action/i)).toBeVisible();
  await expect(page.getByText("PRIVATE-ACCOUNT-A-DRAFT-NEVER-RENDER")).toHaveCount(0);
  expect(calls).toBe(1);
  await page.getByRole("button", { name: /Try again/i }).click();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await page.getByRole("button", { name: "My applications" }).click();
  await expect(page.getByRole("heading", { name: "My applications" })).toBeVisible();
  await expect(page.getByText("PRIVATE-ACCOUNT-A-DRAFT-NEVER-RENDER")).toHaveCount(0);
});

test("same-email account switch removes the previous user's private application editor", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: {
      completed: true, mode: "general", revision: 1,
    },
    cvFilename: "ACCOUNT-A-CV.pdf",
  });
  await page.route("**/api/v1/application-workspaces", async (route) => {
    const tag = state.userId === "synthetic-user-a" ? "A" : "B";
    const workspace = {
      workspace_id: "synthetic-private-draft-" + tag,
      canonical_key: "synthetic-job-" + tag,
      role_title: "Private " + tag + " role",
      company: "Fictional Employer " + tag,
      application_url: "https://jobs.example.invalid/" + tag,
      cv_text: "ACCOUNT-" + tag + "-PRIVATE-CV-TEXT",
      cover_letter_text: "ACCOUNT-" + tag + "-PRIVATE-LETTER-TEXT",
      source_cv_sha256: "", approved_evidence_ids: [],
      revision: 1, status: "draft",
      self_reported_applied_at: "", self_reported_reference: "",
      created_at: "2026-10-10T10:00:00Z", updated_at: "2026-10-10T10:00:00Z",
      authority: {
        may_edit: true, may_download: true,
        may_submit_to_employer: false, has_external_submission_proof: false,
      },
    };
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ workspaces: [workspace], count: 1 }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "My applications" }).click();
  await expect(page.getByRole("textbox", { name: "Editable CV text" }))
    .toHaveValue("ACCOUNT-A-PRIVATE-CV-TEXT");
  await page.getByRole("textbox", { name: "Editable cover letter text" })
    .fill("UNSAVED-ACCOUNT-A-PRIVATE-LETTER");
  state.userId = "synthetic-user-b"; // deliberately same email, different server ID
  state.cvFilename = "ACCOUNT-B-CV.pdf";
  state.preferences = {
    ...EMPTY_PREFERENCES, completed: true, mode: "general",
    revision: 1,
  };
  await page.getByRole("button", { name: "Refresh workspace" }).click();

  await expect(page.getByRole("textbox", { name: "Editable CV text" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Make your next move/i })).toBeVisible();
  await expect(page.getByText("ACCOUNT-A-CV.pdf")).toHaveCount(0);
  await page.getByRole("button", { name: "My applications" }).click();
  await expect(page.getByRole("textbox", { name: "Editable CV text" }))
    .toHaveValue("ACCOUNT-B-PRIVATE-CV-TEXT");
  await expect(page.getByRole("textbox", { name: "Editable cover letter text" }))
    .toHaveValue("ACCOUNT-B-PRIVATE-LETTER-TEXT");
  await expect(page.getByText("Private A role")).toHaveCount(0);
});

test("mobile onboarding remains usable when the optional local AI endpoint fails", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installSyntheticApi(page, { unavailableAI: true });
  await page.goto("/");
  await expect(page.locator("svg[aria-label='SmartPloy turquoise and navy mark']")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Find work that fits your goals." })).toBeVisible();
  await page.getByRole("radio", { name: /General job search/i }).check();
  await page.getByRole("button", { name: /Browse all jobs/i }).click();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeVisible();
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  await evidence(page, "synthetic-general-mobile.png");
});
