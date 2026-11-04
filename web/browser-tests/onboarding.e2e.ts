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
  localAIProbeRequests: number;
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
  readyAI?: boolean;
  masterCVSha256?: string;
  masterCVText?: string;
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
    localAIProbeRequests: 0,
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

    if (path === "/api/v1/local-ai/self-test" && request.method() === "POST") {
      const body = JSON.parse(request.postData() || "{}");
      if (!options.readyAI || body.acknowledge_synthetic_inference !== true ||
          request.headers()["x-smartploy-expected-user-id"] !== state.userId) {
        await response(route, { detail: "Synthetic proof requires explicit owner approval" }, 403);
      } else {
        state.localAIProbeRequests += 1;
        await response(route, {
          inference_succeeded: true, model: "synthetic-browser-only-model",
          provider: "local_obumai_ollama", synthetic_only: true,
          applicant_data_transferred: false, external_actions_performed: 0,
          documents_changed: false,
        });
      }
      return;
    }

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
    if (path === "/api/v1/profile/cv/editor" && request.method() === "GET") {
      if (!state.cvFilename || !options.masterCVSha256) {
        await response(route, {detail: "No version-verifiable synthetic master CV"}, 404);
      } else {
        await response(route, {
          present: true, text: options.masterCVText || "", sha256: options.masterCVSha256,
          filename: state.cvFilename, created_by_editor: false, history: [],
          employer_actions_performed: 0, approved_profile_facts_added: 0,
        });
      }
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
        request.method() === "PUT") {
      const id = decodeURIComponent(path.slice("/api/v1/application-workspaces/".length));
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      const owned = state.privateWorkspaces[state.userId] || [];
      const existing = owned.find(item => item.workspace_id === id);
      if (!existing || body.expected_revision !== existing.revision ||
          request.headers()["x-smartploy-expected-user-id"] !== state.userId ||
          typeof body.cv_text !== "string" || typeof body.cover_letter_text !== "string") {
        await response(route, {detail: "Owner and exact revision are mandatory"}, 409);
      } else {
        const edited = {
          ...existing, cv_text: body.cv_text,
          cover_letter_text: body.cover_letter_text,
          revision: existing.revision + 1,
        };
        state.privateWorkspaces[state.userId] = owned.map(item =>
          item.workspace_id === id ? edited : item
        );
        await response(route, {workspace: edited});
      }
      return;
    }
    if (path.startsWith("/api/v1/application-workspaces/") &&
        /\/preview\/(cv|letter)\/pdf$/.test(path) && request.method() === "GET") {
      const match = path.match(
        /^\/api\/v1\/application-workspaces\/([^/]+)\/preview\/(cv|letter)\/pdf$/
      );
      const id = match ? decodeURIComponent(match[1]) : "";
      const expectedRevision = Number(new URL(request.url()).searchParams.get("expected_revision"));
      const owned = (state.privateWorkspaces[state.userId] || [])
        .find(item => item.workspace_id === id);
      if (!owned) {
        await response(route, {detail: "Not a workspace owned by this user"}, 404);
      } else if (!Number.isSafeInteger(expectedRevision) || expectedRevision !== owned.revision) {
        await response(route, {detail: "Saved documents changed; refresh to review"}, 409);
      } else {
        // Synthetic only: real PDF bytes and content are proved in Python API tests.
        // This tests browser route, exact revision, and no employer transfer.
        await route.fulfill({
          status: 200,
          contentType: "application/pdf",
          headers: {
            "Content-Disposition": "inline; filename=\"synthetic-preview.pdf\"",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
          },
          body: "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
        });
      }
      return;
    }
    if (path.startsWith("/api/v1/application-workspaces/") &&
        path.endsWith("/download/package.zip") && request.method() === "GET") {
      const id = decodeURIComponent(path.slice(
        "/api/v1/application-workspaces/".length, -"/download/package.zip".length,
      ));
      const owned = (state.privateWorkspaces[state.userId] || [])
        .find(item => item.workspace_id === id);
      const revisionParam = new URL(request.url()).searchParams.get("expected_revision");
      if (!owned) {
        await response(route, {detail: "No owner-scoped synthetic application"}, 404);
      } else if (!revisionParam || !/^[1-9][0-9]*$/.test(revisionParam) ||
                 !Number.isSafeInteger(Number(revisionParam))) {
        await response(route, {detail: "Saved revision is required"}, 422);
      } else if (Number(revisionParam) !== owned.revision) {
        await response(route, {detail: "Saved documents changed; refresh to review"}, 409);
      } else {
        // Real file contents are tested by backend ZIP/PDF/DOCX tests.
        // An empty valid ZIP here proves browser download/filename routing.
        await route.fulfill({
          status: 200,
          contentType: "application/zip",
          headers: {
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'attachment; filename="synthetic-application-package.zip"',
            "X-Content-Type-Options": "nosniff",
          },
          body: Buffer.from("UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==", "base64"),
        });
      }
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
        ? { present: true, filename: state.cvFilename, size_bytes: 1200,
            ...(options.masterCVSha256 ? {sha256: options.masterCVSha256} : {}) }
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
        configured: Boolean(options.readyAI), ready: Boolean(options.readyAI),
        provider: options.readyAI ? "local_obumai_ollama" : "disabled",
        model: options.readyAI ? "synthetic-browser-only-model" : "",
        external_ai_forwarding: false,
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

test("SP87 CV-less job-card shortcut cannot bypass upload and choose Manual", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  const card = page.locator(".search-result-card").filter({ hasText: "Junior Data Analyst" });
  await card.getByRole("button", { name: /Apply manually/i }).click();
  await expect(page.getByRole("heading", { name: "From your CV to a complete application." })).toBeVisible();
  await expect(page.getByText(/All three application methods are visible below/)).toBeVisible();
  await expect(page.getByRole("group", { name: "Choose application method" })).toBeVisible();
  for (const mode of ["manual", "assisted", "automatic"]) {
    await expect(page.locator(`.flow-mode[data-flow-mode="${mode}"]`)).toBeDisabled();
  }
  expect(state.applicationWorkspaceCreates).toEqual([]);
});

