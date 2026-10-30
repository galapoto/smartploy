import { describe, expect, it } from "vitest";
import { applicationNextStep, type NextApplicationInputs } from "./applicationNextStep";

const base = (): NextApplicationInputs => ({
  workspaceStatus: "draft",
  unsavedEdits: false,
  previousAttemptReserved: false,
  attemptStatusKnown: true,
  browserReceiptObserved: false,
  handoffReady: true,
  handoffBlockers: [],
  partnerRightsReviewed: false,
  partnerFinalEligible: false,
});

describe("SP71 exact-application next-action guidance", () => {
  it("only independently acknowledged employer status renders submitted", () => {
    const confirmed = applicationNextStep({
      ...base(), workspaceStatus: "provider_acknowledged",
      previousAttemptReserved: true, browserReceiptObserved: true,
      unsavedEdits: true,
    });
    expect(confirmed.kind).toBe("provider_confirmed");
    expect(confirmed.statusLabel).toContain("Provider acknowledged");
    expect(confirmed.action.target).toBe("#smartploy-outcome-step");
    expect(confirmed.detail).toContain("Do not submit it again");
    const reported = applicationNextStep({
      ...base(), workspaceStatus: "self_reported_applied",
      browserReceiptObserved: true,
    });
    expect(reported.kind).toBe("user_reported");
    expect(reported.statusLabel).toContain("not independently verified");
    expect(reported.detail).not.toMatch(/independently confirmed/i);
  });

  it("never turns reserved or browser-observed attempts into permission to retry", () => {
    const reserved = applicationNextStep({
      ...base(), previousAttemptReserved: true, partnerRightsReviewed: true,
      partnerFinalEligible: true,
    });
    expect(reserved.kind).toBe("reserved_attempt");
    expect(reserved.title).toContain("outcome needs review");
    expect(reserved.detail).toContain("Do not retry");
    expect(reserved.action.target).toBe("#smartploy-employer-step");
    const observed = applicationNextStep({
      ...base(), previousAttemptReserved: true, browserReceiptObserved: true,
      partnerFinalEligible: true,
    });
    expect(observed.kind).toBe("observed_confirmation");
    expect(observed.action.target).toBe("#smartploy-observed-evidence");
    expect(observed.detail).toContain("without submitting");
    const browserOnly = applicationNextStep({ ...base(), browserReceiptObserved: true });
    expect(browserOnly.kind).toBe("observed_confirmation");
    expect(browserOnly.title).toContain("not employer-verified");
  });

  it("asks the user to save unsaved edits before any employer handoff", () => {
    const action = applicationNextStep({
      ...base(), unsavedEdits: true, partnerFinalEligible: true,
      partnerRightsReviewed: true,
    });
    expect(action.kind).toBe("unsaved_edits");
    expect(action.action.type).toBe("save");
    expect(action.action.label).toBe("Save my edits");
    expect(action.statusLabel).toContain("not submitted");
  });

  it("fails closed if the private employer-attempt status read is missing", () => {
    const state = applicationNextStep({
      ...base(), attemptStatusKnown: false, partnerFinalEligible: true,
      partnerRightsReviewed: true,
    });
    expect(state.kind).toBe("attempt_checks_unavailable");
    expect(state.title).toContain("do not retry");
    expect(state.statusLabel).toContain("unverified");
    expect(state.action.type).toBe("jump");
  });

  it("uses the server blockers without claiming an application was sent", () => {
    const state = applicationNextStep({
      ...base(), handoffReady: false,
      handoffBlockers: ["Approved name is missing", "Current CV revision required", "Extra note"],
      partnerFinalEligible: true, partnerRightsReviewed: true,
    });
    expect(state.kind).toBe("requirements_blocked");
    expect(state.detail).toContain("Approved name is missing");
    expect(state.detail).toContain("Current CV revision required");
    expect(state.detail).not.toContain("Extra note");
    expect(state.action.target).toBe("#smartploy-employer-step");
    expect(state.statusLabel).toContain("draft only");
  });

  it("treats missing browser handoff evidence as unverified readiness", () => {
    const state = applicationNextStep({ ...base(), handoffReady: null });
    expect(state.kind).toBe("checks_unavailable");
    expect(state.action.target).toBe("#smartploy-cv-review");
    expect(state.statusLabel).not.toContain("Provider acknowledged");
  });

  it("requires separately reviewed rights for partner final guidance", () => {
    const eligible = applicationNextStep({
      ...base(), partnerRightsReviewed: true, partnerFinalEligible: true,
    });
    expect(eligible.kind).toBe("partner_final_review");
    expect(eligible.title).toContain("final approval required");
    expect(eligible.detail).toContain("Nothing has been sent");
    expect(eligible.action.type).toBe("jump");
    const unapproved = applicationNextStep({
      ...base(), partnerRightsReviewed: false, partnerFinalEligible: true,
    });
    expect(unapproved.kind).toBe("manual_handoff");
    expect(unapproved.title).toContain("complete the employer application");
  });

  it("tells the user to record review when partner rights exist but final eligibility does not", () => {
    const state = applicationNextStep({
      ...base(), partnerRightsReviewed: true, partnerFinalEligible: false,
    });
    expect(state.kind).toBe("partner_preparation");
    expect(state.detail).toContain("final transfer has not been approved");
  });

  it("distinguishes AutoApply drafts from applications sent to employers", () => {
    const state = applicationNextStep(base());
    expect(state.kind).toBe("manual_handoff");
    expect(state.detail).toContain("AutoApply drafting is not employer submission");
    expect(state.statusLabel).toBe("Prepared draft · not submitted");
  });
});
