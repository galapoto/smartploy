import type {
  ApplicationsResponse,
  Dashboard,
  HealthResponse,
  CVDocument,
  CandidateFact,
  ProfileFactsResponse,
  SessionInfo,
  JobsResponse,
  ManualJobPayload,
  PrivateSavedJob,
  PrivateSavedJobsResponse,
  PreparationResponse,
  ApplicationWorkspace,
  ApplicationWorkspacesResponse
} from "./types";

/** Read-only owner-scoped employer claim posture; never employer receipt. */
export type EmployerAttemptState = {
  previous_attempt_reserved: boolean;
  state: "not_reserved" | "reserved_unverified" | "uncertain";
  requires_human_reconciliation: boolean;
  automatic_employer_submit_authorized: false;
  external_confirmation_verified: false;
  cross_device_server_claim_required: true;
};

export function getEmployerAttemptStatus(workspaceId: string): Promise<EmployerAttemptState> {
  return request<EmployerAttemptState>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/employer-attempt"
  );
}

const API_BASE = (import.meta.env.VITE_SMARTPLOY_API_BASE ?? "").replace(/\/$/, "");

/** Browser mutations must carry the account captured BEFORE any async wait.
 * The server compares it with the authenticated user binding before side effects.
 * This header is a precondition, never a replacement for authentication.
 */
async function request<T>(path: string, init?: RequestInit, expectedUserId?: string): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const isMutation = path.startsWith("/api/") &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  if (isMutation && (!expectedUserId || !expectedUserId.trim())) {
    throw new Error("Your verified SmartPloy account is required before making changes. Reload the page.");
  }
  const response = await fetch(API_BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
      ...(isMutation ? { "X-Smartploy-Expected-User-Id": expectedUserId! } : {})
    }
  });

  if (!response.ok) {
    let message = "Request failed with HTTP " + response.status;
    let loginUrl = "";
    try {
      const body = (await response.json()) as {
        detail?: string;
        login_url?: string;
        error?: { message?: string };
      };
      if (body.detail) message = body.detail;
      if (body.error?.message) message = body.error.message;
      loginUrl = body.login_url ?? "";
    } catch {
      // Keep the HTTP fallback.
    }
    if (
      response.status === 401 &&
      loginUrl.startsWith("/") &&
      typeof window !== "undefined"
    ) {
      window.location.assign(loginUrl);
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function getDashboard(): Promise<Dashboard> {
  return request<Dashboard>("/api/v1/dashboard");
}

export function getApplications(): Promise<ApplicationsResponse> {
  return request<ApplicationsResponse>("/api/v1/applications?limit=12");
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/healthz");
}

export function prepareJob(canonicalKey: string, expectedUserId: string): Promise<PreparationResponse> {
  return request<PreparationResponse>(
    "/api/v1/jobs/" + encodeURIComponent(canonicalKey) + "/prepare",
    { method: "POST" }, expectedUserId
  );
}

export function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/v1/session");
}

export function getJobs(): Promise<JobsResponse> {
  return request<JobsResponse>("/api/v1/jobs");
}

export function getCV(): Promise<CVDocument> {
  return request<CVDocument>("/api/v1/profile/cv");
}

export function getProfileFacts(): Promise<ProfileFactsResponse> {
  return request<ProfileFactsResponse>("/api/v1/profile/facts");
}

export async function uploadCV(file: File, expectedUserId: string): Promise<CVDocument> {
  if (file.size > 5 * 1024 * 1024) {
    throw new Error("Your CV is too large. Please use a PDF or DOCX under 5 MB.");
  }
  if (!/\.(pdf|docx)$/i.test(file.name)) {
    throw new Error("Please choose a PDF or DOCX CV.");
  }
  const buffer = new Uint8Array(await file.arrayBuffer());
  let encoded = "";
  for (let i = 0; i < buffer.length; i += 16384) {
    encoded += String.fromCharCode(...buffer.subarray(i, i + 16384));
  }
  return request<CVDocument>("/api/v1/profile/cv", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_base64: btoa(encoded) })
  }, expectedUserId);
}

export function deleteCV(expectedUserId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/api/v1/profile/cv", { method: "DELETE" }, expectedUserId);
}