test("CV-first manual application goes from upload to real matching and selected private draft", async ({ page }) => {
  const state = await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await expect(page.locator('.flow-start-card[data-flow-mode="manual"]')).toBeVisible();
  await expect(page.locator('.flow-start-card[data-flow-mode="manual"]')).toBeDisabled();
  await page.locator("input[aria-label='Select CV to upload']").setInputFiles({
    name: "Synthetic-IT-CV.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("IN-TEST CV BLOB; no real CV"),
  });
  await expect(page.getByText("Synthetic-IT-CV.docx is ready")).toBeVisible();
  await expect(page.getByRole("group", { name: "Choose application method" })).toBeVisible();
  await page.getByRole("button", { name: /Apply manually/i }).click();
  await expect(page.getByRole("heading", {
    name: "From your CV to a complete application.",
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

test("SP94: private quick preparation works then Assisted/Automatic completion survives browser reload", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Fictional-IT-CV.pdf",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await page.locator('.flow-mode[data-flow-mode="automatic"]').click();
  const quick = page.getByRole("button", { name: "Prepare 1 private draft now" });
  await expect(quick).toBeEnabled();
  expect(state.applicationWorkspaceCreates).toEqual([]);
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    expect(dialog.message()).toContain("Junior Data Analyst · Example Oy");
    expect(dialog.message()).toContain("NOT contact an employer");
    await dialog.accept();
  });
  await quick.click();
  await expect.poll(() => state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await expect(page.getByRole("region", { name: "Application review queue" }))
    .toContainText("1 private draft to finish");
  await evidence(page, "sp94-quick-private-autoapply-draft.png");

  // A fresh browser load has no remembered method, but the private
  // application survives in the owner's server-side workspace.
  await page.reload();
  await page.getByRole("button", { name: "My applications" }).click();
  const resume = page.getByRole("region", { name: "Choose how to finish saved applications" });
  await expect(resume).toBeVisible();
  const methods = resume.getByRole("group", { name: "Choose application completion method" });
  await expect(methods.locator("button")).toHaveCount(3);
  await expect(methods.locator('button[aria-pressed="true"]')).toHaveCount(0);
  await methods.locator('button[data-resume-mode="assisted"]').click();
  await expect(page.getByRole("region", { name: "Assisted application walkthrough" })).toBeVisible();
  await methods.locator('button[data-resume-mode="automatic"]').click();
  await expect(page.getByRole("region", { name: "Authorized AutoApply batch" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Application review queue" }))
    .toContainText("0 employer-acknowledged");
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await evidence(page, "sp94-saved-draft-resume-after-reload.png");
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
  await expect(page.getByRole("heading", { name: "From your CV to a complete application." })).toBeVisible();
  await expect(page.locator(".flow-mode.selected")).toContainText("Apply with AI help");
  await expect(page.locator(".flow-job.highlighted")).toContainText("Junior Data Analyst");
  expect(state.applicationWorkspaceCreates).toEqual([]);
});

test("SP93 production build shows all three CV-locked methods with the full sidebar", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  const logo = page.locator(".sp99-identity .sp99-identity-mark");
  await expect(logo).toBeVisible();
  const bounds = await logo.boundingBox();
  expect(bounds?.width).toBeGreaterThan(20);
  expect(bounds?.height).toBeGreaterThan(20);
  await expect(page.getByRole("button", { name: /Upload CV first/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Create CV from scratch/i })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply for jobs" })).toBeVisible();
  for (const mode of ["manual", "assisted", "automatic"]) {
    const card = page.locator(`.flow-start-card[data-flow-mode="${mode}"]`);
    await expect(card).toBeVisible();
    await expect(card).toBeDisabled();
  }
  await expect(page.getByRole("button", { name: /just find jobs/i })).toBeVisible();
  await page.getByText(/Optional: set your job search preferences/i).click();
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
  const modal = page.getByRole("dialog", { name: "Add a job and start applying" });
  await modal.getByPlaceholder("e.g. Junior Data Analyst").fill("PRIVATE-BOOKMARK-A");
  await modal.getByPlaceholder("Employer name").fill("Fictional Private Company");
  await modal.getByPlaceholder("Paste the responsibilities and key requirements here.")
    .fill("User-saved reference, not a verified posting");
  await modal.getByRole("button", { name: "Save job only" }).click();

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
  await expect(page.locator(".flow-start-grid-methods .flow-start-card")).toHaveCount(3);
  await expect(page.locator('.flow-start-card[data-flow-mode="automatic"]')).toBeDisabled();
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
  await expect(page.getByText("PRIVATE-ACCOUNT-A.pdf", { exact: true })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "CV connected. Choose how to apply." })).toBeVisible();
  await page.getByRole("button", { name: "Advanced settings" }).click();
  await expect(page.getByRole("radio", { name: /General job search/i })).toBeChecked();
  await page.getByRole("radio", { name: /Personalized jobs/i }).check();
  await expect(page.getByPlaceholder(/Data analyst, Junior software tester/i))
    .toHaveValue("Account B role");
  await page.getByRole("button", { name: "Start here", exact: true }).click();
  await expect(page.getByText("PRIVATE-ACCOUNT-A.pdf")).toHaveCount(0);
  await expect(page.getByText("ACCOUNT-B.pdf", { exact: true })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "CV connected. Choose how to apply." })).toBeVisible();
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
  await expect(page.locator(".sp99-identity .sp99-identity-mark")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await page.getByRole("button", { name: /Just find jobs/i }).click();
  await expect(page.getByText("Junior Data Analyst")).toBeVisible();
  await expect(page.getByText(/Some optional profile or AI tools are temporarily unavailable/i)).toBeVisible();
  await expect(page.getByText(/search match/i)).toHaveCount(0);
  await evidence(page, "synthetic-general-mobile.png");
});

test("SP97: Career tools provides a truthful private AI entry but never bypasses CV-first review", async ({ page }) => {
  const state = await installSyntheticApi(page, { unavailableAI: true });
  const aiGenerations: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/ai-suggestions") && request.method() === "POST") {
      aiGenerations.push(request.url());
    }
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await page.getByRole("button", { name: "CV & AI tools" }).click();
  const readiness = page.getByLabel("Private AI writing readiness");
  await expect(readiness).toBeVisible();
  await expect(readiness).toContainText("Complete English/Finnish letters");
  await page.getByRole("button", { name: /AI writing assistant/i }).click();
  await expect(page.getByRole("heading", {
    name: "From your CV to a complete application.",
  })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload CV & find jobs" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Choose application method" })).toBeVisible();
  await expect(page.locator(".flow-mode.selected")).toHaveCount(0);
  expect(state.applicationWorkspaceCreates).toEqual([]);
  expect(aiGenerations).toEqual([]);
  await evidence(page, "sp97-ai-writing-cv-first-gate.png");
});


