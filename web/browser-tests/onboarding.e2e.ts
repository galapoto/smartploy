/** Synthetic browser acceptance of the BUILT SmartPloy frontend.
 *
 * No production user account, CV, employer form, job API, Cloudflare bypass,
 * or application submission is involved. Every backend response is a private
 * in-test fixture; the actual Vite production preview is rendered by Chromium.
 */
import { mkdir } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { ApplicationWorkspace, PrivateSavedJob, SearchJobCard, SearchPreferences, SearchResults } from "../src/types";

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
    employer_sector: "private", career_area: "it_data", title_experience: "entry",
    source_current: true,
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
  privateWorkspaces: Record<string, ApplicationWorkspace[]>;
  applicationWorkspaceCreates: string[];
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
    privateWorkspaces: {},
    applicationWorkspaceCreates: [],
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

    if (path === "/api/v1/profile/cv" && request.method() === "POST") {
      const uploaded = JSON.parse(request.postData() || "{}") as { filename?: string };
      state.cvFilename = String(uploaded.filename || "Synthetic CV.docx");
      await response(route, {
        present: true, filename: state.cvFilename, size_bytes: 300,
        text_preview: "Synthetic candidate with data analysis and Power BI",
        sha256: "a".repeat(64),
      });
      return;
    }
    if (path === "/api/v1/profile/cv/matches" && request.method() === "GET") {
      await response(route, {
        cv_present: Boolean(state.cvFilename), cv_filename: state.cvFilename,
        match_mode: state.cvFilename ? "cv_text_signals" : "upload_cv",
        detected_roles: ["Data Analyst"], detected_topics: ["Power BI"],
        recommended: [{
          ...analyst, lane: "recommended", preference_score: 87,
          reasons: ["Job title matches Data Analyst"],
        }], other_jobs: [{
          ...tester, lane: "broader", preference_score: 25,
          reasons: [], unknown_fields: ["Experience not stated"],
        }],
        current_jobs_count: 2, recommended_count: 1,
        matched_from: "local_cv_text_not_approved_evidence",
        qualifications_verified: false, employer_actions_performed: false,
      });
      return;
    }
    if (path.startsWith("/api/v1/jobs/") && path.endsWith("/application-workspace")
        && request.method() === "POST") {
      const key = decodeURIComponent(path.split("/")[4] || "");
      const job = [analyst, tester].find((item) => item.canonical_key === key);
      if (!job || !state.cvFilename) {
        await response(route, { detail: "No current synthetic job or connected CV" }, 409);
        return;
      }
      const current = state.privateWorkspaces[state.userId] || [];
      const existing = current.find((item) => item.canonical_key === key);
      if (existing) {
        await response(route, { created: false, workspace: existing });
        return;
      }
      // A real, reusable owner-scoped synthetic workspace, not just an ID.
      // The UI can now render the exact draft after navigation, and cross-user
      // account switches cannot fetch another owner's private CV/letter.
      const workspace: ApplicationWorkspace = {
        workspace_id: "synthetic-draft-" + state.userId + "-" + key,
        canonical_key: key, role_title: job.job.role_title,
        company: job.job.company, application_url: job.job.application_url,
        cv_text: "FICTIONAL CV draft for " + job.job.role_title,
        cover_letter_text: "FICTIONAL letter for " + job.job.company,
        source_cv_sha256: "a".repeat(64), approved_evidence_ids: [],
        revision: 1, status: "draft",
        self_reported_applied_at: "", self_reported_reference: "",
        created_at: "2026-10-30T08:00:00Z", updated_at: "2026-10-30T08:00:00Z",
        authority: { may_edit: true, may_download: true,
          may_submit_to_employer: false, has_external_submission_proof: false },
      };
      state.privateWorkspaces[state.userId] = [workspace, ...current];
      state.applicationWorkspaceCreates.push(key);
      await response(route, { created: true, workspace });
      return;
    }
    if (path === "/api/v1/application-agents/inbox" && request.method() === "GET") {
      await response(route, {
        items: [], count: 0, has_more: false, next_offset: null,
        background_worker_verified: false, external_actions_authorized: false,
      });
      return;
    }
    if (path === "/api/v1/application-agents" && request.method() === "GET") {
      await response(route, { agents: [], count: 0, external_actions_authorized: false });
      return;
    }
    if (path.startsWith("/api/v1/application-workspaces/") &&
        request.method() === "GET") {
      const relative = path.slice("/api/v1/application-workspaces/".length);
      const [encodedId, action] = relative.split("/");
      const id = decodeURIComponent(encodedId);
      const owned = (state.privateWorkspaces[state.userId] || [])
        .find((item) => item.workspace_id === id);
      if (!owned) {
        await response(route, { detail: "No owner-scoped synthetic workspace" }, 404);
        return;
      }
      if (!action) {
        await response(route, { workspace: owned });
        return;
      }
      const privateReads: Record<string, unknown> = {
        agent: { present: false, agent: null, external_actions_authorized: false },
        "handoff-readiness": {
          ready: false, blockers: ["Approve contact details before browser autofill"],
          document_revision: owned.revision, contact_fields_ready: false,
          employer_submission_performed: false, will_require_manual_review: true,
          files_attached: false,
        },
        "employer-attempt": {
          previous_attempt_reserved: false, state: "not_reserved",
          requires_human_reconciliation: false,
          automatic_employer_submit_authorized: false,
          external_confirmation_verified: false,
          cross_device_server_claim_required: true,
        },
        "submit-review-intent": {
          review_recorded: false, review_state: "not_recorded", expires_at: "",
          automatic_employer_submit_authorized: false, external_actions_performed: false,
          browser_grant_issued: false,
        },
        "final-action-readiness": {
          operator_permission_reviewed: false, current_applicant_review_recorded: false,
          separate_final_user_approval_recorded: false,
          previous_employer_attempt_reserved: false,
          trusted_one_use_browser_redemption_available: false,
          final_browser_click_authorized: false,
          employer_submission_performed: false, employer_receipt_verified: false,
          blockers: ["independent_employer_permission_missing"],
        },
        "browser-receipt": { present: false, receipt: null },
      };
      if (!(action in privateReads)) {
        await response(route, { detail: "Unexpected synthetic workspace read" }, 404);
        return;
      }
      await response(route, privateReads[action]);
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
      "/api/v1/application-workspaces": {
        workspaces: state.privateWorkspaces[state.userId] || [],
        count: (state.privateWorkspaces[state.userId] || []).length,
      },
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


test("SP69: first-use Upload CV first is a working button and leads to explicit method choice", async ({ page }) => {
  const state = await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Upload CV first/i })).toBeVisible();
  await page.getByRole("button", { name: /Upload CV first/i }).click();
  await page.locator("input[aria-label='Select CV to upload']").setInputFiles({
    name: "Newcomer-Synthetic-CV.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("IN-TEST CV BLOB; no personal data"),
  });
  await expect(page.getByText("Newcomer-Synthetic-CV.docx is ready")).toBeVisible();
  await expect(page.getByText("Your CV is connected. Choose a method to continue.")).toBeVisible();
  await expect(page.locator(".flow-mode.selected")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Save application draft/i })).toHaveCount(0);
  expect(state.cvFilename).toBe("Newcomer-Synthetic-CV.docx");
  expect(state.applicationWorkspaceCreates).toEqual([]);
});

