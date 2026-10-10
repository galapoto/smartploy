import type {
  ApplicationsResponse,
  Dashboard,
  HealthResponse,
  PreparationResponse
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