export function createFact(fact_type: string, value: string, approved: boolean, expectedUserId: string): Promise<{ fact: CandidateFact }> {
  return request<{ fact: CandidateFact }>("/api/v1/profile/facts", {
    method: "POST",
    body: JSON.stringify({ fact_type, value, approved })
  }, expectedUserId);
}

export function approveFact(fact_id: string, approved: boolean, expectedUserId: string): Promise<{ fact: CandidateFact }> {
  return request<{ fact: CandidateFact }>("/api/v1/profile/facts/" + encodeURIComponent(fact_id), {
    method: "PATCH",
    body: JSON.stringify({ approved })
  }, expectedUserId);
}

export function deleteFact(fact_id: string, expectedUserId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/api/v1/profile/facts/" + encodeURIComponent(fact_id), {
    method: "DELETE"
  }, expectedUserId);
}

/** Save a private bookmark; never submit a listing to the shared ATS registry. */
export function addManualJob(job: ManualJobPayload, expectedUserId: string): Promise<{ status: "saved_private"; job: PrivateSavedJob }> {
  return request<{ status: "saved_private"; job: PrivateSavedJob }>("/api/v1/private-jobs", {
    method: "POST",
    body: JSON.stringify(job)
  }, expectedUserId);
}

export function getPrivateSavedJobs(): Promise<PrivateSavedJobsResponse> {
  return request<PrivateSavedJobsResponse>("/api/v1/private-jobs");
}

export function deletePrivateSavedJob(savedJobId: string, expectedUserId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(
    "/api/v1/private-jobs/" + encodeURIComponent(savedJobId),
    { method: "DELETE" }, expectedUserId
  );
}


export function startApplicationWorkspace(canonicalKey: string, expectedUserId: string): Promise<{ workspace: ApplicationWorkspace; created: boolean }> {
  return request<{ workspace: ApplicationWorkspace; created: boolean }>(
    "/api/v1/jobs/" + encodeURIComponent(canonicalKey) + "/application-workspace",
    { method: "POST" }, expectedUserId
  );
}

export function getApplicationWorkspaces(): Promise<ApplicationWorkspacesResponse> {
  return request<ApplicationWorkspacesResponse>("/api/v1/application-workspaces");
}

export function editApplicationWorkspace(
  workspaceId: string, expectedRevision: number, cvText: string, coverLetterText: string,
  expectedUserId: string
): Promise<{ workspace: ApplicationWorkspace }> {
  return request<{ workspace: ApplicationWorkspace }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId),
    {
      method: "PUT",
      body: JSON.stringify({
        expected_revision: expectedRevision,
        cv_text: cvText,
        cover_letter_text: coverLetterText
      })
    }, expectedUserId
  );
}

export function markApplicationManuallySent(
  workspaceId: string, expectedRevision: number, reference: string, expectedUserId: string
): Promise<{ workspace: ApplicationWorkspace; external_confirmation_verified: false }> {
  return request<{ workspace: ApplicationWorkspace; external_confirmation_verified: false }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/report-applied",
    {
      method: "POST",
      body: JSON.stringify({
        expected_revision: expectedRevision,
        confirmed_external_application: true,
        reference
      })
    }, expectedUserId
  );
}

export function deleteApplicationWorkspace(workspaceId: string, expectedUserId: string): Promise<{ deleted: true }> {
  return request<{ deleted: true }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId),
    { method: "DELETE" }, expectedUserId
  );
}

export function applicationDownloadUrl(
  workspaceId: string, kind: "cv" | "letter", format: "pdf" | "docx"
): string {
  return API_BASE + "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId)
    + "/download/" + kind + "/" + format;
}


export function getLocalAIStatus(): Promise<import("./types").LocalAIStatus> {
  return request<import("./types").LocalAIStatus>("/api/v1/local-ai/status");
}

export function requestLocalAISuggestions(
  workspaceId: string, expectedRevision: number, expectedUserId: string
): Promise<{ suggestion: import("./types").LocalAISuggestion; workspace_revision: number }> {
  return request<{ suggestion: import("./types").LocalAISuggestion; workspace_revision: number }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/ai-suggestions",
    { method: "POST", body: JSON.stringify({
      expected_revision: expectedRevision,
      acknowledge_local_ai_processing: true
    }) }, expectedUserId
  );
}


export function getBrowserHandoffReadiness(workspaceId: string): Promise<import("./types").BrowserHandoffReadiness> {
  return request<import("./types").BrowserHandoffReadiness>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/handoff-readiness"
  );
}

