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

export interface Dashboard {
  top_matches: RankingCard[];
  possible_matches: RankingCard[];
  preparation_counts: Record<string, number>;
  applications: ApplicationSummary;
  source_health: SourceHealth[];
  profile: ProfileStatus;
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
  external_actions_authorized: boolean;
}

export interface PreparationResponse {
  package_id: string;
  canonical_key: string;
  status: string;
  error?: string;
  updated_at?: string;
}
