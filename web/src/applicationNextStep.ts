import type { ApplicationWorkspace } from "./types";

/**
 * Read-only presentation guidance for one owner-scoped exact application.
 *
 * It is not a grant, reviewer decision, employer attempt, claim or receipt.
 * All actual actions still go through the existing authenticated server
 * checks. Most importantly, "browser handoff ready" never means "sent".
 */
export type NextApplicationStep = {
  kind: "provider_confirmed" | "user_reported" | "observed_confirmation" |
    "reserved_attempt" | "unsaved_edits" | "requirements_blocked" |
    "checks_unavailable" | "partner_final_review" | "partner_preparation" |
    "manual_handoff";
  title: string;
  detail: string;
  statusLabel: string;
  tone: "confirmed" | "attention" | "neutral";
  action: {
    label: string;
    type: "jump" | "save";
    target?: "#smartploy-cv-review" | "#smartploy-employer-step" |
      "#smartploy-observed-evidence" | "#smartploy-outcome-step";
  };
};

export type NextApplicationInputs = {
  workspaceStatus: ApplicationWorkspace["status"];
  unsavedEdits: boolean;
  previousAttemptReserved: boolean;
  browserReceiptObserved: boolean;
  /** null includes pending/failed policy reads; never treat as authorized. */
  handoffReady: boolean | null;
  handoffBlockers: readonly string[];
  partnerRightsReviewed: boolean;
  partnerFinalEligible: boolean;
};

export function applicationNextStep(input: NextApplicationInputs): NextApplicationStep {
  // Durable employer acknowledgment is the sole independently verified
  // submission outcome. Self-report and browser observation are not.
  if (input.workspaceStatus === "provider_acknowledged") {
    return {
      kind: "provider_confirmed",
      title: "Employer system acknowledged your application",
      detail: "A provider acknowledgment was recorded for this exact application. Do not submit it again. This is not a hiring decision.",
      statusLabel: "Provider acknowledged · submitted",
      tone: "confirmed",
      action: { type: "jump", label: "Review employer confirmation", target: "#smartploy-outcome-step" },
    };
  }
  if (input.workspaceStatus === "self_reported_applied") {
    return {
      kind: "user_reported",
      title: "You reported applying — employer verification is pending",
      detail: "SmartPloy has recorded your own report, not an independent employer acknowledgment. Keep any confirmation email; do not treat this as ATS-verified.",
      statusLabel: "Self-reported · not independently verified",
      tone: "attention",
      action: { type: "jump", label: "Review recorded outcome", target: "#smartploy-outcome-step" },
    };
  }
  // A reserved final attempt is a one-use anti-duplicate guard, even when
  // browser evidence exists. Never suggest another sender action here.
  if (input.previousAttemptReserved) {
    if (input.browserReceiptObserved) {
      return {
        kind: "observed_confirmation",
        title: "Employer confirmation observed — verification still pending",
        detail: "An employer attempt is already reserved and a browser-observed confirmation exists. Review its evidence; reconcile without submitting the job again.",
        statusLabel: "Browser-observed · no independent provider receipt",
        tone: "attention",
        action: { type: "jump", label: "Review observed confirmation", target: "#smartploy-observed-evidence" },
      };
    }
    return {
      kind: "reserved_attempt",
      title: "Previous employer attempt — outcome needs review",
      detail: "An employer attempt is reserved for this job. Do not retry. Check the employer page and your email, then import a matching confirmation if available.",
      statusLabel: "Attempt reserved · not confirmed",
      tone: "attention",
      action: { type: "jump", label: "Resolve the reserved attempt", target: "#smartploy-employer-step" },
    };
  }
  if (input.browserReceiptObserved) {
    return {
      kind: "observed_confirmation",
      title: "Browser confirmation recorded — not employer-verified",
      detail: "The browser observed a reference for this application. This does not independently confirm the employer received it; review and reconcile the outcome.",
      statusLabel: "Browser-observed · no independent provider receipt",
      tone: "attention",
      action: { type: "jump", label: "Review observed confirmation", target: "#smartploy-observed-evidence" },
    };
  }
  if (input.unsavedEdits) {
    return {
      kind: "unsaved_edits",
      title: "Save your changes before continuing",
      detail: "Your CV or cover letter differs from the private saved revision. Save the changes and review the exact job before using a browser packet or employer form.",
      statusLabel: "Unsaved draft · not submitted",
      tone: "attention",
      action: { type: "save", label: "Save my edits" },
    };
  }
  if (input.handoffReady === false) {
    const first = input.handoffBlockers.filter(Boolean).slice(0, 2);
    return {
      kind: "requirements_blocked",
      title: "Complete the missing application requirements",
      detail: first.length
        ? "SmartPloy cannot prepare the browser handoff yet: " + first.join("; ") + ". No employer submission has occurred."
        : "SmartPloy cannot prepare the browser handoff yet. Check the listed prerequisites below. No employer submission has occurred.",
      statusLabel: "Action required · draft only",
      tone: "attention",
      action: { type: "jump", label: "See missing requirements", target: "#smartploy-employer-step" },
    };
  }
  if (input.handoffReady !== true) {
    return {
      kind: "checks_unavailable",
      title: "Review the draft — submission checks unavailable",
      detail: "SmartPloy could not verify browser handoff readiness for this revision. Your documents are private; no employer submission has been confirmed. Refresh when ready.",
      statusLabel: "Readiness unverified · draft only",
      tone: "attention",
      action: { type: "jump", label: "Review the CV first", target: "#smartploy-cv-review" },
    };
  }
  if (input.partnerFinalEligible && input.partnerRightsReviewed) {
    return {
      kind: "partner_final_review",
      title: "Reviewed employer route available — final approval required",
      detail: "This exact job may use the separately authorized employer integration. Nothing has been sent yet. Inspect the reviewed details and make a separate final decision; the server will recheck permission.",
      statusLabel: "Eligible for reviewed final action · not submitted",
      tone: "neutral",
      action: { type: "jump", label: "Review authorized employer action", target: "#smartploy-employer-step" },
    };
  }
  if (input.partnerRightsReviewed) {
    return {
      kind: "partner_preparation",
      title: "Prepare your final employer review",
      detail: "An employer partner route is configured for this job, but the final transfer has not been approved. Review your documents, the job and the current eligibility checks.",
      statusLabel: "Review required · not submitted",
      tone: "neutral",
      action: { type: "jump", label: "Review partner handoff", target: "#smartploy-employer-step" },
    };
  }
  return {
    kind: "manual_handoff",
    title: "Draft prepared — complete the employer application",
    detail: "Your private CV and letter are prepared. Use the original employer form or supported browser assistance after review. AutoApply drafting is not employer submission.",
    statusLabel: "Prepared draft · not submitted",
    tone: "neutral",
    action: { type: "jump", label: "See employer application options", target: "#smartploy-employer-step" },
  };
}