test("CV-first manual application goes from upload to real matching and selected private draft", async ({ page }) => {
  const state = await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await expect(page.getByRole("button", { name: /Apply manually/i })).toHaveCount(0);
  await page.locator("input[aria-label='Select CV to upload']").setInputFiles({
    name: "Synthetic-IT-CV.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("IN-TEST CV BLOB; no real CV"),
  });
  await expect(page.getByText("Synthetic-IT-CV.docx is ready")).toBeVisible();
  await expect(page.getByRole("group", { name: "Choose application method" })).toBeVisible();
  await page.getByRole("button", { name: /Apply manually/i }).click();
  await expect(page.getByRole("heading", {
    name: "Upload your CV. Choose your method. Apply.",
  })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs from your CV" })).toBeVisible();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText(/CV-text matches/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Save application draft" })).toHaveCount(0);
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await expect(page.getByLabel("Next step for Junior Data Analyst")).toBeVisible();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await page.getByRole("button", { name: "Save application draft" }).click();
  await expect.poll(() => state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await expect(page.getByRole("heading", { name: /My applications/i }).first()).toBeVisible();
  const progress = page.getByRole("region", { name: "Application progress and next action" });
  await expect(progress).toBeVisible();
  await expect(progress).toContainText("Action required · draft only");
  await expect(progress).toContainText("Approve contact details before browser autofill");
  await expect(page.getByRole("link", { name: "See missing requirements" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Review CV/i }).first()).toBeVisible();
  const reviewQueue = page.getByRole("region", { name: "Application review queue" });
  await expect(reviewQueue).toBeVisible();
  await expect(reviewQueue).toContainText("1 private draft to finish");
  await expect(reviewQueue).toContainText("0 self-reported");
  await expect(reviewQueue).toContainText("0 employer-acknowledged");
  const filters = reviewQueue.getByRole("group", { name: "Filter application statuses" });
  await filters.getByRole("button", { name: /Drafts to finish 1/i }).click();
  await expect(page.getByRole("complementary", { name: "Your application drafts" })
    .getByRole("button", { name: /Junior Data Analyst/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Continue this draft/i })).toHaveAttribute(
    "href", "#smartploy-cv-review");
  const attemptAudit = page.getByRole("region", { name: "Previous employer attempt checks" });
  await expect(attemptAudit).toContainText("0 of 1 loaded private drafts checked");
  await attemptAudit.getByRole("button", { name: "Check next 1 draft attempt" }).click();
  await expect(attemptAudit).toContainText("1 of 1 loaded private drafts checked");
  await expect(attemptAudit).toContainText("0 need previous-attempt reconciliation");
  await attemptAudit.getByText("View per-application attempt checks").click();
  await expect(attemptAudit).toContainText(
    "No previous attempt recorded at check time — not send permission");
  // An attempt check is a signed-in GET, never another application creation
  // or a final employer action.
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  expect(state.cvFilename).toBe("Synthetic-IT-CV.docx");
  await evidence(page, "sp73-checked-private-draft-attempt.png");
  await evidence(page, "sp72-private-draft-review-queue.png");
  await evidence(page, "sp71-private-draft-next-action.png");
  await evidence(page, "synthetic-cv-first-manual-application.png");
});

