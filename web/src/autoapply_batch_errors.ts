/** SP50: fixed applicant-safe labels for failures of PRIVATE draft creation.
 *
 * A server may commit an idempotent workspace before a 5xx/network failure.
 * No class here is permission to repeat a provider/employer submission.
 * Never put raw response details, account identifiers, job URLs or candidate
 * data into a batch diagnostic.
 */
import { SmartployHttpError } from "./api";
import type { AutoApplyBatchIssue } from "./types";

export function describeAutoApplyBatchIssue(
  canonicalKey: string, failure: unknown,
): AutoApplyBatchIssue {
  const status = failure instanceof SmartployHttpError ? failure.status : 0;
  if (status === 404 || status === 410) {
    return {
      canonicalKey, kind: "job_missing", retryable: false,
      guidance: "This posting could not be found. Refresh job search and choose a current vacancy.",
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
