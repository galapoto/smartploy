export type EmployerSector = "public" | "private" | "unknown";

export interface JobCardData {
  company: string;
  role_title: string;
  location: string;
  work_mode: string;
  deadline: string;
  application_url: string;
  employer_sector: EmployerSector;
  /** Title-derived browse label, never a qualification or eligibility claim. */
  career_area?: "it_data" | "planning" | "other";
  title_experience?: "entry" | "senior" | "unspecified";
  opportunity_kind?: "job" | "internship" | "traineeship" | "graduate";
  source_ids: string[];
  posted_at: string;
  first_seen_at: string;
  last_seen_at: string;
  source_current: boolean;
  source_attribution: string;
  ai_preparation_allowed: boolean;
}

export interface RankingCard {
  canonical_key: string;
  fit_score: number;
  priority_score: number;
  queue: string;
  fit_breakdown: Record<string, number>;
  priority_breakdown: Record<string, number>;
  matched_evidence_ids: string[];
  matched_requirements: string[];
  mandatory_gaps: string[];
  preferred_gaps: string[];
  prepare_recommended: boolean;
  status: string;
  job: JobCardData | null;
}

export interface SourceHealth {
  source_id: string;
  status: string;
  parser_version: string;
  last_attempt_at: string;
  last_success_at: string;
  last_failure_at: string;
  last_item_count: number;
  consecutive_failures: number;
  last_error: string;
  metadata: Record<string, unknown>;
}

export interface ApplicationSummary {
  total_records: number;
  state_counts: Record<string, number>;
  preparing: number;
  awaiting_review: number;
  preparation_blocked: number;
  actually_submitted: number;
  interviews: number;
  offers: number;
  rejections: number;
}

export interface ProfileStatus {
  profile_id?: string;
  ready: boolean;
  approved_fact_count?: number;
  fact_count?: number;
  [key: string]: unknown;
}

export interface WorkerTaskView {
  task_id: string;
  task_kind: string;
  enabled: boolean;
  cadence_seconds: number;
  next_run_at: string;
  last_started_at: string;
  last_completed_at: string;
  last_status: string;
  consecutive_failures: number;
  last_error: string;
  lease_active: boolean;
  lease_until: string;
  metadata: Record<string, unknown>;
}

export interface WorkerSnapshot {
  configured: boolean;
  ready: boolean;
  count: number;
  tasks: WorkerTaskView[];
  error: string;
}

export interface Dashboard {
  top_matches: RankingCard[];
  possible_matches: RankingCard[];
  preparation_counts: Record<string, number>;
  applications: ApplicationSummary;
  source_health: SourceHealth[];
  profile: ProfileStatus;
  worker: WorkerSnapshot;
  external_actions_authorized: boolean;
}


export type ApplicationAgentMilestone = "recruiter_replied" | "interview" | "offer" | "rejected" | "hired";

/** One durable case identity per selected application workspace. */
export interface ApplicationAgent {
  agent_id: string;
  workspace_id: string;
  canonical_key: string;
  role_title: string;
  company: string;
  state: "active" | "paused" | "closed";
  revision: number;
  next_due_at: string;
  last_woke_at: string;
  created_at: string;
  updated_at: string;
  closed_at: string;
  close_reason: "" | "owner_closed" | "rejected" | "hired";
  milestone: ApplicationAgentMilestone | "none";
  milestone_source: "none" | "candidate_self_report";
  workspace_status: "draft" | "self_reported_applied" | "provider_acknowledged";
  observed_workspace_status: "draft" | "self_reported_applied" | "provider_acknowledged";
  followups_sent: number;
  last_followup_at: string;
  followup_suggestion: string;
  external_actions_authorized: false;
  employer_contacted: false;
  notification_channel: "in_app_only";
}

/** SP35: server-prioritized private cases, never inferred employer replies. */
export type ApplicationAgentAttention =
  "status_changed" | "due_review" | "draft_review" |
  "awaiting_response" | "paused" | "closed";

export type ApplicationAgentInboxItem = ApplicationAgent & {
  attention_state: ApplicationAgentAttention;
};