test("SP69: direct CV upload requires an explicit Manual, Assisted or Automatic choice", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
  });
  await page.goto("/");
  await page.locator("input[aria-label='Select CV to upload']").setInputFiles({
    name: "Synthetic-IT-CV.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("IN-TEST CV BLOB; no applicant data"),
  });
  await expect(page.getByText("Synthetic-IT-CV.docx is ready")).toBeVisible();
  await expect(page.getByText("Your CV is connected. Choose a method to continue.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs from your CV" })).toBeVisible();
  await expect(page.locator(".flow-mode.selected")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /save application draft/i })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: /select for preparation/i })).toHaveCount(0);

  await page.getByRole("button", { name: /apply with AI help/i }).click();
  await expect(page.locator(".flow-mode.selected")).toContainText("Apply with AI help");
  await expect(page.getByRole("button", { name: /prepare CV & application/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await expect(page.getByRole("button", { name: /prepare CV & application/i })).toBeVisible();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await page.getByRole("button", { name: /AutoApply/i }).click();
  await expect(page.locator(".flow-mode.selected")).toContainText("AutoApply");
  await expect(page.getByRole("checkbox", { name: /select for preparation/i }).first()).toBeVisible();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await evidence(page, "sp69-connected-cv-explicit-mode.png");
});

test("SP70: Manual, Assisted and AutoApply explain and preserve distinct job actions", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Fictional-CV.pdf",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await expect(page.getByRole("heading", { name: "How do you want to apply?" })).toBeVisible();
  await page.getByRole("button", { name: /Apply manually/i }).last().click();
  await expect(page.getByText("Choose one job to continue")).toBeVisible();
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await expect(page.getByLabel("Next step for Junior Data Analyst")).toBeVisible();
  await expect(page.getByRole("link", { name: /Apply on employer site/i })).toBeVisible();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await evidence(page, "sp70-selected-manual-next-action.png");
  await page.getByRole("button", { name: /Apply with AI help/i }).click();
  await expect(page.getByRole("button", { name: /Prepare CV & application/i })).toBeVisible();
  await page.getByRole("button", { name: /AutoApply/i }).click();
  await expect(page.getByRole("checkbox", { name: /Select for preparation/i }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Prepare applications & start agents/i })).toBeDisabled();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await evidence(page, "sp70-autoapply-selection-before-preparation.png");
});

