/** SP111: SmartPloy-to-local-Playwright review flow.
 * No hidden browser operation: applicant starts one local helper per job,
 * enters a one-use pairing code, sees the planned fields and approves once.
 * Same-account/session reverified before and after private bridge actions.
 */
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Monitor, ShieldCheck, XCircle } from "lucide-react";
import { applicationDownloadUrl, getBrowserHandoffReadiness,
  getEmployerAttemptStatus, getSession, importBrowserReceipt,
  getApplicationQuestionMemory, rememberApplicationQuestions,
  saveApplicationQuestionAnswer } from "./api";
import type { BrowserReceiptImport, BrowserObservedReceipt,
  ApplicationProfileQuestion, ApplicationProfileMode } from "./types";
import {
  attachExactReviewedCvLocally, fetchExactReviewedCvPdf,
  callLocalPlaywrightBridge, localBridgeOriginAllowed,
  type LocalBridgeOpened, type LocalBridgeInspected,
  type LocalBridgeFilled, type LocalQuestionsInspected,
  type LocalAnswersFilled, type LocalReviewedQuestion, type LocalBridgeObserved,
  type LocalBridgeStopped, type LocalBridgeField,
} from "./localPlaywrightBridge";
import "./local-playwright.css";

type Phase = "not-paired" | "opened" | "inspected" | "filled" | "uncertain" | "stopped";
const CODE = /^[A-Za-z0-9_-]{20,80}$/;
const SESSION_CHANGED = "Your SmartPloy sign-in changed. The local connection is blocked; restart and review again.";

