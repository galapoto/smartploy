// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AIConsentSettings from "./AIConsentSettings";
import type { JobAIProcessingConsent, SavedJob } from "./types";

const allowedJob = {
  canonical_key: "synthetic-job-key", source_current: true,
  job: {
    role_title: "Junior Developer", company: "Example Oy",
    ai_preparation_allowed: true
  }
} as SavedJob;

const permission = {
  consent_id: "consent-fixture", canonical_key: "synthetic-job-key",
  processor: "obumai", purpose: "application_draft", mode: "unattended",
  job_snapshot_sha256: "a".repeat(64), evidence_sha256: "b".repeat(64),
  revision: 1, granted_at: "2026-10-17T10:00:00+00:00",
  revoked_at: "", active: true, processing_started: false,
  employer_actions_authorized: false
} as JobAIProcessingConsent;

afterEach(cleanup);

it("requires a checked, explicit job-specific permission before invoking any mutation", async () => {
  const grant = vi.fn(async (_jobKey: string) => undefined);
  render(<AIConsentSettings jobs={[allowedJob]} consents={[]} events={[]}
    status="ready" busy={false} onGrant={grant} onRevoke={vi.fn()} />);
  const button = screen.getByRole("button", { name: /save job-specific permission/i });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  const select = screen.getByLabelText(/choose a currently approved job/i);
  fireEvent.change(select, { target: { value: "synthetic-job-key" } });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: /i explicitly allow obumai/i }));
  expect((button as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() => expect(grant).toHaveBeenCalledExactlyOnceWith("synthetic-job-key"));
  expect((button as HTMLButtonElement).disabled).toBe(true);
});

it("does not offer a grant for source-restricted jobs and handles outages fail-closed", () => {
  const grant = vi.fn(async (_jobKey: string) => undefined);
  const blocked = { ...allowedJob, job: { ...allowedJob.job, ai_preparation_allowed: false } };
  const { rerender } = render(<AIConsentSettings jobs={[blocked]} consents={[]}
    events={[]} status="ready" busy={false} onGrant={grant} onRevoke={vi.fn()} />);
  expect(screen.queryByRole("option", { name: /Junior Developer/i })).toBeNull();
  expect((screen.getByRole("button", { name: /save job-specific permission/i })
    as HTMLButtonElement).disabled).toBe(true);
  rerender(<AIConsentSettings jobs={[allowedJob]} consents={[permission]}
    events={[]} status="unavailable" busy={false}
    onGrant={grant} onRevoke={vi.fn()} />);
  expect(screen.getByRole("status").textContent).toMatch(/will not assume consent/i);
  expect(screen.queryByRole("button", { name: /save job-specific permission/i })).toBeNull();
  expect(grant).not.toHaveBeenCalled();
});

it("offers consent withdrawal independently of any employer or AI action", async () => {
  const revoke = vi.fn(async (_id: string) => undefined);
  render(<AIConsentSettings jobs={[allowedJob]} consents={[permission]} events={[]}
    status="ready" busy={false} onGrant={vi.fn()} onRevoke={revoke} />);
  fireEvent.click(screen.getByRole("button", { name: /withdraw permission/i }));
  await waitFor(() => expect(revoke).toHaveBeenCalledExactlyOnceWith("consent-fixture"));
});
