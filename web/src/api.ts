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
  PreparationResponse,
  ApplicationWorkspace,
  ApplicationWorkspacesResponse
} from "./types";

const API_BASE = (import.meta.env.VITE_SMARTPLOY_API_BASE ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API_BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
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

export function prepareJob(canonicalKey: string): Promise<PreparationResponse> {
  return request<PreparationResponse>(
    "/api/v1/jobs/" + encodeURIComponent(canonicalKey) + "/prepare",
    { method: "POST" }
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

export async function uploadCV(file: File): Promise<CVDocument> {
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
  });
}

export function deleteCV(): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/api/v1/profile/cv", { method: "DELETE" });
}

export function createFact(fact_type: string, value: string, approved: boolean): Promise<{ fact: CandidateFact }> {
  return request<{ fact: CandidateFact }>("/api/v1/profile/facts", {
    method: "POST",
    body: JSON.stringify({ fact_type, value, approved })
  });
}

export function approveFact(fact_id: string, approved: boolean): Promise<{ fact: CandidateFact }> {
  return request<{ fact: CandidateFact }>("/api/v1/profile/facts/" + encodeURIComponent(fact_id), {
    method: "PATCH",
    body: JSON.stringify({ approved })
  });
}

export function deleteFact(fact_id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/api/v1/profile/facts/" + encodeURIComponent(fact_id), {
    method: "DELETE"
  });
}

export function addManualJob(job: ManualJobPayload): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/jobs/ingest", {
    method: "POST",
    body: JSON.stringify({
      observation: {
        source_id: "manual-import",
        source_mode: "manual",
        source_url: job.application_url,
        raw_text: job.role_title + " " + job.company + " " + job.description,
        observed_at: new Date().toISOString(),
        payload: job
      }
    })
  });
}


export function startApplicationWorkspace(canonicalKey: string): Promise<{ workspace: ApplicationWorkspace; created: boolean }> {
  return request<{ workspace: ApplicationWorkspace; created: boolean }>(
    "/api/v1/jobs/" + encodeURIComponent(canonicalKey) + "/application-workspace",
    { method: "POST" }
  );
}

export function getApplicationWorkspaces(): Promise<ApplicationWorkspacesResponse> {
  return request<ApplicationWorkspacesResponse>("/api/v1/application-workspaces");
}

export function editApplicationWorkspace(
  workspaceId: string, expectedRevision: number, cvText: string, coverLetterText: string
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
    }
  );
}

export function markApplicationManuallySent(
  workspaceId: string, expectedRevision: number, reference: string
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
    }
  );
}

export function deleteApplicationWorkspace(workspaceId: string): Promise<{ deleted: true }> {
  return request<{ deleted: true }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId),
    { method: "DELETE" }
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
  workspaceId: string, expectedRevision: number
): Promise<{ suggestion: import("./types").LocalAISuggestion; workspace_revision: number }> {
  return request<{ suggestion: import("./types").LocalAISuggestion; workspace_revision: number }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/ai-suggestions",
    { method: "POST", body: JSON.stringify({
      expected_revision: expectedRevision,
      acknowledge_local_ai_processing: true
    }) }
  );
}


export function getBrowserHandoffReadiness(workspaceId: string): Promise<import("./types").BrowserHandoffReadiness> {
  return request<import("./types").BrowserHandoffReadiness>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/handoff-readiness"
  );
}

export function createBrowserHandoffPacket(
  workspaceId: string, revision: number
): Promise<{ packet: import("./types").BrowserHandoffPacket; external_actions_performed: false }> {
  return request<{ packet: import("./types").BrowserHandoffPacket; external_actions_performed: false }>(
    "/api/v1/application-workspaces/" + encodeURIComponent(workspaceId) + "/browser-packet",
    { method: "POST", body: JSON.stringify({
      expected_revision: revision,
      confirm_private_data_transfer: true
    }) }
  );
}