export function createBrowserHandoffPacket(
  workspaceId: string, revision: number, expectedUserId: string
): Promise<{ packet: import("./types").BrowserHandoffPacket; external_actions_performed: false }> {
  return request<{ packet: import("./types").BrowserHandoffPacket; external_actions_performed: false }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/browser-packet",
    { method: "POST", body: JSON.stringify({
      expected_revision: revision,
      confirm_private_data_transfer: true
    }) }, expectedUserId
  );
}


/** Official Lever partner submit is available only with employer-specific
 * reviewed API rights, exact configured posting and a fresh applicant gesture.
 */
/** Hashed server-produced preview of the ALREADY reviewed application.
 * No bearer token, applicant contact data, CV, credential or execution grant.
 */
export type LeverPartnerReviewEvidence = {
  workspace_id: string;
  revision: number;
  document_sha256: string;
  cv_pdf_sha256: string;
  approved_fields_sha256: string;
  cv_pdf_size: number;
  expires_at: string;
};

export type LeverPartnerReadiness = {
  partner_provider: "lever";
  partner_api_configured: boolean;
  independent_partner_rights_reviewed: boolean;
  current_applicant_review_recorded: boolean;
  current_document_and_posting_ready: boolean;
  prior_employer_attempt: boolean;
  provider_acknowledged: boolean;
  eligible_for_explicit_partner_submit: boolean;
  review_evidence: LeverPartnerReviewEvidence | null;
  review_evidence_is_authorization: false;
  unattended_auto_apply_enabled: false;
  automatic_retry_authorized: false;
};

export type LeverProviderAcknowledgment = {
  provider: "lever";
  provider_application_id: string;
  provider_application_acknowledged: true;
  employer_hiring_decision_verified: false;
  automatic_retry_authorized: false;
};

export type LeverPartnerApplyResult =
  | ({state: "provider_acknowledged";external_actions_performed:true} & LeverProviderAcknowledgment)
  | {state:"outcome_uncertain";provider_acknowledged:false;automatic_retry_authorized:false;
      employer_hiring_decision_verified:false;requires_human_reconciliation:true};

export function getLeverPartnerReadiness(workspaceId: string): Promise<LeverPartnerReadiness> {
  return request<LeverPartnerReadiness>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/partner-lever-readiness"
  );
}

export function getLeverPartnerReceipt(
  workspaceId: string
): Promise<{present:boolean;receipt:LeverProviderAcknowledgment|null}> {
  return request<{present:boolean;receipt:LeverProviderAcknowledgment|null}>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/partner-lever-receipt"
  );
}

export function sendLeverPartnerApplication(
  workspaceId: string, revision:number, documentSha:string,
  cvPdfSha:string, fieldsSha:string, pdfSize:number, expectedUserId:string
): Promise<LeverPartnerApplyResult> {
  return request<LeverPartnerApplyResult>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/partner-lever-apply",
    {method:"POST",body:JSON.stringify({
      expected_revision:revision, expected_document_sha256:documentSha,
      expected_cv_pdf_sha256:cvPdfSha,
      expected_fields_sha256:fieldsSha,expected_cv_pdf_size:pdfSize,
      explicit_final_user_approval:true,approve_employer_data_transfer:true,
      affirm_reviewed_employer_form:true,
    })},expectedUserId
  );
}

/** Read-only independent employer-rights posture. There is NO submit capability. */
export type EmployerFinalActionReadiness = {
  operator_permission_reviewed: boolean;
  current_applicant_review_recorded: boolean;
  separate_final_user_approval_recorded: boolean;
  previous_employer_attempt_reserved: boolean;
  trusted_one_use_browser_redemption_available: false;
  final_browser_click_authorized: false;
  employer_submission_performed: false;
  employer_receipt_verified: false;
  blockers: string[];
};

export function getEmployerFinalActionReadiness(
  workspaceId: string
): Promise<EmployerFinalActionReadiness> {
  return request<EmployerFinalActionReadiness>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId)
      + "/final-action-readiness"
  );
}

/** Non-submitting 10-minute final-review record. No extension bearer/grant. */
export type EmployerReviewIntentState = {
  review_recorded: boolean;
  review_state: "not_recorded" | "pending" | "cancelled" | "expired";
  expires_at: string;
  automatic_employer_submit_authorized: false;
  external_actions_performed: false;
  browser_grant_issued: false;
  new_review_recorded?: boolean;
};

