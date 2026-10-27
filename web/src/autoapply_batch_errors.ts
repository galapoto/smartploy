/** SP50: fixed applicant-safe labels for failures of PRIVATE draft creation.
 *
 * A server may commit an idempotent workspace before a 5xx/network failure.
 * No class here is permission to repeat a provider/employer submission.
 * Never put raw response details, account identifiers, job URLs or candidate
 * data into a batch diagnostic.
 */
import type { AutoApplyBatchIssue } from "./types";

export function describeAutoApplyBatchIssue(
  canonicalKey: string, failure: unknown,
): AutoApplyBatchIssue {
  // Only the typed SmartployHttpError from api.ts is expected in the app.
  // Structural status lookup also keeps isolated React tests independent of
  // the mocked API module. Invalid or synthetic values fall back to unknown.
  const reported = failure && typeof failure === "object" && "status" in failure
    ? (failure as { status?: unknown }).status : null;
  const status = typeof reported === "number" && Number.isInteger(reported) &&
    reported >= 400 && reported <= 599 ? reported : 0;
  if (status === 404 || status === 410) {
    return {
      canonicalKey, kind: "job_missing", retryable: false,
      guidance: "This posting could not be found. Refresh job search and choose a current vacancy.",
    };
  }
  if (status === 401 || status === 403) {
    return {
      canonicalKey, kind: "access_denied", retryable: false,
      guidance: "Private preparation access is unavailable. Verify your sign-in and permissions before preparing further jobs.",
    };
  }
  if ((status >= 400 && status < 500) && status !== 408 && status !== 429) {
    return {
      canonicalKey, kind: "review_required", retryable: false,
      guidance: "The job, CV or approved profile needs review. Refresh and correct it before selecting this job again.",
    };
  }
  if (status === 408 || status === 429 || status === 502 || status === 503 || status === 504) {
    return {
      canonicalKey, kind: "service_busy", retryable: true,
      guidance: "The private preparation service is temporarily unavailable. Check My applications, then retry this job when ready.",
    };
  }
  return {
    canonicalKey, kind: "outcome_unknown", retryable: true,
    guidance: "The result could not be confirmed. Check My applications for an existing draft before deliberately retrying this job.",
  };
}