test("SP75: one-click CV-matched AutoApply shortlist prepares only reviewed current job drafts", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Fictional-IT-CV.pdf",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await page.getByRole("button", { name: /AutoApply/i }).click();
  await expect(page.getByRole("button", { name: "Prepare applications & start agents" }))
    .toBeDisabled();
  const suggested = page.getByRole("button", { name: "Select 1 CV-title matched job" });
  await expect(suggested).toBeEnabled();
  await suggested.click();
  await expect(page.getByText("1 of 15 vacancies selected")).toBeVisible();
  const matchedJob = page.locator(".flow-job").filter({ hasText: "Junior Data Analyst" });
  const exploratoryJob = page.locator(".flow-job").filter({ hasText: "Software Tester" });
  await expect(matchedJob.getByRole("checkbox", { name: "Selected" }))
    .toBeChecked();
  await expect(exploratoryJob.getByRole("checkbox", { name: "Select for preparation" }))
    .not.toBeChecked();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  await page.getByText("Review 1 selected job before preparing").click();
  await expect(page.locator(".flow-shortlist-review")).toContainText("Junior Data Analyst");
  await evidence(page, "sp75-one-click-cv-matched-shortlist.png");
  await page.getByRole("button", { name: "Prepare applications & start agents" }).click();
  await expect.poll(() => state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await expect(page.getByRole("heading", { name: /My applications/i }).first()).toBeVisible();
  // Even after an AutoApply batch, the result is a private draft, not an
  // employer response or permission for unattended final submission.
  await expect(page.getByRole("region", { name: "Application review queue" }))
    .toContainText("1 private draft to finish");
  await expect(page.getByRole("region", { name: "Application review queue" }))
    .toContainText("0 employer-acknowledged");
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await evidence(page, "sp75-private-shortlist-draft-after-preparation.png");
});

test("SP75: a changed CV match search clears the prior AutoApply shortlist before preparation", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Fictional-IT-CV.pdf",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await page.getByRole("button", { name: /AutoApply/i }).click();
  await page.getByRole("button", { name: "Select 1 CV-title matched job" }).click();
  await expect(page.getByText("1 of 15 vacancies selected")).toBeVisible();
  await page.getByRole("searchbox", { name: "Filter matching jobs" }).fill("Different employer");
  await expect(page.getByText("0 of 15 vacancies selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare applications & start agents" }))
    .toBeDisabled();
  expect(state.applicationWorkspaceCreates).toEqual([]);
});

test("existing job-search cards open the requested assisted journey without creating a draft", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Synthetic-CV.pdf",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Find jobs", exact: true }).click();
  const analystCard = page.locator(".search-result-card").filter({ hasText: "Junior Data Analyst" });
  await analystCard.getByRole("button", { name: /Apply with AI/i }).click();
  await expect(page.getByRole("heading", { name: "Upload your CV. Choose your method. Apply." })).toBeVisible();
  await expect(page.locator(".flow-mode.selected")).toContainText("Apply with AI help");
  await expect(page.locator(".flow-job.highlighted")).toContainText("Junior Data Analyst");
  expect(state.applicationWorkspaceCreates).toEqual([]);
});