test("SP98: real inference is an explicit synthetic-only action inside a saved Assisted draft", async ({ page }) => {
  const state = await installSyntheticApi(page, {
    initial: { completed: true, mode: "general", revision: 1 },
    cvFilename: "Synthetic-owned-CV.pdf",
    readyAI: true,
  });
  const privateModelDrafts: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/ai-suggestions") && request.method() === "POST") {
      privateModelDrafts.push(request.url());
    }
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/");
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await page.getByRole("button", { name: /Apply with AI help/i }).last().click();
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await page.getByRole("button", { name: /Prepare CV & application/i }).click();
  await expect(page.getByRole("heading", { name: /My applications/i }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Run real AI test" })).toBeEnabled();
  expect(state.localAIProbeRequests).toBe(0);
  await page.getByRole("button", { name: "Run real AI test" }).click();
  await expect(page.getByRole("status", {
    name: "Private local model inference verified",
  })).toBeVisible();
  expect(state.localAIProbeRequests).toBe(1);
  expect(privateModelDrafts).toEqual([]);
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await evidence(page, "sp98-private-model-synthetic-generation-proof.png");
});


test("SP99 original Finnish panorama and complete logo restore the earlier page without hiding CV flow", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto("/");
  const panorama = page.getByRole("region", { name: "Finland winter archipelago cover" });
  await expect(panorama).toBeVisible();
  const image = panorama.getByRole("img", { name: /Original artwork: rose-gold winter light/ });
  await expect(image).toBeVisible();
  const loaded = await image.evaluate((node) => {
    const picture = node as HTMLImageElement;
    return { complete: picture.complete, naturalWidth: picture.naturalWidth };
  });
  expect(loaded.complete).toBe(true);
  expect(loaded.naturalWidth).toBeGreaterThan(100);
  const avif = await page.request.get("/finland-archipelago-winter.avif");
  expect(avif.ok()).toBe(true);
  expect((await avif.body()).byteLength).toBeGreaterThan(2000);
  const svg = await page.request.get("/finland-archipelago-winter.svg");
  expect(svg.ok()).toBe(true);
  expect(await svg.text()).toContain("Original Finland winter archipelago");
  const fullLogo = page.getByRole("group", { name: "SmartPloy complete page logo" });
  await expect(fullLogo).toBeVisible();
  const brandMark = fullLogo.locator(".sp99-identity-mark");
  await expect(brandMark).toBeVisible();
  const logoRect = await brandMark.boundingBox();
  expect(logoRect?.width).toBeGreaterThanOrEqual(48);
  expect(logoRect?.height).toBeGreaterThanOrEqual(48);
  const pageLogo = fullLogo.locator(".sp99-identity-text strong");
  await expect(pageLogo).toHaveText("SmartPloy");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.locator('.flow-start-card[data-flow-mode="assisted"]')).toBeDisabled();
  await evidence(page, "sp99-finland-cover-full-logo-cv-first-light.png");
});

