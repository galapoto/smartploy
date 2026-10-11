export type EmployerSector = "public" | "private" | "unknown";

export interface JobCardData {
  company: string;
  role_title: string;
  location: string;
  work_mode: string;
  deadline: string;
  application_url: string;
  employer_sector: EmployerSector;
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
  profile: ProfileStatus;
  obumai_configured: boolean;
  worker: {
    configured: boolean;
    ready: boolean;
    count: number;
    error: string;
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
  status: "draft" | "self_reported_applied";
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