export interface ApplicationAgentInboxPage {
  items: ApplicationAgentInboxItem[];
  count: number;
  has_more: boolean;
  next_offset: number | null;
  background_worker_verified: false;
  external_actions_authorized: false;
}

export interface ApplicationAgentEvent {
  sequence: number;
  event_type: "case_created" | "review_reminder_due" | "case_paused" |
    "case_resumed" | "case_closed" | "followup_due" |
    "candidate_reported_followup" | "candidate_reported_reply" |
    "candidate_reported_interview" | "candidate_reported_offer" |
    "candidate_reported_rejected" | "candidate_reported_hired" |
    "application_self_reported" | "application_provider_acknowledged" |
    "application_draft_review";
  message: string;
  occurred_at: string;
  external_actions_performed: 0;
}

export interface ApplicationRecord {
  application_id: string;
  canonical_key: string;
  package_id: string;
  state: string;
  created_at: string;
  updated_at: string;
  submitted_at: string;
  has_been_submitted: boolean;
  external_confirmation_id: string;
  external_reference: string;
  metadata: Record<string, unknown>;
}

export interface ApplicationsResponse {
  applications: ApplicationRecord[];
  count: number;
}

export interface HealthResponse {
  ok: boolean;
  service: string;
  storage: { mode: string; ready: boolean; error?: string };
  /** Public health intentionally contains no private profile metadata. */
  obumai_configured: boolean;
  worker: {
    configured: boolean;
    ready: boolean;
    count: number;
  };
  external_actions_authorized: boolean;
}

export interface PreparationResponse {
  package_id: string;
  canonical_key: string;
  status: string;
  error?: string;
  updated_at?: string;
}


export interface CVDocument {
  present: boolean;
  filename?: string;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
  updated_at?: string;
  text_preview?: string;
  text_extracted?: boolean;
  created_by_editor?: boolean;
}

/** Full owner-private editor text; unlike the small public-UI CV preview. */
export interface CVEditorArchive {
  sha256: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  archived_at?: string;
  updated_at?: string;
  archived: true;
}
export interface CVEditorDocument {
  present: boolean;
  text: string;
  sha256: string;
  filename: string;
  created_by_editor: boolean;
  history: CVEditorArchive[];
  employer_actions_performed: 0;
  approved_profile_facts_added: 0;
}
export interface CVEditorSaved {
  cv: CVDocument;
  history: CVEditorArchive[];
  employer_actions_performed: 0;
  approved_profile_facts_added: 0;
}

export interface CandidateFact {
  fact_id: string;
  fact_type: string;
  value: string;
  approved: boolean;
  source: string;
  confidence: number;
  created_at: string;
}

export interface ProfileFactsResponse {
  facts: CandidateFact[];
  count: number;
}

export interface SessionInfo {
  authenticated: boolean;
  email?: string;
  auth_source?: string;
  // Server-issued identity, not user-editable profile data. Emails are not
  // globally unique identity keys and must never be used for account binding.
  user_id?: string;
  profile_id?: string;
  subject_fingerprint?: string;
}

export interface JobAIProcessingConsent {
  consent_id: string;
  canonical_key: string;
  processor: "obumai";
  purpose: "application_draft";
  mode: "unattended";
  job_snapshot_sha256: string;
  evidence_sha256: string;
  revision: number;
  granted_at: string;
  revoked_at: string;
  active: boolean;
  processing_started: false;
  employer_actions_authorized: false;
}

export interface JobAIProcessingConsentEvent {
  event_id: string;
  consent_id: string;
  event_type: "granted" | "revoked";
  revision: number;
  job_snapshot_sha256: string;
  evidence_sha256: string;
  occurred_at: string;
}

export interface JobAIConsentsResponse {
  consents: JobAIProcessingConsent[];
  count: number;
  private: true;
  unattended_processing_enabled: false;
}

export interface JobAIConsentEventsResponse {
  events: JobAIProcessingConsentEvent[];
  count: number;
  private: true;
  history_type: "consent_grant_and_withdrawal_only";
}