export default function LocalPlaywrightAssist(props: {
  packetText: string;
  enabled: boolean;
  expectedUserId: string;
  expectedAuthSource: string;
  expectedWorkspaceId: string;
  expectedRevision: number;
  observationEnabled?: boolean;
  onReceiptImported?: (receipt: BrowserObservedReceipt) => void;
  autoInspectOnPair?: boolean;
  /** Only explicit applicant consent can arm one-time ordinary-field filling. */
  autoFillOnPair?: boolean;
}) {
  const [code, setCode] = useState("");
  const [autoFillAfterInspect, setAutoFillAfterInspect] = useState(
    props.autoFillOnPair === true
  );
  const [phase, setPhase] = useState<Phase>("not-paired");
  const [fields, setFields] = useState<LocalBridgeField[]>([]);
  const [planId, setPlanId] = useState("");
  const [cvAttachment, setCvAttachment] = useState<{
    available: boolean; label: string; attach_id: string;
  }>({ available: false, label: "", attach_id: "" });
  const [cvAttached, setCvAttached] = useState(false);
  const [cvAttachAttempted, setCvAttachAttempted] = useState(false);
  const [cvAttachBusy, setCvAttachBusy] = useState(false);
  const [reviewedQuestions, setReviewedQuestions] = useState<LocalReviewedQuestion[]>([]);
  const [humanOnlyQuestions, setHumanOnlyQuestions] = useState<string[]>([]);
  const [questionAnswers, setQuestionAnswers] = useState<string[]>([]);
  const [questionPlanId, setQuestionPlanId] = useState("");
  const [questionAttempted, setQuestionAttempted] = useState(false);
  const [questionInspectionDone, setQuestionInspectionDone] = useState(false);
  const [questionStatus, setQuestionStatus] = useState("");
  const [questionMemory, setQuestionMemory] = useState<Record<string, ApplicationProfileQuestion>>({});
  const [questionProfileMode, setQuestionProfileMode] = useState<ApplicationProfileMode>("guided");
  const [questionMemoryAvailable, setQuestionMemoryAvailable] = useState(false);
  const [rememberMyAnswers, setRememberMyAnswers] = useState(true);

  const [observedReceipt, setObservedReceipt] = useState<BrowserReceiptImport | null>(null);
  const [receiptSaveClaimed, setReceiptSaveClaimed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const sessionToken = useRef("");
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      // A changed account or job must never expose the old token in new UI.
      // The local helper remains safe (its bearer token is no longer in UI
      // memory) and can be stopped with Ctrl+C in the applicant terminal.
      mounted.current = false;
      sessionToken.current = "";
    };
  }, []);

  async function verifyAccount() {
    const session = await getSession();
    if (session.authenticated !== true ||
        session.user_id !== props.expectedUserId ||
        session.auth_source !== props.expectedAuthSource) {
      sessionToken.current = "";
      throw new Error(SESSION_CHANGED);
    }
  }

  async function verifyCurrentDraft() {
    // Existing owner-scoped backend readiness must recheck source/job and
    // document revision immediately before each local browser action.
    // The helper's 15-minute packet is NOT enough to detect another tab edit.
    // A held/uncertain employer attempt must not lead to a second CV
    // transmission from a stale browser tab; reuse the server's original
    // one-use attempt ledger, not a UI-derived submission status.
    const attempt = await getEmployerAttemptStatus(props.expectedWorkspaceId);
    if (attempt.previous_attempt_reserved !== false) {
      throw new Error("An employer application attempt is already reserved or uncertain. " +
        "Review its receipt before any new local browser action.");
    }
    const readiness = await getBrowserHandoffReadiness(props.expectedWorkspaceId);
    if (readiness.ready !== true ||
        readiness.document_revision !== props.expectedRevision) {
      throw new Error("This job or reviewed CV/letter changed. Stop the local browser, " +
        "save and prepare a fresh application packet.");
    }
  }

  async function verifyReceiptDraftIdentity() {
    // Browser receipt IMPORT is allowed after an employer attempt has been
    // reserved. A reserved ledger prevents another send, not a read-only
    // observation of that same exact application. This checks REVISION only.
    const readiness = await getBrowserHandoffReadiness(props.expectedWorkspaceId);
    if (readiness.document_revision !== props.expectedRevision) {
      throw new Error("The saved CV/letter revision changed. A confirmation for " +
        "the old job cannot be imported into this application.");
    }
  }

  async function guardedReceipt(action: () => Promise<void>) {
    if (!mounted.current || inFlight.current ||
        props.observationEnabled === false || !sessionToken.current) return;
    inFlight.current = true;
    setBusy(true); setError(""); setFeedback("");
    try {
      await verifyAccount();
      await verifyReceiptDraftIdentity();
      await verifyAccount();
      if (!mounted.current) return;
      await action();
      await verifyAccount();
    } catch (exc) {
      if (mounted.current) setError(
        exc instanceof Error ? exc.message : "Receipt observation was blocked."
      );
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  async function guarded(action: () => Promise<void>) {
    if (!props.enabled || !mounted.current || inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(""); setFeedback("");
    try {
      await verifyAccount();
      if (!mounted.current) return;
      await verifyCurrentDraft();
      await verifyAccount();
      if (!mounted.current) return;
      await action();
      await verifyAccount();
    } catch (exc) {
      if (!mounted.current) return;
      const message = exc instanceof Error ? exc.message : "The local browser action was blocked.";
      setError(message);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  /** A single applicant-approved fill after a fresh, exact-job inspection.
   * Never retries a browser write, uploads a CV or submits the application.
   */
  async function fillAfterApprovedInspection(inspected: LocalBridgeInspected, token: string) {
    if (!inspected.approved_fields.length || !inspected.plan_id ||
        !token || sessionToken.current !== token) return;
    // The window may have been edited or its OIDC identity changed while
    // Chromium opened and inspected the real employer page. Revalidate NOW.
    await verifyCurrentDraft();
    await verifyAccount();
    if (!mounted.current || sessionToken.current !== token) return;
    // A timeout or browser crash AFTER this point is an uncertain write.
    // Never expose an automatic retry action, even for partial fills.
    setPhase("uncertain");
    const result = await callLocalPlaywrightBridge<LocalBridgeFilled>(
      "fill", {plan_id: inspected.plan_id, confirmation: "FILL REVIEWED FIELDS"},
      {token, expectedStage: "filled"},
    );
    await verifyAccount();
    if (!mounted.current || sessionToken.current !== token) return;
    setPhase("filled");
    setFeedback("Visible AutoApply filled " + result.filled + " of " +
      result.planned + " reviewed ordinary employer fields once. " +
      (result.stopped_on_change
        ? "The employer form changed; complete the remaining fields yourself. "
        : "") +
      "Review the visible employer form, approve CV attachment separately, " +
      "and click the employer Submit button yourself. No application was submitted.");
  }

  function startLocalBrowser() {
    if (phase !== "not-paired" || !CODE.test(code.trim()) || !props.packetText) return;
    const fillAfterPair = props.autoInspectOnPair === true &&
      props.autoFillOnPair === true && autoFillAfterInspect;
    if (!window.confirm(fillAfterPair
      ? "Start visible AutoApply for this exact saved employer job? The local " +
        "Chromium helper will open the page, inspect its fields and fill ONLY " +
        "approved ordinary contact/letter fields ONCE when the job form is " +
        "ready. Some employer websites transmit data on each input. " +
        "This does NOT attach the CV or click Submit. You must review every " +
        "value and personally submit. Continue?"
      : "Send the currently reviewed SmartPloy packet (approved contact details " +
        "and cover letter) ONLY to the helper on this computer at 127.0.0.1? " +
        "The helper opens the exact employer posting in visible Chromium. " +
        "The employer website may receive data during form filling, but this step " +
        "does not fill fields, upload a CV or submit an application."
    )) return;
    void guarded(async () => {
      let packet: unknown;
      try { packet = JSON.parse(props.packetText); }
      catch { throw new Error("The reviewed application packet is invalid. Copy a fresh one."); }
      if (!packet || typeof packet !== "object" ||
          (packet as { workspace_id?: unknown }).workspace_id !== props.expectedWorkspaceId ||
          (packet as { revision?: unknown }).revision !== props.expectedRevision) {
        throw new Error("The reviewed packet does not match this exact current job. Copy a fresh one.");
      }
      const response = await callLocalPlaywrightBridge<LocalBridgeOpened>(
        "prepare", { pairing_code: code.trim(), packet }, { expectedStage: "opened" },
      );
      // Do not leave an old applicant's browser session reusable after an
      // in-flight OIDC switch; best-effort cleanup is LOCAL only.
      try { await verifyAccount(); } catch (exc) {
        try {
          await callLocalPlaywrightBridge<LocalBridgeStopped>(
            "stop", {}, { token: response.token, expectedStage: "stopped" }
          );
        } catch { /* helper can always be shut down from terminal */ }
        throw exc;
      }
      if (!mounted.current) return;
      sessionToken.current = response.token; // memory only: no storage/log/URL
      setCode("");
      setPhase("opened");
      setFeedback("Visible Chromium opened for " + response.company +
        " — " + response.role_title + ". Checking whether the reviewed job form is ready…");
      if (!props.autoInspectOnPair) {
        setFeedback("Local Chromium opened for " + response.company +
          " — " + response.role_title + ". Navigate to the employer form and inspect it.");
        return;
      }
      // The one-time pairing click can automatically perform READ-ONLY
      // inspection after opening Chromium. Never automatically fill values,
      // attach a file or click employer Submit. If login/ATS navigation is
      // needed, the applicant can complete it visibly and inspect again.
      let inspected: LocalBridgeInspected | null = null;
      try {
        inspected = await callLocalPlaywrightBridge<LocalBridgeInspected>(
          "inspect", {}, { token: response.token, expectedStage: "inspected" },
        );
      } catch {
        // A nonstandard landing page is a normal handoff; login and navigation
        // remain in the visible browser. This never retries a fill.
      }
      // IMPORTANT: Account verification must run outside the inspection
      // catch, so an OIDC switch is never treated as an innocuous form error.
      try { await verifyAccount(); } catch (exc) {
        try {
          await callLocalPlaywrightBridge<LocalBridgeStopped>(
            "stop", {}, { token: response.token, expectedStage: "stopped" },
          );
        } catch { /* local helper can always be stopped from the terminal */ }
        sessionToken.current = "";
        throw exc;
      }
      if (!mounted.current) return;
      if (inspected) {
        setFields(inspected.approved_fields);
        setPlanId(inspected.plan_id);
        setCvAttachment(inspected.cv_attachment);
        setCvAttached(false); setCvAttachAttempted(false);
        setPhase("inspected");
        if (fillAfterPair && inspected.approved_fields.length) {
          await fillAfterApprovedInspection(inspected, response.token);
          return;
        }
        setFeedback(inspected.approved_fields.length
          ? "Employer form ready. Review the " + inspected.approved_fields.length +
            " detected ordinary field(s), then click Fill to watch Chromium complete them. " +
            "Nothing has been sent or submitted by this inspection."
          : "Form opened, but no safe ordinary fields were detected. Complete the " +
            "employer form personally or inspect after navigating to its application page.");
      } else {
        setPhase("opened");
        setFeedback("Chromium is open. Complete the employer login or click Apply " +
          "on the visible employer website, then inspect the exact form here. " +
          "No information was filled or submitted.");
      }
    });
  }

  function inspectLocalBrowser() {
    // Many employers show only a job detail page first. After the applicant
    // clicks Apply/signs in, they must be able to inspect the newly visible
    // form without restarting the helper or silently reusing the old plan.
    // Re-inspection is read-only; never permit it after any write or upload.
    if (!["opened", "inspected"].includes(phase) || !sessionToken.current ||
        busy || inFlight.current || questionAttempted || cvAttachAttempted) return;
    const autoFillAfterReinspect = props.autoInspectOnPair === true &&
      props.autoFillOnPair === true && autoFillAfterInspect;
    if (autoFillAfterReinspect && !window.confirm(
      "Reinspect the visible employer form and fill reviewed ordinary fields " +
      "ONCE if a safe match is found? Inputs may immediately transmit to the " +
      "employer. No CV upload or final Submit will occur."
    )) return;
    if (questionAnswers.some(answer => answer.trim()) &&
        !window.confirm("Reinspect the employer form? Unsaved question answers " +
          "in this SmartPloy panel will be cleared. Nothing will be submitted.")) return;
    // The local bridge invalidates the previous inspection token BEFORE it
    // inspects. Invalidate the matching UI state before network I/O as well,
    // including when the new inspection fails or times out.
    setPhase("opened");
    setFields([]);
    setPlanId("");
    setCvAttachment({available: false, label: "", attach_id: ""});
    setReviewedQuestions([]);
    setHumanOnlyQuestions([]);
    setQuestionAnswers([]);
    setQuestionPlanId("");
    setQuestionInspectionDone(false);
    setQuestionStatus("");
    setQuestionMemory({});
    setQuestionMemoryAvailable(false);
    void guarded(async () => {
      const response = await callLocalPlaywrightBridge<LocalBridgeInspected>(
        "inspect", {}, { token: sessionToken.current, expectedStage: "inspected" },
      );
      if (!mounted.current) return;
      setFields(response.approved_fields);
      setPlanId(response.plan_id);
      setCvAttachment(response.cv_attachment);
      setCvAttached(false); setCvAttachAttempted(false);
      setPhase("inspected");
      if (autoFillAfterReinspect && response.approved_fields.length) {
        await fillAfterApprovedInspection(response, sessionToken.current);
        return;
      }
      setFeedback(response.approved_fields.length
        ? "Detected " + response.approved_fields.length +
          " safe field(s) on the current form. Check them, then click Fill once. " +
          "The employer has not received a submission."
        : "No ordinary empty fields were found. If you are on a job posting, " +
          "click Apply or sign in inside Chromium and choose Inspect again. " +
          "Sensitive and nonstandard fields remain manual.");
    });
  }

  function fillLocalBrowser() {
    if (phase !== "inspected" || !sessionToken.current ||
        !planId || !fields.length || !props.enabled || inFlight.current) return;
    if (!window.confirm(
      "Fill these " + fields.length + " reviewed, ordinary fields ONCE in the " +
      "visible employer form? The employer page may transmit each value " +
      "immediately. A separate reviewed CV attachment action is optional; " +
      "SmartPloy will never click Submit. " +
      "A changed form or uncertain outcome stops without retry."
    )) return;
    // Even after a network timeout the local helper may have filled some
    // values. Disable local retry before issuing the request.
    setPhase("uncertain");
    void guarded(async () => {
      const response = await callLocalPlaywrightBridge<LocalBridgeFilled>(
        "fill", { plan_id: planId, confirmation: "FILL REVIEWED FIELDS" },
        { token: sessionToken.current, expectedStage: "filled" },
      );
      if (!mounted.current) return;
      setPhase("filled");
      setFeedback("Filled " + response.filled + " of " + response.planned +
        " reviewed fields. " + (response.stopped_on_change
          ? "The form changed; finish remaining fields manually. "
          : "") +
        "Review every value, attach documents and submit personally on the employer website.");
    });
  }

  function reviewEmployerQuestions() {
    if (!props.enabled || inFlight.current || !sessionToken.current ||
        questionAttempted || !["opened", "inspected", "filled"].includes(phase)) return;
    void guarded(async () => {
      const result = await callLocalPlaywrightBridge<LocalQuestionsInspected>(
        "questions", {}, {
          token: sessionToken.current, expectedStage: "questions_inspected",
        },
      );
      if (!mounted.current) return;
      // Lane C: reuse the private profile API; a newly discovered ordinary
      // question becomes a permanent MISSING profile prompt immediately.
      // An approved answer may be suggested, but is never filled without
      // this applicant's new, job-specific explicit confirmation.
      // Native selects are employer-specific option sets, not reusable profile
      // answers. Preserve the existing private text-question memory only.
      const reusableQuestions = result.questions.filter(q =>
        q.type !== "select" && q.type !== "radio_group");
      let saved: ApplicationProfileQuestion[] = [];
      let mode: ApplicationProfileMode = "guided";
      let memoryAvailable = false;
      try {
        await verifyAccount();
        const memory = await getApplicationQuestionMemory();
        await verifyAccount();
        mode = memory.mode;
        if (mode === "guided" && reusableQuestions.length) {
          const registered = await rememberApplicationQuestions(
            props.expectedWorkspaceId, props.expectedRevision,
            reusableQuestions.map(q => ({
              label: q.label, expected_id: q.expected_id,
              expected_name: q.expected_name,
              expected_placeholder: q.expected_placeholder,
            })), props.expectedUserId,
          );
          await verifyAccount();
          if (registered.profile_mode !== "cv_only") {
            saved = registered.questions;
            memoryAvailable = true;
          } else {
            mode = "cv_only";
          }
        } else {
          memoryAvailable = false;
        }
      } catch {
        // A failed profile read/write is never evidence of a remembered
        // question. The original local browser form remains manually usable.
        memoryAvailable = false;
      }
      if (!mounted.current) return;
      setReviewedQuestions(result.questions);
      setHumanOnlyQuestions(result.human_only);
      const byLabel = Object.fromEntries(saved.map(item => [item.label, item]));
      setQuestionMemory(byLabel);
      setQuestionProfileMode(mode);
      setQuestionMemoryAvailable(memoryAvailable);
      setRememberMyAnswers(mode === "guided" && memoryAvailable &&
        reusableQuestions.length > 0);
      setQuestionAnswers(result.questions.map(q => {
        if (q.type === "select" || q.type === "radio_group") return ""; // fresh per-employer choice
        const previous = byLabel[q.label];
        // Exact-label, explicit owner-reviewed reusable answers only.
        return previous?.approved_for_reuse && previous.reusable_scope === "exact_question"
          ? previous.answer.slice(0, q.max_answer_length) : "";
      }));
      setQuestionPlanId(result.plan_id);
      setQuestionInspectionDone(true);
      setQuestionStatus(result.questions.length
        ? (mode === "cv_only"
          ? "CV-only mode: no question is saved to your profile. You can fill reviewed fields once; remaining questions stay manual."
          : !reusableQuestions.length
            ? "Reviewed employer options are available now. Select exact choices for this application; radio and dropdown answers are not saved as reusable profile facts."
            : memoryAvailable
              ? "Safe text questions are saved as missing profile prompts. Reviewed past answers are suggestions only; check them again for this employer."
              : "Text-question profile memory was unavailable: new prompts were not saved. You may still review this employer form and fill the approved fields.")
        : "No safe unanswered questions. Complete remaining questions " +
          "personally in the employer browser.");
    });
  }

  function fillReviewedEmployerAnswers() {
    if (!props.enabled || !sessionToken.current || inFlight.current ||
        !questionInspectionDone || !questionPlanId || questionAttempted ||
        !["opened", "inspected", "filled"].includes(phase) ||
        !questionAnswers.some(item => item.trim())) return;
    if (!window.confirm(
      "FILL YOUR REVIEWED EMPLOYER ANSWERS ONCE? You confirm every entered " +
      "statement is accurate and truthful. The employer may receive answers " +
      "immediately on input/change. " +
      (rememberMyAnswers && questionProfileMode === "guided" && questionMemoryAvailable
        ? "You ALSO approve saving eligible text answers permanently to your private profile for future exact-question suggestions. Dropdown and radio choices are NOT remembered. "
        : "No answer will be stored in your permanent profile. ") +
      "Sensitive questions, salary, visa, legal consent and identity details " +
      "remain manual. SmartPloy NEVER clicks Submit; uncertain fills are NOT retried."
    )) return;
    const approved = [...questionAnswers];
    void guarded(async () => {
      if (rememberMyAnswers && questionProfileMode === "guided") {
        if (!questionMemoryAvailable) {
          throw new Error("Profile memory is unavailable. Turn off answer saving or retry profile synchronization before filling.");
        }
        for (let i = 0; i < reviewedQuestions.length; i++) {
          const q = reviewedQuestions[i], answer = approved[i]?.trim();
          if (q.type === "select" || q.type === "radio_group" || !answer) continue;
          const remembered = questionMemory[q.label];
          if (!remembered) {
            throw new Error("This question is not yet saved to your profile. Reinspect it before filling.");
          }
          const reusable = remembered.reusable_scope === "exact_question";
          if (remembered.answer === answer &&
              remembered.approved_for_reuse === reusable) continue;
          const saved = await saveApplicationQuestionAnswer(
            remembered.question_key, remembered.version, answer, reusable,
            props.expectedUserId,
          );
          await verifyAccount();
          if (saved.employer_actions_performed !== 0 ||
              saved.automatic_employer_submission_authorized !== false ||
              saved.question.question_key !== remembered.question_key) {
            throw new Error("The reviewed profile answer was not saved safely.");
          }
        }
      }
      await verifyAccount();
      await verifyCurrentDraft();
      await verifyAccount();
      if (!mounted.current) return;
      // Only NOW burn the one-use local attempt, before browser input events.
      // A network response can be lost AFTER the employer site sees fields.
      setQuestionAttempted(true);
      const result = await callLocalPlaywrightBridge<LocalAnswersFilled>(
        "fill-questions", {
          plan_id: questionPlanId,
          confirmation: "FILL REVIEWED ANSWERS",
          answers: approved,
        }, { token: sessionToken.current, expectedStage: "answers_filled" },
      );
      if (!mounted.current) return;
      setQuestionAnswers([]);
      setQuestionStatus("Reviewed employer answers: " + result.filled + " of " +
        result.planned + " filled. " + (result.status === "filled_for_review"
          ? "Review every value in the employer browser before submitting."
          : "Some inputs changed or were refused; inspect the employer page " +
            "manually and do not retry."));
    });
  }

  function attachCurrentReviewedCv() {
    if (!props.enabled || inFlight.current || !sessionToken.current ||
        !cvAttachment.available || !cvAttachment.attach_id ||
        cvAttachAttempted || cvAttachBusy ||
        !["inspected", "filled"].includes(phase)) return;
    if (!window.confirm(
      "Attach the EXACT saved SmartPloy CV PDF to the reviewed \"" +
      cvAttachment.label + "\" field in the visible employer browser? " +
      "SmartPloy will re-download and verify the current private PDF, then " +
      "transfer it ONLY through localhost. The employer website may upload " +
      "the PDF as soon as the file input changes. This is a single attempt; " +
      "you must verify the employer's attachment and submit personally."
    )) return;
    void guarded(async () => {
      let packet: unknown;
      try { packet = JSON.parse(props.packetText); }
      catch { throw new Error("The private reviewed packet is invalid. Prepare a fresh one."); }
      if (!packet || typeof packet !== "object") {
        throw new Error("No reviewed CV document is available for attachment.");
      }
      const info = packet as Record<string, unknown>;
      if (info.workspace_id !== props.expectedWorkspaceId ||
          info.revision !== props.expectedRevision ||
          typeof info.cv_pdf_sha256 !== "string" ||
          typeof info.cv_pdf_size !== "number") {
        throw new Error("The saved CV revision no longer matches your reviewed application.");
      }
      setCvAttachBusy(true);
      try {
        const pdf = await fetchExactReviewedCvPdf(
          applicationDownloadUrl(props.expectedWorkspaceId, "cv", "pdf",
            props.expectedRevision),
          { cv_pdf_sha256: info.cv_pdf_sha256, cv_pdf_size: info.cv_pdf_size },
        );
        // A second identity check AFTER the private download prevents a
        // stale account from transferring someone else's CV to localhost.
        await verifyAccount();
        await verifyCurrentDraft();
        await verifyAccount();
        if (!mounted.current || !props.enabled) return;
        // Burn the UI attempt BEFORE the local helper sees valid PDF bytes.
        // A timeout may follow an actual employer-upload event; never retry.
        setCvAttachAttempted(true);
        const result = await attachExactReviewedCvLocally(
          pdf, sessionToken.current, cvAttachment.attach_id,
        );
        if (!mounted.current) return;
        setCvAttached(result.attached_locally);
        setFeedback("Exact reviewed CV PDF placed in the employer's " +
          cvAttachment.label + " field. This is NOT employer upload confirmation. " +
          "Check the employer page and click Submit personally.");
      } finally {
        if (mounted.current) setCvAttachBusy(false);
      }
    });
  }

  function observeManualEmployerReceipt() {
    if (!sessionToken.current || props.observationEnabled === false ||
        !["opened", "inspected", "filled", "uncertain"].includes(phase) ||
        inFlight.current || observedReceipt) return;
    if (!window.confirm(
      "OBSERVE THIS EMPLOYER CONFIRMATION? You PERSONALLY clicked the employer's " +
      "Submit button and can see a reference-bearing confirmation for this exact job. " +
      "SmartPloy will only LOOK at the visible Chromium page using the original " +
      "Chrome companion inspector. It will NOT submit, retry, or claim independent " +
      "employer verification. A separate action is required to record evidence."
    )) return;
    void guardedReceipt(async () => {
      const result = await callLocalPlaywrightBridge<LocalBridgeObserved>(
        "observe", { confirmation: "OBSERVE EMPLOYER CONFIRMATION" },
        { token: sessionToken.current, expectedStage: "observed" },
      );
      if (!mounted.current) return;
      if (!result.confirmed || !result.receipt) {
        setFeedback("No unique, reference-bearing confirmation is visible for " +
          "this exact job. Do NOT repeat an employer Submit action. " +
          "Check the existing employer portal manually.");
        return;
      }
      const r = result.receipt;
      if (r.workspace_id !== props.expectedWorkspaceId ||
          r.document_revision !== props.expectedRevision) {
        throw new Error("Observed receipt belongs to a different application.");
      }
      setObservedReceipt(r);
      setFeedback("Browser-visible reference found. The employer has NOT " +
        "independently confirmed delivery through SmartPloy. You may save the " +
        "observation below after another confirmation.");
    });
  }

  function saveManualReceiptObservation() {
    if (!observedReceipt || receiptSaveClaimed || inFlight.current ||
        props.observationEnabled === false || !sessionToken.current) return;
    if (!window.confirm(
      "SAVE THIS UNVERIFIED BROWSER OBSERVATION? Reference: " +
      observedReceipt.reference + ". You personally observed the employer page " +
      "after submitting this exact application. This records an owner-reported " +
      "browser observation only. It is NOT a provider acknowledgement, " +
      "does NOT increment independently verified submission counts, and " +
      "does NOT send or retry the application."
    )) return;
    void guardedReceipt(async () => {
      if (observedReceipt.workspace_id !== props.expectedWorkspaceId ||
          observedReceipt.document_revision !== props.expectedRevision) {
        throw new Error("Receipt no longer matches the current saved job.");
      }
      // A network timeout could follow a successfully committed receipt.
      // Never blindly replay a state-changing import for this observation.
      setReceiptSaveClaimed(true);
      const result = await importBrowserReceipt(
        props.expectedWorkspaceId, observedReceipt, props.expectedUserId,
      );
      if (result.external_confirmation_verified !== false ||
          result.receipt.status !== "browser_observed_unverified" ||
          result.receipt.independently_verified_by_employer !== false ||
          result.receipt.actually_submitted_count_changed !== false ||
          result.receipt.workspace_id !== props.expectedWorkspaceId ||
          result.receipt.document_revision !== props.expectedRevision) {
        throw new Error("The server did not return a valid unverified receipt status.");
      }
      if (!mounted.current) return;
      props.onReceiptImported?.(result.receipt);
      setFeedback("Employer page observation saved as UNVERIFIED. No application " +
        "was submitted by SmartPloy, and no employer acknowledgement was verified.");
    });
  }

  function stopLocalBrowser() {
    if (!sessionToken.current || inFlight.current) return;
    const token = sessionToken.current;
    sessionToken.current = "";
    setBusy(true); setError("");
    void callLocalPlaywrightBridge<LocalBridgeStopped>(
      "stop", {}, { token, expectedStage: "stopped" },
    ).then(() => {
      if (mounted.current) setFeedback("Local Playwright browser closed. Restart the helper for another job.");
    }).catch(() => {
      if (mounted.current) setError(
        "Could not confirm local browser closure. Press Ctrl+C in the helper terminal."
      );
    }).finally(() => {
      if (!mounted.current) return;
      setPhase("stopped"); setFields([]); setPlanId("");
      setCvAttachment({ available: false, label: "", attach_id: "" });
      setCvAttached(false); setCvAttachAttempted(true);
      setReviewedQuestions([]); setHumanOnlyQuestions([]);
      setQuestionAnswers([]); setQuestionPlanId("");
      setQuestionMemory({}); setQuestionMemoryAvailable(false);
      setQuestionProfileMode("guided"); setRememberMyAnswers(false);
      setQuestionAttempted(true); setQuestionInspectionDone(false);
      setQuestionStatus("");
      setBusy(false);
    });
  }

  const trustedPage = localBridgeOriginAllowed(window.location.origin);

  return <section className="local-playwright-panel" aria-label="Paired local Playwright browser">
    <div className="local-playwright-heading">
      <Monitor size={20} aria-hidden="true" />
      <div>
        <strong>Connect my local Playwright browser</strong>
        <p>Watch Chromium open the reviewed employer form. SmartPloy inspects safe fields first,
          shows you the plan, and fills them only after your approval. Final Submit stays yours.</p>
      </div>
    </div>
    <p className="local-playwright-notice">
      <ShieldCheck size={15} aria-hidden="true" />
      Private local connection only · 127.0.0.1 · CV attachment only after consent · no employer submission
    </p>
    <p className="muted">
      Install the reviewed Playwright ZIP once, then start <code>python bridge.py</code> on
      your own desktop. The terminal prints a one-use code. Keep the visible Chromium
      browser open while completing the employer's application. The Chrome extension
      remains an alternative when local-network access is blocked.
    </p>
    {!trustedPage ? <p role="alert">This origin cannot connect to your local Playwright helper.
      Use the Chrome companion instead.</p> : null}
    {phase === "not-paired" ? <div className="local-playwright-actions">
      {props.autoFillOnPair ? <label className="local-playwright-remember">
        <input type="checkbox" checked={autoFillAfterInspect}
          disabled={!props.enabled || busy}
          onChange={(event) => setAutoFillAfterInspect(event.target.checked)} />
        When this exact employer form is ready, fill my approved ordinary fields
        once after I confirm. Fields may transmit immediately to the employer;
        CV attachment and final Submit still require my separate approval.
      </label> : null}
      <label htmlFor="smartploy-local-playwright-code">Temporary local pairing code
        <input id="smartploy-local-playwright-code" type="password"
          autoComplete="off" spellCheck={false} value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Code printed by python bridge.py" maxLength={80} />
      </label>
      <button type="button" className="navy-btn"
        disabled={!props.enabled || busy || !trustedPage || !CODE.test(code.trim())}
        onClick={startLocalBrowser}>
        {busy ? "Opening visible Chromium…" :
          props.autoFillOnPair && autoFillAfterInspect
            ? "Start AutoApply · open, inspect & fill once"
            : "Start visible AutoApply (open & inspect)"}
      </button>
    </div> : null}
    {["opened", "inspected"].includes(phase) && !questionAttempted &&
      !cvAttachAttempted ? <div className="local-playwright-actions">
      <button type="button" className={phase === "opened" ? "navy-btn" : "outline-btn"}
        disabled={!props.enabled || busy}
        onClick={inspectLocalBrowser}>
        {busy ? "Inspecting…" : phase === "inspected"
          ? "Inspect current employer form again" : "Inspect current employer form"}
      </button>
      <small>After logging in or clicking Apply in visible Chromium, inspect again.
        This replaces the previous read-only field plan; no values are filled.</small>
    </div> : null}
    {phase === "inspected" ? <div className="local-playwright-actions">
      <strong>Reviewed safe fields ({fields.length})</strong>
      <ul className="local-playwright-fields">
        {fields.map((item, index) =>
          <li key={item.key + ":" + index}>{item.label} <small>{item.key}</small></li>)}
      </ul>
      {fields.length ? <button type="button" className="navy-btn"
        disabled={!props.enabled || busy}
        onClick={fillLocalBrowser}>
        Fill reviewed fields once (never submit)
      </button> : <small>No safe fields detected yet. Navigate to the real application
        form in visible Chromium, then use Inspect again.</small>}
    </div> : null}
    {sessionToken.current && ["opened", "inspected", "filled"].includes(phase) ?
      <div className="local-playwright-actions" aria-label="Reviewed employer questions">
        <strong>Employer questions · applicant review</strong>
        <p className="muted">
          Reuses the original Chrome companion question policy. Only safe,
          unanswered required text and native dropdown questions are eligible
          for optional one-time filling. You must answer salary, work authorization,
          legal consent, identity and other sensitive questions yourself.
        </p>
        <button type="button" className="outline-btn"
          disabled={!props.enabled || busy || questionAttempted}
          onClick={reviewEmployerQuestions}>
          {questionInspectionDone ? "Reinspect unanswered questions" :
            "Review unanswered employer questions"}
        </button>
        {questionInspectionDone ? <>
          {reviewedQuestions.length > 0 ? <div className="local-playwright-questions">
            {reviewedQuestions.map((question, i) =>
              <label key={question.index + ":" + question.label}>
                {question.label}
                {(question.type === "select" || question.type === "radio_group") ? <select
                  value={questionAnswers[i] || ""}
                  disabled={!props.enabled || busy || questionAttempted}
                  onChange={(event) => setQuestionAnswers(previous =>
                    previous.map((value, n) => n === i ? event.target.value : value)
                  )}>
                  <option value="">Choose an exact employer option</option>
                  {(question.options || []).map(option =>
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>)}
                </select> : <textarea rows={3}
                  value={questionAnswers[i] || ""}
                  maxLength={question.max_answer_length}
                  autoComplete="off" spellCheck={false}
                  placeholder="Write a truthful answer; leave blank to handle manually"
                  disabled={!props.enabled || busy || questionAttempted}
                  onChange={(event) => setQuestionAnswers(previous =>
                    previous.map((value, n) => n === i ? event.target.value : value)
                  )}/>} 
              </label>)}
            {reviewedQuestions.some(question => question.type !== "select" &&
              question.type !== "radio_group") ?
            <label className="local-playwright-remember">
              <input type="checkbox"
                checked={rememberMyAnswers}
                disabled={!props.enabled || busy || questionAttempted ||
                  questionProfileMode === "cv_only" || !questionMemoryAvailable}
                onChange={event => setRememberMyAnswers(event.target.checked)}
              />
              Permanently remember my reviewed text answers in my private profile
              for future exact-question suggestions. Native dropdown and radio selections
              are always application-specific (never submit automatically).
            </label> : null}
            <button type="button" className="navy-btn"
              disabled={!props.enabled || busy || questionAttempted ||
                !questionAnswers.some(value => value.trim())}
              onClick={fillReviewedEmployerAnswers}>
              Fill my reviewed answers once (never submit)
            </button>
          </div> : null}
          {humanOnlyQuestions.length ? <div className="local-playwright-manual">
            <strong>Answer personally on the employer website</strong>
            <ul>{humanOnlyQuestions.slice(0, 12).map((label, i) =>
              <li key={label + ":" + i}>{label}</li>)}</ul>
            {humanOnlyQuestions.length > 12 ?
              <p>Additional manual fields: {humanOnlyQuestions.length - 12}</p> : null}
          </div> : null}
          {questionStatus ? <p role="status">{questionStatus}</p> : null}
          {questionAttempted ? <p role="alert">
            Answer filling has been attempted once. Do not retry after
            an uncertain result; review the actual employer form manually.
          </p> : null}
        </> : null}
      </div> : null}
    {cvAttachment.available && ["inspected", "filled"].includes(phase) ?
      <div className="local-playwright-actions" aria-label="Reviewed CV PDF attachment">
        <strong>CV PDF · {cvAttachment.label}</strong>
        <p className="muted">
          Reuse your exact saved SmartPloy CV PDF (SHA-256 and file size verified
          against this reviewed job). The PDF goes to your own local helper,
          then to the employer input ONLY after another explicit approval.
          The employer may upload it immediately on input.
        </p>
        <button className="outline-btn" type="button"
          disabled={!props.enabled || busy || cvAttachBusy || cvAttachAttempted}
          onClick={attachCurrentReviewedCv}>
          {cvAttachBusy ? "Verifying local reviewed CV…" :
            "Attach exact saved CV PDF once"}
        </button>
        {cvAttached ? <p role="status">
          CV placed in the employer file input, but server acceptance is
          unverified. Review the visible employer page before submitting.
        </p> : null}
        {cvAttachAttempted && !cvAttached ? <p role="alert">
          Attachment result uncertain. Inspect the visible employer browser
          manually and do not retry this file action.
        </p> : null}
      </div> : null}
    {sessionToken.current && ["opened", "inspected", "filled", "uncertain"].includes(phase) &&
      props.observationEnabled !== false ?
      <div className="local-playwright-actions" aria-label="Manual employer receipt observation">
        <strong>After you submit personally: observe the employer receipt</strong>
        <p className="muted">
          First click the employer's own Submit button PERSONALLY, then
          inspect its confirmation here. This reuses SmartPloy's existing
          Chrome companion receipt observer. SmartPloy never clicks Submit.
          A visible reference is a browser observation, not provider verification.
        </p>
        <button type="button" className="outline-btn"
          disabled={busy || !!observedReceipt}
          onClick={observeManualEmployerReceipt}>
          Observe employer confirmation (read-only)
        </button>
        {observedReceipt ? <div className="local-playwright-receipt">
          <p><strong>Observed reference:</strong> {observedReceipt.reference}</p>
          <p><strong>Exact job confirmation:</strong> {observedReceipt.confirmation_page_url}</p>
          <p>Evidence is browser-observed and unverified by the employer.</p>
          <button type="button" className="navy-btn"
            disabled={busy || receiptSaveClaimed}
            onClick={saveManualReceiptObservation}>
            Save unverified observation to SmartPloy
          </button>
          {receiptSaveClaimed ? <p role="status">
            Receipt import was attempted once. If its outcome is uncertain,
            refresh My Applications to check the existing record; do not retry.
          </p> : null}
        </div> : null}
      </div> : null}
    {phase === "uncertain" ? <p role="alert">
      The fill attempt may have changed the employer form. Inspect the visible
      browser manually; do not retry an uncertain application.
    </p> : null}
    {phase === "filled" ? <p role="status" className="local-playwright-result">
      <CheckCircle2 size={17} aria-hidden="true" />
      Field-fill action completed. Your application is NOT submitted.
    </p> : null}
    {phase === "stopped" ? <p role="status">
      Session stopped. Restart <code>python bridge.py</code> for the next job.
    </p> : null}
    {feedback ? <p role="status" className="local-playwright-result">{feedback}</p> : null}
    {error ? <p role="alert" className="local-playwright-error">
      <XCircle size={16} aria-hidden="true" /> {error}
    </p> : null}
    {sessionToken.current && phase !== "stopped" ? <button type="button"
      className="outline-btn compact" disabled={busy} onClick={stopLocalBrowser}>
      Stop local browser session
    </button> : null}
    {!props.enabled ? <p role="alert">
      Additional form filling and CV attachment are blocked or unavailable.
      If you already submitted personally in this paired browser, you can
      observe the confirmation without triggering another employer action.
    </p> : null}
  </section>;
}