export function getEmployerReviewIntent(workspaceId: string): Promise<EmployerReviewIntentState> {
  return request<EmployerReviewIntentState>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/submit-review-intent"
  );
}

export function recordEmployerReviewIntent(
  workspaceId: string, revision: number, documentSha256: string,
  cvPdfSha256: string, expectedUserId: string,
): Promise<EmployerReviewIntentState> {
  return request<EmployerReviewIntentState>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/submit-review-intent",
    { method: "POST", body: JSON.stringify({
      expected_revision: revision,
      expected_document_sha256: documentSha256,
      expected_cv_pdf_sha256: cvPdfSha256,
      confirm_reviewed_application: true,
      acknowledge_manual_only: true,
    }) }, expectedUserId
  );
}

export function cancelEmployerReviewIntent(
  workspaceId: string, expectedUserId: string,
): Promise<EmployerReviewIntentState> {
  return request<EmployerReviewIntentState>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/submit-review-intent",
    { method: "DELETE" }, expectedUserId
  );
}

export function getBrowserReceipt(
  workspaceId: string
): Promise<{ present: boolean; receipt: import("./types").BrowserObservedReceipt | null }> {
  return request<{ present: boolean; receipt: import("./types").BrowserObservedReceipt | null }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/browser-receipt"
  );
}

export function importBrowserReceipt(
  workspaceId: string, receipt: import("./types").BrowserReceiptImport,
  expectedUserId: string
): Promise<{ receipt: import("./types").BrowserObservedReceipt; external_confirmation_verified: false }> {
  return request<{ receipt: import("./types").BrowserObservedReceipt; external_confirmation_verified: false }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/browser-receipt",
    { method: "POST", body: JSON.stringify({
      confirm_user_observed: true,
      receipt
    })}, expectedUserId
  );
}


export function getSearchPreferences(): Promise<import("./types").SearchPreferences> {
  return request<import("./types").SearchPreferences>("/api/v1/search-preferences");
}

export function updateSearchPreferences(
  preferences: import("./types").SearchPreferencesUpdate, expectedUserId: string
): Promise<import("./types").SearchPreferences> {
  return request<import("./types").SearchPreferences>("/api/v1/search-preferences", {
    method: "PUT", body: JSON.stringify(preferences)
  }, expectedUserId);
}

export type AutoStageResult = {
  status: "staged_for_owner_review" | "not_opted_in";
  created: number;
  existing: number;
  considered: number;
  skipped?: Record<string, number>;
  result: "review_only";
  employer_submissions: 0;
  no_employer_actions: true;
  user_must_review_each_draft: true;
};

export function stageMatchedDraftsNow(expectedUserId: string): Promise<AutoStageResult> {
  return request<AutoStageResult>("/api/v1/job-autopilot/stage", {
    method: "POST", body: "{}",
  },expectedUserId);
}

export function getSearchResults(): Promise<import("./types").SearchResults> {
  return request<import("./types").SearchResults>("/api/v1/search-results");
}

/** Inspect saved permissions without triggering an AI request. */
export function getJobAIConsents(): Promise<import("./types").JobAIConsentsResponse> {
  return request<import("./types").JobAIConsentsResponse>("/api/v1/ai-processing-consents");
}

export function getJobAIConsentEvents(): Promise<import("./types").JobAIConsentEventsResponse> {
  return request<import("./types").JobAIConsentEventsResponse>("/api/v1/ai-processing-consents/events");
}

/** The literal true opt-in is sent only from a separate, confirmed user action. */
export function grantJobAIConsent(canonicalKey: string, expectedUserId: string):
    Promise<{ consent: import("./types").JobAIProcessingConsent; created_or_updated: boolean;
              processing_started: false; external_actions_authorized: false }> {
  return request("/api/v1/ai-processing-consents", {
    method: "POST",
    body: JSON.stringify({
      canonical_key: canonicalKey, acknowledge_obumai_processing: true
    })
  }, expectedUserId);
}

export function revokeJobAIConsent(consentId: string, expectedUserId: string):
    Promise<{ consent: import("./types").JobAIProcessingConsent; revoked: true }> {
  return request("/api/v1/ai-processing-consents/" + encodeURIComponent(consentId), {
    method: "DELETE"
  }, expectedUserId);
}