export interface SavedJob {
  canonical_key: string;
  source_current: boolean;
  source_ids: string[];
  posted_at: string;
  first_seen_at: string;
  job: JobCardData;
}

export interface JobsResponse {
  jobs: SavedJob[];
  count: number;
}

/** User-owned bookmark, never an employer-verified ATS vacancy. */
export interface PrivateSavedJob {
  saved_job_id: string;
  company: string;
  role_title: string;
  location: string;
  description: string;
  application_url: string;
  created_at: string;
  private: true;
  employer_availability_verified: false;
  external_actions_authorized: false;
}

export interface PrivateSavedJobsResponse {
  jobs: PrivateSavedJob[];
  count: number;
  private: true;
}

export interface ManualJobPayload {
  company: string;
  role_title: string;
  location: string;
  description: string;
  application_url: string;
}


export interface ApplicationWorkspace {
  workspace_id: string;
  canonical_key: string;
  role_title: string;
  company: string;
  application_url: string;
  cv_text: string;
  cover_letter_text: string;
  source_cv_sha256: string;
  approved_evidence_ids: string[];
  revision: number;
  status: "draft" | "self_reported_applied" | "provider_acknowledged";
  self_reported_applied_at: string;
  self_reported_reference: string;
  created_at: string;
  updated_at: string;
  authority: {
    may_edit: boolean;
    may_download: boolean;
    may_submit_to_employer: false;
    has_external_submission_proof: false;
  };
}

export interface ApplicationWorkspacesResponse {
  workspaces: ApplicationWorkspace[];
  count: number;
}


export interface LocalAIStatus {
  configured: boolean;
  ready: boolean;
  provider: "disabled" | "local_obumai_ollama";
  model: string;
  external_ai_forwarding: false;
  endpoint_reachable?: boolean;
  failure_category?: "disabled" | "endpoint_unreachable" | "invalid_model_catalog" | "model_not_installed" | "ready";
}

export interface LocalAIProposal {
  schema: "smartploy.local_draft.v1";
  cv_headline: string;
  cv_summary: string;
  cover_letter: string;
  highlights: { text: string; evidence_fact_ids: string[] }[];
  risks: string[];
  review_notes: string[];
}

export interface LocalAISuggestion {
  proposal: LocalAIProposal;
  provider: string;
  model: string;
  approved_evidence_ids: string[];
  external_actions_performed: false;
  suggestions_applied: false;
  requires_owner_review: true;
}


export interface BrowserHandoffReadiness {
  ready: boolean;
  blockers: string[];
  document_revision: number;
  contact_fields_ready: boolean;
  employer_submission_performed: false;
  will_require_manual_review: true;
  files_attached: false;
}

export interface BrowserHandoffPacket {
  schema: "smartploy.browser_handoff.v2";
  issued_at: string;
  expires_at: string;
  application_url: string;
  company: string;
  role_title: string;
  workspace_id: string;
  revision: number;
  document_sha256: string;
  cv_pdf_sha256: string;
  cv_pdf_size: number;
  /** Server-owned SHA fingerprint for the EXACT approved employer transfer. */
  approved_fields_sha256?: string;
  fields: {
    full_name: string;
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    location: string;
    linkedin: string;
    github: string;
    cover_letter: string;
  };
  privacy: {
    approved_contact_only: true;
    original_cv_included: false;
    browser_form_fill_allowed_after_user_click: true;
    employer_submit_allowed_without_new_approval: false;
  };
}


export interface BrowserObservedReceipt {
  workspace_id: string;
  document_revision: number;
  document_sha256: string;
  reference: string;
  confirmation_page_url: string;
  confirmation_page_sha256: string;
  observed_at: string;
  evidence_digest: string;
  status: "browser_observed_unverified";
  independently_verified_by_employer: false;
  actually_submitted_count_changed: false;
}

export interface BrowserReceiptImport {
  schema: "smartploy.browser_receipt.v1";
  workspace_id: string;
  document_revision: number;
  document_sha256: string;
  application_url: string;
  confirmation_page_url: string;
  reference: string;
  confirmation_page_sha256: string;
  observed_at: string;
  confirmed_visible: true;
}