test("SP87 production build puts CV first, locks methods, and renders the actual start choices", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  const logo = page.locator("svg[aria-label='SmartPloy turquoise and navy mark']");
  await expect(logo).toBeVisible();
  const bounds = await logo.boundingBox();
  expect(bounds?.width).toBeGreaterThan(20);
  expect(bounds?.height).toBeGreaterThan(20);
  await expect(page.getByRole("button", { name: /Upload CV first/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Create CV from scratch/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /apply manually/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /apply with AI/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /autoapply/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /just find jobs/i })).toBeVisible();
  await page.getByText(/Advanced: customize search preferences/i).click();
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
  await page.getByRole("button", { name: /Just find jobs/i }).click();
  await expect(page.getByRole("heading", { name: "IT, data & planning jobs in Finland" })).toBeVisible();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText("Software Tester")).toBeVisible();
  await expect(page.getByText("General listing")).toHaveCount(2);
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  expect(state.lastSave?.mode).toBe("general");
  expect(state.lastSave?.roles).toEqual([]);
  await evidence(page, "synthetic-general-search.png");

  await page.getByRole("button", { name: "Advanced settings" }).click();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await page.getByPlaceholder(/Data analyst, Junior software tester/i).fill("Data Analyst");
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await expect(page.getByText("87% search match")).toBeVisible();
  await page.getByRole("button", { name: "Why shown" }).click();
  await expect(page.getByText(/not a verified skills or eligibility assessment/i)).toBeVisible();
  expect(state.preferences.roles).toEqual(["Data Analyst"]);
  await evidence(page, "synthetic-personalized-search.png");

  await page.getByRole("button", { name: "Advanced settings" }).click();
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
  await page.getByRole("button", { name: "Advanced settings" }).click();
  await page.getByRole("radio", { name: /General job search/i }).check();
  const readsBeforeSave = preferenceReads;
  await page.getByRole("button", { name: /Save search preferences/i }).click();
  await saveStarted;
  await expect(page.getByRole("button", { name: /Saving/i })).toBeDisabled();

  await page.getByRole("button", { name: "Refresh workspace" }).click();
  expect(preferenceReads).toBe(readsBeforeSave);
  expect(state.preferences.mode).toBe("personalized");

  finishSave();
  await expect(page.getByRole("heading", { name: "IT & planning opportunities across Finland" })).toBeVisible();
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
  await page.getByRole("button", { name: "Advanced settings" }).click();
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
  await page.getByRole("button", { name: "Advanced settings" }).click();
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
  await page.getByRole("button", { name: "Find jobs", exact: true }).click();
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
  // Account B has no CV; the START JOURNEY must reset to Step 1.
  // General search cards may still offer an "Apply manually" shortcut,
  // but that route is separately guarded and cannot select a mode pre-CV.
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await expect(page.locator(".flow-start-grid-methods")).toHaveCount(0);
  await page.getByRole("button", { name: "Find jobs", exact: true }).click();
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
  await page.getByRole("button", { name: "Advanced settings" }).click();
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
  await page.getByRole("button", { name: "Advanced settings" }).click();
  await expect(page.getByRole("radio", { name: /General job search/i })).toBeChecked();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await expect(page.getByPlaceholder(/Data analyst, Junior software tester/i))
    .toHaveValue("Account B role");
  await page.getByRole("button", { name: "Start here", exact: true }).click();
  await expect(page.getByText("PRIVATE-ACCOUNT-A.pdf")).toHaveCount(0);
  await expect(page.getByText("ACCOUNT-B.pdf")).toBeVisible();
});

test("a delayed application-draft response is discarded after same-email account switch", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "PRIVATE-ACCOUNT-A.pdf",
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
  await page.locator(".flow-start-card").filter({ hasText: "Apply manually" }).click();
  await expect(page.getByRole("heading", { name: "Jobs from your CV" })).toBeVisible();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await page.getByRole("button", { name: "Save application draft", exact: true }).click();
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
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await page.getByRole("button", { name: /Just find jobs/i }).click();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeVisible();
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  await evidence(page, "synthetic-general-mobile.png");
});