test("SP99 dark/light mode is usable, persists after reload, and does not remove the sidebar", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  const panel = page.locator(".flow-start");
  const lightSurface = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
  const toggle = page.getByRole("button", { name: "Switch to dark mode" });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-smartploy-theme", "dark");
  const darkSurface = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(darkSurface).not.toBe(lightSurface);
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.getByRole("group", { name: "SmartPloy complete page logo" })).toBeVisible();
  await evidence(page, "sp99-finland-cover-full-logo-dark.png");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-smartploy-theme", "dark");
  await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-smartploy-theme", "light");
  const restored = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(restored).toBe(lightSurface);
});

test("SP99 mobile has visible whole logo and an operable theme toggle without losing navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installSyntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Finland winter archipelago cover" })).toBeVisible();
  await expect(page.getByRole("group", { name: "SmartPloy complete page logo" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-smartploy-theme", "dark");
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.locator(".sidebar .site-brand-mark")).toBeVisible();
  await page.getByRole("button", { name: "Close navigation" }).click();
  await expect(page.getByRole("heading", { name: "Start with your CV." })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(horizontalOverflow).toBe(false);
  await evidence(page, "sp99-finland-mobile-dark-logo.png");
});


test("SP104: actual browser preserves unsaved cover letter after cancelled navigation", async ({ page }) => {
  const state = await installSyntheticApi(page, { cvFilename: "Synthetic-Approved-CV.docx" });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "CV connected. Choose how to apply." })).toBeVisible();
  await page.locator('.flow-start-card[data-flow-mode="manual"]').click();
  await expect(page.getByRole("heading", { name: "Jobs from your CV" })).toBeVisible();
  await page.getByRole("button", { name: "Choose this job" }).first().click();
  await page.getByRole("button", { name: "Save application draft" }).click();
  const letter = page.getByRole("textbox", { name: "Editable cover letter text" });
  await expect(letter).toBeVisible();
  const unsaved = "SYNTHETIC ONLY: complete applicant letter with unsaved additional evidence.";
  await letter.fill(unsaved);

  let warning = "";
  page.once("dialog", async dialog => {
    warning = dialog.message();
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  expect(warning).toContain("unsaved changes to your application CV or cover letter");
  await expect(letter).toHaveValue(unsaved);
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);

  page.once("dialog", async dialog => { await dialog.accept(); });
  await page.getByRole("button", { name: "Apply for jobs" }).click();
  await expect(page.getByRole("heading", { name: "How do you want to apply?" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Editable cover letter text" })).toHaveCount(0);
  // Leaving a draft is a local navigation only, never an employer request.
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
});


test("SP105: compare and deliberately use a newer master CV in one saved job without employer submission", async ({page}) => {
  const fullMaster = "Full verified applicant CV in private synthetic fixture. Python, SQL, Power BI, Azure and project evidence.";
  const state = await installSyntheticApi(page, {
    cvFilename: "Current-master-CV.docx",
    masterCVSha256: "b".repeat(64),
    masterCVText: fullMaster,
  });
  await page.goto("/");
  await page.locator('.flow-start-card[data-flow-mode="manual"]').click();
  await expect(page.getByRole("heading", {name: "Jobs from your CV"})).toBeVisible();
  await page.getByRole("button", {name: "Choose this job"}).first().click();
  await page.getByRole("button", {name: "Save application draft"}).click();
  const cv = page.getByRole("textbox", {name: "Editable CV text"});
  const letter = page.getByRole("textbox", {name: "Editable cover letter text"});
  await expect(cv).toHaveValue("FICTIONAL CV draft for Junior Data Analyst");
  await expect(letter).toHaveValue("FICTIONAL letter for Example Oy");
  const panel = page.getByRole("region", {name: "CV version and comparison"});
  await expect(panel).toContainText("started from an earlier master CV");
  await panel.getByRole("button", {name: "Compare with current master CV"}).click();
  const comparison = page.getByRole("region", {name: "Job-specific CV versus current master CV"});
  await expect(comparison).toContainText(fullMaster);
  await expect(cv).toHaveValue("FICTIONAL CV draft for Junior Data Analyst");
  page.once("dialog", async dialog => dialog.accept());
  await panel.getByRole("button", {name: /Use current master CV in this job draft/i}).click();
  await expect(cv).toHaveValue(fullMaster);
  await expect(letter).toHaveValue("FICTIONAL letter for Example Oy");
  await page.getByRole("button", {name: "Undo master CV replacement"}).click();
  await expect(cv).toHaveValue("FICTIONAL CV draft for Junior Data Analyst");
  await expect(letter).toHaveValue("FICTIONAL letter for Example Oy");
  // The first copy and its undo were both editor-only.
  expect(state.privateWorkspaces[state.userId][0].revision).toBe(1);
  await panel.getByRole("button", {name: "Compare with current master CV"}).click();
  await expect(comparison).toContainText(fullMaster);
  page.once("dialog", async dialog => dialog.accept());
  await panel.getByRole("button", {name: /Use current master CV in this job draft/i}).click();
  await expect(cv).toHaveValue(fullMaster);
  expect(state.privateWorkspaces[state.userId][0].revision).toBe(1);
  await page.getByRole("button", {name: /^Save changes$/}).click();
  await expect.poll(() => state.privateWorkspaces[state.userId][0].revision).toBe(2);
  expect(state.privateWorkspaces[state.userId][0].cv_text).toBe(fullMaster);
  expect(state.privateWorkspaces[state.userId][0].cover_letter_text)
    .toBe("FICTIONAL letter for Example Oy");
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  await expect(page.getByRole("button", {name: /Submit reviewed application to authorized/i}))
    .toHaveCount(0);
  await evidence(page,"sp105-current-master-cv-reconciliation.png");
});


test("SP106: one saved job downloads a private CV and letter ZIP without employer submission", async ({page}) => {
  const state = await installSyntheticApi(page,{cvFilename:"User-owned-CV.docx"});
  await page.goto("/");
  await page.locator('.flow-start-card[data-flow-mode="manual"]').click();
  await page.getByRole("button",{name:"Choose this job"}).first().click();
  await page.getByRole("button",{name:"Save application draft"}).click();
  const panel = page.getByRole("region",{name:"Complete application file package"});
  const link = panel.getByRole("link",{
    name:"Download complete application ZIP with CV and cover letter PDF and DOCX",
  });
  await expect(link).toHaveAttribute(
    "href", /\/download\/package\.zip\?expected_revision=1$/
  );
  const priorVersionUrl = (await link.getAttribute("href"))!;
  const letter = page.getByRole("textbox",{name:"Editable cover letter text"});
  await letter.fill("Saved applicant letter with a genuinely reviewed job-specific correction.");
  await expect(panel.getByLabel(
    "Download complete application ZIP with CV and cover letter PDF and DOCX"
  )).toHaveAttribute("aria-disabled","true");
  await page.getByRole("button",{name:/^Save changes$/}).click();
  await expect(link).toHaveAttribute("aria-disabled","false");
  await expect(link).toHaveAttribute(
    "href", /\/download\/package\.zip\?expected_revision=2$/
  );
  // A stale link in another browser tab cannot silently export a newer CV.
  const stale = await page.evaluate(async (url) => {
    const result = await fetch(url, {credentials: "same-origin", cache: "no-store"});
    return result.status;
  }, priorVersionUrl);
  expect(stale).toBe(409);
  const missing = await page.evaluate(async (url) =>
    (await fetch(url, {credentials: "same-origin", cache: "no-store"})).status,
    priorVersionUrl.split("?")[0]
  );
  expect(missing).toBe(422);
  const downloadPromise = page.waitForEvent("download");
  await link.click();
  const file = await downloadPromise;
  expect(file.suggestedFilename()).toBe("synthetic-application-package.zip");
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  expect(state.privateWorkspaces[state.userId][0].status).toBe("draft");
  expect(state.privateWorkspaces[state.userId][0].revision).toBe(2);
});


test("SP107: exact saved PDFs are previewable without employer submission or stale revision drift", async ({page}) => {
  const state = await installSyntheticApi(page, {cvFilename: "Owned-CV.docx"});
  await page.goto("/");
  await page.locator('.flow-start-card[data-flow-mode="assisted"]').click();
  await page.getByRole("button", {name: "Choose this job"}).first().click();
  await page.getByRole("button", {name: "Prepare CV & application"}).click();
  const panel = page.getByRole("region", {name: "Complete application file package"});
  const cvPreview = panel.getByRole("link", {name: "Preview saved CV PDF in a new tab"});
  const letterPreview = panel.getByRole("link", {name: "Preview saved cover letter PDF in a new tab"});
  await expect(cvPreview).toHaveAttribute("target", "_blank");
  await expect(cvPreview).toHaveAttribute("rel", "noopener noreferrer");
  await expect(cvPreview).toHaveAttribute("href", /\/preview\/cv\/pdf\?expected_revision=1$/);
  // Browser-context fetch exercises the installed account-scoped synthetic
  // page route. Playwright's separate page.request API bypasses page.route.
  const previewRequest = async (url: string) => page.evaluate(async (href) => {
    const result = await fetch(href, { credentials: "same-origin", cache: "no-store" });
    return {status: result.status, media: result.headers.get("content-type"),
      disposition: result.headers.get("content-disposition")};
  }, url);
  const first = await previewRequest((await cvPreview.getAttribute("href"))!);
  expect(first.status).toBe(200);
  expect(first.media).toContain("application/pdf");
  expect(first.disposition).toContain("inline");

  const editor = page.getByRole("textbox", {name: "Editable cover letter text"});
  await editor.fill("Revised applicant-owned complete letter text for a synthetic employer.");
  await expect(panel.getByLabel("Preview saved CV PDF in a new tab")).toHaveAttribute(
    "aria-disabled", "true"
  );
  await expect(panel.getByLabel("Preview saved cover letter PDF in a new tab"))
    .not.toHaveAttribute("href", /preview\/letter\/pdf/);
  await page.getByRole("button", {name: /^Save changes$/}).click();
  await expect(cvPreview).toHaveAttribute("href", /\/preview\/cv\/pdf\?expected_revision=2$/);
  await expect(letterPreview).toHaveAttribute("href", /\/preview\/letter\/pdf\?expected_revision=2$/);
  const latest = await previewRequest((await letterPreview.getAttribute("href"))!);
  expect(latest.status).toBe(200);
  const stale = await previewRequest(
    (await cvPreview.getAttribute("href"))!.replace("expected_revision=2", "expected_revision=1")
  );
  expect(stale.status).toBe(409);
  expect(state.applicationWorkspaceCreates).toEqual(["synthetic-analyst"]);
  expect(state.privateWorkspaces[state.userId][0].revision).toBe(2);
  expect(state.privateWorkspaces[state.userId][0].status).toBe("draft");
});


test("SP124 Prismatic: desktop rail collapses to 76px, survives reload, expands without losing navigation", async ({page}) => {
  await page.setViewportSize({width:1540,height:900});
  await page.emulateMedia({colorScheme:"light"});
  await installSyntheticApi(page);
  await page.goto("/");
  const shell = page.locator(".smartploy-app");
  await expect(page.getByRole("button", {name:"Collapse sidebar"})).toBeVisible();
  await expect(shell).toHaveAttribute("data-sidebar-size","expanded");
  const expandedWidth = await page.locator(".sidebar").evaluate(el => el.getBoundingClientRect().width);
  await page.getByRole("button", {name:"Collapse sidebar"}).click();
  await expect(shell).toHaveAttribute("data-sidebar-size","compact");
  await expect(page.getByRole("button", {name:"Expand sidebar"})).toBeVisible();
  const compactWidth = await page.locator(".sidebar").evaluate(el => el.getBoundingClientRect().width);
  expect(expandedWidth).toBeGreaterThan(200);
  expect(compactWidth).toBeGreaterThanOrEqual(72);
  expect(compactWidth).toBeLessThanOrEqual(80);
  const link = page.getByRole("navigation", {name:"Main navigation"})
    .getByRole("button", {name:"My applications"});
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("title", "My applications");
  await page.reload();
  await expect(shell).toHaveAttribute("data-sidebar-size","compact");
  await page.getByRole("button", {name:"Expand sidebar"}).click();
  await expect(shell).toHaveAttribute("data-sidebar-size","expanded");
});

test("SP124 Prismatic: zoom-equivalent CSS width uses mobile drawer with no sideways overflow", async ({page}) => {
  await page.setViewportSize({width:850,height:870});
  await page.emulateMedia({colorScheme:"dark"});
  await installSyntheticApi(page);
  await page.goto("/");
  const drawer = page.locator("#smartploy-sidebar");
  await expect(page.getByRole("button", {name:"Open menu"})).toBeVisible();
  await page.getByRole("button", {name:"Open menu"}).click();
  await expect(drawer).toHaveClass(/open/);
  await expect(page.getByRole("navigation", {name:"Main navigation"})
    .getByRole("button", {name:"Apply for jobs"})).toBeVisible();
  await page.getByRole("button", {name:"Close menu"}).click();
  await expect(drawer).not.toHaveClass(/open/);
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
});

test("SP124 Prismatic: real dark application next-action and quality cards have legible text", async ({page}) => {
  await page.setViewportSize({width:1366,height:880});
  await page.emulateMedia({colorScheme:"light"});
  await installSyntheticApi(page,{cvFilename:"Synthetic-Approved-CV.docx"});
  await page.goto("/");
  await page.locator('.flow-start-card[data-flow-mode="manual"]').click();
  await expect(page.getByRole("heading",{name:"Jobs from your CV"})).toBeVisible();
  await page.getByRole("button",{name:"Choose this job"}).first().click();
  await page.getByRole("button",{name:"Save application draft"}).click();
  await expect(page.locator(".studio-next-action")).toBeVisible();
  await page.getByRole("button", {name:"Switch to dark mode"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-smartploy-theme","dark");
  const pairs = await page.evaluate(() => {
    const ratio = (a:string,b:string) => {
      const value = (v:string) => {
        const c = v.match(/\d+(?:\.\d+)?/g)?.slice(0,3).map(Number) || [0,0,0];
        const light = (x:number) => {const n=x/255;return n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4};
        return .2126*light(c[0])+.7152*light(c[1])+.0722*light(c[2]);
      };
      const x=value(a),y=value(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
    };
    const next = document.querySelector(".studio-next-action");
    const label = next?.querySelector(".studio-next-action-copy strong");
    const card = document.querySelector(".document-coach-checks li");
    const cardText = card?.querySelector("strong");
    return {
      nextBackground:next ? getComputedStyle(next).backgroundColor : "",
      nextContrast:next&&label ? ratio(getComputedStyle(next).backgroundColor,getComputedStyle(label).color):0,
      checklistBackground:card ? getComputedStyle(card).backgroundColor : "",
      checklistContrast:card&&cardText ? ratio(getComputedStyle(card).backgroundColor,getComputedStyle(cardText).color):0,
    };
  });
  expect(pairs.nextBackground).not.toBe("rgb(255, 255, 255)");
  expect(pairs.checklistBackground).not.toBe("rgb(255, 255, 255)");
  expect(pairs.nextContrast).toBeGreaterThanOrEqual(4.5);
  expect(pairs.checklistContrast).toBeGreaterThanOrEqual(4.5);
});