export interface SearchPreferences {
  completed: boolean;
  mode: "personalized" | "general";
  roles: string[];
  locations: string[];
  languages: string[];
  work_modes: string[];
  keywords: string[];
  skills: string[];
  seniority: string;
  /** Must be explicitly enabled for per-account local automatic draft preparation. */
  auto_draft_enabled?: boolean;
  /** Independent opt-in to a case per background-matched application, OFF by default. */
  auto_agent_tracking_enabled?: boolean;
  auto_draft_external_actions_authorized?: false;
  auto_agent_external_actions_authorized?: false;
  revision: number;
  updated_at: string;
  verified_qualification_fit: false;
}

export type SearchPreferencesUpdate = Omit<SearchPreferences,
  "completed" | "revision" | "updated_at" | "verified_qualification_fit"> & {
    expected_revision: number;
  };

export interface SearchJobCard {
  canonical_key: string;
  job: JobCardData & { language?: string };
  preference_score: number | null;
  reasons: string[];
  unknown_fields: string[];
  mismatched_fields?: string[];
  lane: "recommended" | "broader" | "all";
}

export interface SearchResults {
  mode: "personalized" | "general" | "setup_required";
  completed: boolean;
  recommendations: SearchJobCard[];
  broader: SearchJobCard[];
  all_jobs: SearchJobCard[];
  available_count: number;
  score_kind: string;
  external_actions_authorized: false;
}

/** Provider destination links are not open vacancies and cannot be auto-applied. */
export interface TrainingProgram {
  id: string;
  provider: string;
  title: string;
  kind: "recruitment_training" | "academy" | "employer_trainee" | "internship_portal";
  region: string;
  url: string;
  focus: string[];
  eligibility_note: string;
  opening_status: "check_provider";
  listing_type: "directory_link";
  counts_as_live_job: false;
  automatic_application_authorized: false;
}

export interface TrainingProgramsResponse {
  programs: TrainingProgram[];
  count: number;
  opening_status: "check_provider";
  job_count_included: 0;
  external_actions_authorized: false;
}

/** Read-only owner-bound matches derived from stored CV text, not verified qualifications. */
export interface CVJobMatches {
  cv_present: boolean;
  cv_filename: string;
  match_mode: "upload_cv" | "cv_text_signals" | "no_recognized_cv_signals";
  detected_roles: string[];
  detected_topics: string[];
  recommended: SearchJobCard[];
  other_jobs: SearchJobCard[];
  current_jobs_count: number;
  recommended_count: number;
  /** Total matching exploratory rows, not just the current page. */
  other_jobs_count?: number;
  /** Exact current posting chosen from Search, even outside either page. */
  selected_job?: SearchJobCard | null;
  matched_from: "none" | "local_cv_text_not_approved_evidence";
  qualifications_verified: false;
  employer_actions_performed: false;
}

/** A fixed, non-sensitive diagnostic, not employer data or permission. */
export interface AutoApplyBatchIssue {
  canonicalKey: string;
  kind: "job_missing" | "review_required" | "service_busy" | "outcome_unknown" | "access_denied";
  guidance: string;
  retryable: boolean;
}

/** SP49/50: truthful per-job private draft outcomes, not employer receipts. */
export interface AutoApplyBatchOutcome {
  preparedKeys: string[];
  /** Exact private workspace IDs returned by owner-verified create-or-get; not employer receipts. */
  preparedWorkspaces?: Array<{ canonicalKey: string; workspaceId: string }>;
  failedKeys: string[];
  /** Only unstarted jobs; stop is honored between existing private requests. */
  skippedKeys?: string[];
  stopRequested?: boolean;
  /** An authorization failure halted the queue; reload after restoring access. */
  accessInterrupted?: boolean;
  issues?: AutoApplyBatchIssue[];
  agentsActive: number;
  agentsPaused: number;
  agentsClosed: number;
  agentsUnavailable: number;
}

/** A product experience mode, not employer-automation authorization. */
export type ApplicationFlowMode = "manual" | "assisted" | "automatic";
export type ApplicationAssistanceLevel = "filter" | "documents" | "full";
