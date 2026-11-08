// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getApplications, getCV, getDashboard, getHealth, getJobAIConsentEvents,
  getJobAIConsents, getJobs, getLocalAIStatus, getPrivateSavedJobs,
  getProfileFacts, getSearchPreferences, getSearchResults, getSession,
} from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("SP157: private bootstrap fetch cancellation", () => {
  it("forwards the one abort signal to every existing read-only bootstrap request", async () => {
    const seen: Array<{ path: string; signal?: AbortSignal }> = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      seen.push({ path: String(url), signal: init?.signal ?? undefined });
      return { ok: true, json: async () => ({}) };
    }));
    const controller = new AbortController();
    await Promise.all([
      getApplications(controller.signal), getCV(controller.signal),
      getDashboard(controller.signal), getHealth(controller.signal),
      getJobAIConsentEvents(controller.signal), getJobAIConsents(controller.signal),
      getJobs(controller.signal), getLocalAIStatus(controller.signal),
      getPrivateSavedJobs(controller.signal), getProfileFacts(controller.signal),
      getSearchPreferences(controller.signal), getSearchResults(controller.signal),
      getSession(controller.signal),
    ]);
    expect(seen).toHaveLength(13);
    expect(new Set(seen.map((call) => call.path)).size).toBe(13);
    expect(seen.every((call) => call.signal === controller.signal)).toBe(true);
  });

  it("rejects an aborted in-flight session fetch instead of occupying a browser connection", async () => {
    let stopped = false;
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        stopped = true;
        reject(new DOMException("Request aborted", "AbortError"));
      }, { once: true });
    })));
    const controller = new AbortController();
    const task = getSession(controller.signal);
    controller.abort();
    await expect(task).rejects.toMatchObject({ name: "AbortError" });
    expect(stopped).toBe(true);
  });
});
