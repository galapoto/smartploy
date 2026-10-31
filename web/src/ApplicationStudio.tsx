import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowUpRight, BriefcaseBusiness, CheckCircle2, Clock3,
  Download, FileCheck2, FileText, LockKeyhole, RefreshCw, Save, ShieldCheck,
  Trash2, AlertCircle, Sparkles, WandSparkles, ClipboardCopy, ExternalLink
} from "lucide-react";
import {
  applicationDownloadUrl, deleteApplicationWorkspace, editApplicationWorkspace,
  getApplicationWorkspaces, getApplicationWorkspaceById, markApplicationManuallySent,
  getLocalAIStatus, requestLocalAISuggestions, proposeEvidenceLetter,
  getBrowserHandoffReadiness, createBrowserHandoffPacket,
  getEmployerAttemptStatus, getEmployerReviewIntent, getEmployerFinalActionReadiness,
  getLeverPartnerReadiness, getLeverPartnerReceipt, sendLeverPartnerApplication,
  getAshbyPartnerReadiness, getAshbyPartnerReceipt, sendAshbyPartnerApplication,
  recordEmployerReviewIntent, cancelEmployerReviewIntent,
  getBrowserReceipt, importBrowserReceipt, getSession
} from "./api";
import ApplicationAgentCard from "./ApplicationAgentCard";
import ApplicationAgentInbox from "./ApplicationAgentInbox";
import ApplicationAttemptAudit from "./ApplicationAttemptAudit";
import type { ApplicationFlowMode, ApplicationWorkspace, LocalAIStatus, LocalAISuggestion, BrowserHandoffReadiness, BrowserObservedReceipt, BrowserReceiptImport } from "./types";
import { safeExternalJobUrl } from "./lib";
import { applicationNextStep } from "./applicationNextStep";
import { summarizeApplicationReviewQueue, type ApplicationReviewFilter } from "./applicationReviewQueue";
import type { EmployerAttemptState, EmployerReviewIntentState, EmployerFinalActionReadiness, LeverPartnerReadiness, LeverProviderAcknowledgment, LeverPartnerReviewEvidence } from "./api";

const ACCOUNT_CHANGED_NOTICE =
  "Your signed-in SmartPloy account changed or could not be verified. Reload SmartPloy to continue safely.";

class StudioAccountChanged extends Error {}
class StudioSelectionChanged extends Error {}

// A draft's identity is its workspace ID, revision, AND the viewer's
// selection epoch. Switching away and back must not resurrect late results.
type DraftTicket = { key: string; epoch: number };

const safePostingLink = safeExternalJobUrl;

/** UI routing hint ONLY. Never infer Lever rights for unrelated hosts.
 * Backend still enforces exact posting, independent rights and one-use claim.
 */
function partnerKind(url: string): "lever" | "ashby" | null {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password ||
        parsed.port) return null;
    if (parsed.hostname === "jobs.ashbyhq.com") return "ashby";
    if (parsed.hostname === "jobs.lever.co" ||
        parsed.hostname === "jobs.eu.lever.co") return "lever";
    return null;
  } catch {
    return null;
  }
}

// Reuse the existing review / packet hashes, never a browser clipboard token.
// The server rechecks all these fields in a new signed-in transaction.
function freshPartnerEvidence(
  evidence: LeverPartnerReviewEvidence | null | undefined,
  selected: ApplicationWorkspace
): evidence is LeverPartnerReviewEvidence {
  return !!evidence && evidence.workspace_id === selected.workspace_id &&
    evidence.revision === selected.revision && Date.parse(evidence.expires_at) > Date.now() &&
    /^[a-f0-9]{64}$/.test(evidence.document_sha256) &&
    /^[a-f0-9]{64}$/.test(evidence.cv_pdf_sha256) &&
    /^[a-f0-9]{64}$/.test(evidence.approved_fields_sha256) &&
    Number.isSafeInteger(evidence.cv_pdf_size) &&
    evidence.cv_pdf_size >= 12 && evidence.cv_pdf_size <= 2 * 1024 * 1024;
}

export default function ApplicationStudio(props: {
  focusId: string; expectedUserId: string; expectedAuthSource: string; onFindJobs: () => void;
  mode?: ApplicationFlowMode | null;
}) {
  const [workspaces, setWorkspaces] = useState<ApplicationWorkspace[]>([]);
  const [selectedId, setSelectedId] = useState(props.focusId);
  // The filter is local UI state. Owner-scoped workspaces never leave the
  // browser, and changing the filter never creates or submits a job case.
  const [reviewFilter, setReviewFilter] = useState<ApplicationReviewFilter>("all");
  const [cvText, setCvText] = useState("");
  const [letterText, setLetterText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAIBusy] = useState(false);
  const [letterBusy, setLetterBusy] = useState(false);
  const [aiStatus, setAIStatus] = useState<LocalAIStatus | null>(null);
  const [aiSuggestion, setAISuggestion] = useState<LocalAISuggestion | null>(null);
  const [handoff, setHandoff] = useState<BrowserHandoffReadiness | null>(null);
  const [employerAttempt, setEmployerAttempt] = useState<EmployerAttemptState | null>(null);
  const [finalReview, setFinalReview] = useState<EmployerReviewIntentState | null>(null);
  const [finalAction, setFinalAction] = useState<EmployerFinalActionReadiness | null>(null);
  const [partnerReadiness, setPartnerReadiness] = useState<LeverPartnerReadiness | null>(null);
  const [partnerReceipt, setPartnerReceipt] = useState<LeverProviderAcknowledgment | null>(null);
  const [partnerBusy, setPartnerBusy] = useState(false);
  const partnerSendingRef = useRef(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [handoffPacketText, setHandoffPacketText] = useState("");
  const [browserReceipt, setBrowserReceipt] = useState<BrowserObservedReceipt | null>(null);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [receiptInput, setReceiptInput] = useState("");
  const [receiptBusy, setReceiptBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [accountBlocked, setAccountBlocked] = useState(false);
  const mountedRef = useRef(false);
  const accountBlockedRef = useRef(false);
  const reloadGenerationRef = useRef(0);
  const selectedDraftRef = useRef<DraftTicket>({ key: "", epoch: 0 });
  const currentSelectedId = useRef(props.focusId);
  useEffect(() => { currentSelectedId.current = selectedId; }, [selectedId]);

  const isCurrentDraft = useCallback((ticket: DraftTicket) =>
    mountedRef.current && !accountBlockedRef.current &&
    selectedDraftRef.current.key === ticket.key &&
    selectedDraftRef.current.epoch === ticket.epoch, []);

  const captureDraft = (item: ApplicationWorkspace): DraftTicket => ({
    key: JSON.stringify([item.workspace_id, item.revision, item.application_url]),
    epoch: selectedDraftRef.current.epoch,
  });

  // The parent page normally remounts this component on an account switch.
  // Local refreshes and delayed responses still need their own boundary:
  // an unchanged email is not proof of an unchanged server-side account.
  const blockAccount = useCallback(() => {
    if (!mountedRef.current || accountBlockedRef.current) return;
    accountBlockedRef.current = true;
    ++reloadGenerationRef.current;
    ++selectedDraftRef.current.epoch;
    setWorkspaces([]); setSelectedId("");
    setCvText(""); setLetterText(""); setAISuggestion(null); setAIStatus(null);
    setHandoff(null); setEmployerAttempt(null); setFinalReview(null); setFinalAction(null);
    setPartnerReadiness(null); setPartnerReceipt(null); setPartnerBusy(false); setHandoffPacketText("");
    setBrowserReceipt(null); setReceiptOpen(false); setReceiptInput("");
    setMessage(""); setError(ACCOUNT_CHANGED_NOTICE);
    setBusy(false); setAIBusy(false); setLetterBusy(false); setHandoffBusy(false); setReceiptBusy(false); setReviewBusy(false); setPartnerBusy(false);
    setAccountBlocked(true); setLoading(false);
  }, []);

  const verifyAccount = useCallback(async () => {
    if (!mountedRef.current || accountBlockedRef.current) throw new StudioAccountChanged();
    let who;
    try {
      who = await getSession();
    } catch {
      blockAccount();
      throw new StudioAccountChanged();
    }
    if (!mountedRef.current || accountBlockedRef.current) throw new StudioAccountChanged();
    if (!props.expectedUserId.trim() || !who.authenticated ||
        who.user_id?.trim() !== props.expectedUserId.trim() ||
        (who.auth_source || "") !== props.expectedAuthSource) {
      blockAccount();
      throw new StudioAccountChanged();
    }
  }, [blockAccount, props.expectedAuthSource, props.expectedUserId]);

  // A private mutation is scoped to the identity that initiated it.
  // Backend expected-user headers still enforce ownership before writes;
  // these checks prevent publishing an old request's result into a new
  // browser account. A successful backend write is NOT rolled back.
  const runPrivateAction = useCallback(async <T,>(
    action: () => Promise<T>, ticket: DraftTicket
  ): Promise<T> => {
    await verifyAccount();
    if (!isCurrentDraft(ticket)) throw new StudioSelectionChanged();
    try {
      const result = await action();
      await verifyAccount();
      if (!isCurrentDraft(ticket)) throw new StudioSelectionChanged();
      return result;
    } catch (exc) {
      if (exc instanceof StudioAccountChanged || exc instanceof StudioSelectionChanged) throw exc;
      // A network failure may hide an account switch; verify before showing
      // an error, and never publish the former draft's error in the new one.
      await verifyAccount();
      if (!isCurrentDraft(ticket)) throw new StudioSelectionChanged();
      throw exc;
    }
  }, [isCurrentDraft, verifyAccount]);

  function reportActionError(exc: unknown, fallback: string) {
    if (exc instanceof StudioAccountChanged || exc instanceof StudioSelectionChanged ||
        !mountedRef.current || accountBlockedRef.current) return;
    setError(exc instanceof Error ? exc.message : fallback);
  }

  const reload = useCallback(async () => {
    if (accountBlockedRef.current) return;
    const generation = ++reloadGenerationRef.current;
    const active = () => mountedRef.current && !accountBlockedRef.current &&
      generation === reloadGenerationRef.current;
    try {
      // Verify BEFORE the private GET, and again BEFORE publishing it.
      // The latter covers cookie changes while the request is in flight.
      await verifyAccount();
      if (!active()) return;
      const result = await getApplicationWorkspaces();
      if (!active()) return;
      await verifyAccount();
      if (!active()) return;
      // Older owned cases may be beyond the original 100-workspace listing.
      // Reuse the exact owner-scoped GET rather than silently jumping back
      // to the first draft when that case is refreshed.
      const wanted = currentSelectedId.current || props.focusId;
      let visible = result.workspaces;
      if (wanted && !visible.some((item) => item.workspace_id === wanted)) {
        try {
          const older = await getApplicationWorkspaceById(wanted);
          await verifyAccount();
          if (!active()) return;
          visible = [...visible, older.workspace];
        } catch {
          // The old case may have been deleted in another tab. Verify that
          // a cookie/account switch was not hidden by the failed GET.
          await verifyAccount();
          if (!active()) return;
        }
      }
      if (!active()) return;
      setWorkspaces(visible);
      setSelectedId((current) => {
        const requested = current || props.focusId;
        return visible.some((item) => item.workspace_id === requested)
          ? requested : (visible[0]?.workspace_id || "");
      });
      setError("");
    } catch (exc) {
      if (!active()) return;
      // Even an HTTP/network error may conceal a cookie switch.
      // Preserve existing same-account edits only after re-verification.
      try { await verifyAccount(); } catch { return; }
      if (active()) {
        setError(exc instanceof Error ? exc.message : "Unable to load your application drafts.");
      }
    } finally {
      if (active()) setLoading(false);
    }
  }, [props.focusId, verifyAccount]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; ++reloadGenerationRef.current; };
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    let alive = true;
    void getLocalAIStatus().then((status) => {
      if (alive && !accountBlockedRef.current) setAIStatus(status);
    }).catch(() => {
      if (alive && !accountBlockedRef.current) setAIStatus(null);
    });
    return () => { alive = false; };
  }, []);

  const selected = useMemo(
    () => workspaces.find((item) => item.workspace_id === selectedId) || null,
    [workspaces, selectedId]
  );
  const selectedPartner = selected ? partnerKind(selected.application_url) : null;
  // Clear draft-local editor content, receipt/packet previews AND pending
  // indicators before a different draft can paint. The old draft's promise
  // may still finish; its completion must never unlock the new draft.
  useLayoutEffect(() => {
    const key = selected ? JSON.stringify([
      selected.workspace_id, selected.revision, selected.application_url,
    ]) : "";
    if (selectedDraftRef.current.key !== key) {
      selectedDraftRef.current = { key, epoch: selectedDraftRef.current.epoch + 1 };
      setBusy(false); setAIBusy(false); setLetterBusy(false); setHandoffBusy(false); setReceiptBusy(false); setReviewBusy(false); setPartnerBusy(false);
      setAISuggestion(null);
      setCvText(selected?.cv_text || "");
      setLetterText(selected?.cover_letter_text || "");
      setHandoffPacketText(""); setFinalReview(null); setFinalAction(null);
      setPartnerReadiness(null); setPartnerReceipt(null);
      setReceiptOpen(false); setReceiptInput("");
      setHandoff(null); setBrowserReceipt(null); setEmployerAttempt(null); setFinalReview(null); setFinalAction(null);
          setPartnerReadiness(null); setPartnerReceipt(null);
    }
  }, [selected?.workspace_id, selected?.revision, selected?.application_url]);

  useEffect(() => {
    if (!selected?.workspace_id || accountBlockedRef.current) return;
    let alive = true;
    const workspaceId = selected.workspace_id;
    void (async () => {
      try {
        await verifyAccount();
        if (!alive || accountBlockedRef.current) return;
        // Private owner reads revalidate identity both before and after.
        // Policy posture is NOT a browser grant or a submission instruction.
        const provider = partnerKind(selected.application_url);
        const [handoffResult, receiptResult, attemptResult, reviewResult, finalActionResult,
          partnerReadyResult, partnerReceiptResult] = await Promise.allSettled([
          getBrowserHandoffReadiness(workspaceId),
          getBrowserReceipt(workspaceId),
          getEmployerAttemptStatus(workspaceId),
          getEmployerReviewIntent(workspaceId),
          getEmployerFinalActionReadiness(workspaceId),
          provider === "ashby" ? getAshbyPartnerReadiness(workspaceId)
            : provider === "lever" ? getLeverPartnerReadiness(workspaceId) : Promise.resolve(null),
          provider === "ashby" ? getAshbyPartnerReceipt(workspaceId)
            : provider === "lever" ? getLeverPartnerReceipt(workspaceId) : Promise.resolve(null),
        ]);
        if (!alive || accountBlockedRef.current) return;
        await verifyAccount();
        if (!alive || accountBlockedRef.current) return;
        setHandoff(handoffResult.status === "fulfilled" ? handoffResult.value : null);
        setBrowserReceipt(receiptResult.status === "fulfilled" ? receiptResult.value.receipt : null);
        setEmployerAttempt(attemptResult.status === "fulfilled" ? attemptResult.value : null);
        setFinalReview(reviewResult.status === "fulfilled" ? reviewResult.value : null);
        setFinalAction(finalActionResult.status === "fulfilled" ? finalActionResult.value : null);
        setPartnerReadiness(partnerReadyResult.status === "fulfilled" &&
          partnerReadyResult.value?.partner_provider === provider ? partnerReadyResult.value : null);
        setPartnerReceipt(partnerReceiptResult.status === "fulfilled" &&
          partnerReceiptResult.value?.receipt?.provider === provider
            ? partnerReceiptResult.value.receipt : null);
      } catch {
        // verifyAccount clears private state and blocks the editor on any
        // missing or different session. Ordinary API failures show no data.
        if (alive && !accountBlockedRef.current) {
          setHandoff(null); setBrowserReceipt(null); setEmployerAttempt(null); setFinalReview(null); setFinalAction(null);
          setPartnerReadiness(null); setPartnerReceipt(null);
        }
      }
    })();
    return () => { alive = false; };
  }, [selected?.workspace_id, selected?.revision, selected?.application_url, verifyAccount]);

  const dirty = Boolean(selected && (
    cvText !== selected.cv_text || letterText !== selected.cover_letter_text
  ));

  // Presentation-only: server-owned job rights, reviewed-document hashes,
  // previous attempts, workspace outcome and saved revision remain authoritative.
  // Stale/missing reads cannot become a green "ready to submit" message.
  const nextAction = selected ? applicationNextStep({
    workspaceStatus: selected.status,
    unsavedEdits: dirty,
    previousAttemptReserved: employerAttempt?.previous_attempt_reserved === true,
    attemptStatusKnown: employerAttempt !== null,
    browserReceiptObserved: browserReceipt !== null,
    handoffReady: handoff?.document_revision === selected.revision ? handoff.ready : null,
    handoffBlockers: handoff?.document_revision === selected.revision ? handoff.blockers : [],
    partnerRightsReviewed: !!selectedPartner &&
      partnerReadiness?.partner_provider === selectedPartner &&
      partnerReadiness?.partner_api_configured === true &&
      partnerReadiness?.independent_partner_rights_reviewed === true &&
      partnerReadiness?.current_document_and_posting_ready === true &&
      partnerReadiness?.prior_employer_attempt === false,
    partnerFinalEligible: !!selectedPartner &&
      partnerReadiness?.partner_provider === selectedPartner &&
      partnerReadiness?.eligible_for_explicit_partner_submit === true &&
      finalReview?.review_recorded === true &&
      Date.parse(finalReview?.expires_at || "") > Date.now() &&
      freshPartnerEvidence(partnerReadiness?.review_evidence,selected),
  }) : null;

  // Reuse the already saved owner-scoped workspace list. Moving between
  // applications never creates another draft, agent, or employer attempt.
  // Wrap in list order, but skip acknowledged and self-reported outcomes.
  const nextDraft = useMemo(() => {
    const current = workspaces.findIndex((item) => item.workspace_id === selectedId);
    if (current < 0) return null;
    return [...workspaces.slice(current + 1), ...workspaces.slice(0, current)]
      .find((item) => item.status === "draft") || null;
  }, [workspaces, selectedId]);

  // Categorize only the verified owner-scoped rows that are currently loaded.
  // Do not imply full-account totals or per-job partner authorization from
  // these durable high-level workspace statuses.
  const reviewQueue = useMemo(
    () => summarizeApplicationReviewQueue(workspaces, reviewFilter),
    [workspaces, reviewFilter],
  );

  function pick(id: string) {
    if (dirty && !window.confirm("Discard unsaved changes and open another draft?")) return;
    if (id !== selectedId) ++selectedDraftRef.current.epoch;
    setSelectedId(id);
    setMessage("");
    setError("");
  }

  async function openInboxCase(workspaceId: string) {
    if (workspaces.some((item) => item.workspace_id === workspaceId)) {
      pick(workspaceId);
      return;
    }
    if (dirty && !window.confirm("Discard unsaved changes and open another draft?")) return;
    // Opening an older owned workspace is a read-only operation. The server
    // rechecks ownership, and both session and selection are revalidated
    // before the response can replace an on-screen private application.
    const epoch = ++selectedDraftRef.current.epoch;
    setError(""); setMessage("");
    try {
      await verifyAccount();
      const found = await getApplicationWorkspaceById(workspaceId);
      await verifyAccount();
      if (!mountedRef.current || accountBlockedRef.current ||
          selectedDraftRef.current.epoch !== epoch) return;
      setWorkspaces((items) => [...items.filter(
        (item) => item.workspace_id !== found.workspace.workspace_id
      ), found.workspace]);
      setSelectedId(found.workspace.workspace_id);
    } catch (exc) {
      if (!mountedRef.current || accountBlockedRef.current ||
          selectedDraftRef.current.epoch !== epoch) return;
      try { await verifyAccount(); } catch { return; }
      if (selectedDraftRef.current.epoch === epoch) {
        setError(exc instanceof Error ? exc.message : "Unable to open this private application.");
      }
    }
  }

  function updateItem(item: ApplicationWorkspace) {
    setWorkspaces((items) => items.map((before) => before.workspace_id === item.workspace_id ? item : before));
    setSelectedId(item.workspace_id);
  }

  async function save() {
    if (!selected || selected.status !== "draft" || browserReceipt ||
        partnerReceipt || employerAttempt?.previous_attempt_reserved) return;
    const ticket = captureDraft(selected);
    setBusy(true); setMessage(""); setError("");
    try {
      const result = await runPrivateAction(() => editApplicationWorkspace(
        selected.workspace_id, selected.revision, cvText, letterText, props.expectedUserId
      ), ticket);
      if (!isCurrentDraft(ticket)) return;
      updateItem(result.workspace);
      setMessage("Your edits were saved. Downloaded documents will contain this version.");
    } catch (exc) {
      reportActionError(exc, "Draft could not be saved.");
    } finally { if (isCurrentDraft(ticket)) setBusy(false); }
  }

  async function redraftLetter(language: "fi" | "en") {
    if (!selected || selected.status !== "draft" || busy || letterBusy ||
        aiBusy || !!browserReceipt || !!partnerReceipt ||
        employerAttempt?.previous_attempt_reserved) return;
    if (dirty && !window.confirm(
      "Replace your current unsaved cover-letter changes with a new " +
      (language === "fi" ? "Finnish" : "English") +
      " draft? Unsaved CV edits will remain in the editor, but neither " +
      "document will be saved automatically."
    )) return;
    const ticket = captureDraft(selected);
    setLetterBusy(true); setError(""); setMessage("");
    try {
      // Reuse the same account- and saved-revision checks that guard edits.
      const proposal = await runPrivateAction(
        () => proposeEvidenceLetter(
          selected.workspace_id, selected.revision, language,
          props.expectedUserId,
        ), ticket,
      );
      if (!isCurrentDraft(ticket)) return;
      if (proposal.workspace_revision !== selected.revision ||
          !proposal.review_required || proposal.saved ||
          proposal.employer_contacts !== 0 ||
          proposal.external_actions_performed !== 0) {
        throw new Error("The private cover-letter proposal was not safe to use");
      }
      setLetterText(proposal.cover_letter);
      setMessage(proposal.complete === false
        ? "Letter prose inserted, but it needs more confirmed information: " +
          (proposal.missing_information || []).join(" ") +
          " Review the wording and click Save changes. Nothing was sent to an employer."
        : (language === "fi" ? "Finnish" : "English") +
          " cover letter generated as complete, editable prose. Review each claim, " +
          "personalize if needed, and click Save changes. Nothing was sent to an employer."
      );
    } catch (exc) {
      reportActionError(exc, "Unable to create a private evidence-backed draft.");
    } finally {
      setLetterBusy(false);
    }
  }

  async function askLocalAI() {
    if (!selected || dirty || selected.status !== "draft" || browserReceipt ||
        employerAttempt?.previous_attempt_reserved || !aiStatus?.ready) return;
    const ok = window.confirm(
      "Send the job description and your approved profile facts to the configured " +
      "private local ObumAI/Ollama model? Your uploaded CV file, unapproved profile " +
      "facts, and employer applications will NOT be sent. The response is a draft " +
      "proposal only and must be reviewed before saving."
    );
    if (!ok) return;
    const ticket = captureDraft(selected);
    setAIBusy(true); setError(""); setMessage(""); setAISuggestion(null);
    try {
      const response = await runPrivateAction(() =>
        requestLocalAISuggestions(selected.workspace_id, selected.revision, props.expectedUserId),
        ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setAISuggestion(response.suggestion);
      setMessage("Local AI returned draft suggestions. Review them and choose whether to insert them.");
    } catch (exc) {
      reportActionError(exc, "Local AI is currently unavailable.");
    } finally { if (isCurrentDraft(ticket)) setAIBusy(false); }
  }

  async function insertAISuggestion() {
    if (!selected || !aiSuggestion || selected.status !== "draft" || browserReceipt ||
        employerAttempt?.previous_attempt_reserved) return;
    const draft = aiSuggestion.proposal;
    const ticket = captureDraft(selected);
    if (!window.confirm(
      "Insert these AI suggestions into your editable CV and cover letter? " +
      "They may contain mistakes. Nothing is saved or sent until you review and click Save changes."
    )) return;
    try { await verifyAccount(); } catch { return; }
    if (!isCurrentDraft(ticket)) return;
    setCvText((old) =>
      "TARGET ROLE: " + selected.role_title + " — " + selected.company +
      "\n\nPROFILE SUMMARY (review AI wording):\n" + draft.cv_summary +
      "\n\n" + old
    );
    setLetterText(draft.cover_letter);
    setAISuggestion(null);
    setMessage("AI wording inserted as unsaved edits. Review every claim and save to keep them.");
  }

  async function copyBrowserPacket() {
    if (!selected || dirty || !handoff?.ready || selected.status !== "draft" || browserReceipt ||
        employerAttempt?.previous_attempt_reserved) return;
    let origin = "the employer website";
    try { origin = new URL(selected.application_url).origin; } catch { /* disabled by API validation */ }
    if (!window.confirm(
      "Prepare a short-lived job-application packet for " + origin + "? " +
      "This copies your approved name and contact fields, and reviewed cover letter, " +
      "to your computer clipboard. Keep it private; you will paste it into the " +
      "optional SmartPloy browser companion. No form is filled or submitted by this action."
    )) return;
    const ticket = captureDraft(selected);
    setHandoffBusy(true); setError(""); setMessage("");
    try {
      const response = await runPrivateAction(() =>
        createBrowserHandoffPacket(selected.workspace_id, selected.revision, props.expectedUserId),
        ticket
      );
      if (!isCurrentDraft(ticket)) return;
      const json = JSON.stringify(response.packet);
      if (navigator.clipboard?.writeText) {
        let copied = false;
        try {
          await navigator.clipboard.writeText(json);
          copied = true;
        } catch {
          // Clipboard permissions may be denied; allow deliberate manual copy.
        }
        // A browser sign-in can change while the clipboard API is pending.
        // Do not show a former user's packet or a success notice afterwards.
        await verifyAccount();
        if (!isCurrentDraft(ticket)) return;
        setHandoffPacketText(json);
        setMessage(copied
          ? "Private packet copied. Open the employer posting and use the browser companion within 15 minutes. Review and attach CV before submitting manually on the employer website."
          : "Your private packet is ready below. Select and copy it manually, then open the employer posting and browser companion.");
      } else {
        await verifyAccount();
        if (!isCurrentDraft(ticket)) return;
        setHandoffPacketText(json);
        setMessage("Your private packet is ready below. Select and copy it manually into the browser companion.");
      }
    } catch (exc) {
      reportActionError(exc, "Unable to copy the application packet.");
    } finally { if (isCurrentDraft(ticket)) setHandoffBusy(false); }
  }

  /** Reuse the exact existing 10-minute reviewed-intent route for both
   * manual browser handoff and official partner API. A success is NOT submit.
   */
  async function storeReviewedEvidence(
    ticket: DraftTicket, evidence: {
      document_sha256: string; cv_pdf_sha256: string; approved_fields_sha256: string;
    }
  ) {
    if (!selected) return;
    const item = await runPrivateAction(() => recordEmployerReviewIntent(
      selected.workspace_id,selected.revision,
      evidence.document_sha256,evidence.cv_pdf_sha256,
      evidence.approved_fields_sha256,props.expectedUserId
    ),ticket);
    if (!isCurrentDraft(ticket)) return;
    setFinalReview(item);
    setMessage("Review recorded temporarily. No employer application was sent.");
    setPartnerReadiness(null);
    const provider = partnerKind(selected.application_url);
    if (!provider) return;
    // Never infer partner eligibility from a successful review write. The
    // original signed-in private GET rechecks separate employer rights.
    try {
      const refreshed = await runPrivateAction(
        () => provider === "ashby"
            ? getAshbyPartnerReadiness(selected.workspace_id)
            : getLeverPartnerReadiness(selected.workspace_id),ticket
      );
      if (isCurrentDraft(ticket)) setPartnerReadiness(refreshed);
    } catch {
      if (isCurrentDraft(ticket)) setPartnerReadiness(null);
    }
  }

  /** One click to review a partner job, with no clipboard/extension dependency. */
  async function recordPartnerReview() {
    const provider = selected ? partnerKind(selected.application_url) : null;
    if (!selected || !provider || dirty || !handoff?.ready || !finalReview ||
        finalReview.review_state === "stale" || reviewBusy ||
        partnerBusy || browserReceipt || partnerReceipt ||
        partnerReadiness?.partner_provider !== provider ||
        employerAttempt?.previous_attempt_reserved ||
        !partnerReadiness?.partner_api_configured ||
        !partnerReadiness.independent_partner_rights_reviewed ||
        partnerReadiness.prior_employer_attempt ||
        !freshPartnerEvidence(partnerReadiness.review_evidence,selected)) return;
    const evidence=partnerReadiness.review_evidence;
    if (!window.confirm(
      "REVIEW EXACT CV, COVER LETTER AND JOB FOR " + selected.company + "?\n\n" +
      "I have checked the displayed CV, letter, name, approved contact details, " +
      "this vacancy and employer form. Save my review for ten minutes. " +
      "This step DOES NOT submit to any employer, share personal data externally, " +
      "or authorize a future automatic application."
    )) return;
    const ticket=captureDraft(selected);
    setReviewBusy(true);setError("");setMessage("");
    try {
      await storeReviewedEvidence(ticket,evidence);
    } catch (exc) {
      reportActionError(exc,"The reviewed partner application could not be recorded.");
    } finally {
      if (isCurrentDraft(ticket)) setReviewBusy(false);
    }
  }

  /** Records exact reviewed CV/letter, but never authorizes an employer submission. */
  async function recordFinalReview() {
    if (!selected || !handoffPacketText || dirty || !handoff?.ready ||
        !finalReview || finalReview.review_state === "stale" ||
        employerAttempt?.previous_attempt_reserved ||
        reviewBusy || browserReceipt) return;
    let packet;
    try {
      packet = JSON.parse(handoffPacketText) as {
        workspace_id: string; revision: number; expires_at: string;
        document_sha256: string; cv_pdf_sha256: string;
        approved_fields_sha256: string;
      };
      if (packet.workspace_id !== selected.workspace_id ||
          packet.revision !== selected.revision ||
          Date.parse(packet.expires_at) <= Date.now() ||
          !/^[a-f0-9]{64}$/.test(packet.document_sha256) ||
          !/^[a-f0-9]{64}$/.test(packet.cv_pdf_sha256) ||
          !/^[a-f0-9]{64}$/.test(packet.approved_fields_sha256)) {
        throw new Error("Your reviewed application packet changed or expired. Generate a new packet.");
      }
    } catch (exc) {
      reportActionError(exc, "Review packet is invalid.");
      return;
    }
    if (!window.confirm(
      "RECORD A 10-MINUTE REVIEW FOR " + selected.role_title + " AT " + selected.company + "?\n\n" +
      "I have reviewed the exact CV PDF, letter and job. This only records my review; " +
      "it DOES NOT submit the application or authorize SmartPloy to click the employer's Submit button."
    )) return;
    const ticket = captureDraft(selected);
    setReviewBusy(true); setError(""); setMessage("");
    try {
      await storeReviewedEvidence(ticket,packet);
    } catch (exc) {
      reportActionError(exc, "Review was not recorded.");
    } finally { if (isCurrentDraft(ticket)) setReviewBusy(false); }
  }

  async function cancelFinalReview() {
    if (!selected || !finalReview ||
        (finalReview.review_state !== "stale" && !finalReview.review_recorded)
        || reviewBusy) return;
    const ticket = captureDraft(selected);
    setReviewBusy(true); setError(""); setMessage("");
    try {
      const result = await runPrivateAction(
        () => cancelEmployerReviewIntent(selected.workspace_id, props.expectedUserId), ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setFinalReview(result);
      setPartnerReadiness(null);
      setMessage("Review cancelled. No employer application was submitted.");
      const provider = partnerKind(selected.application_url);
      if (!provider) return;
      try {
        const refreshed = await runPrivateAction(
          () => provider === "ashby"
            ? getAshbyPartnerReadiness(selected.workspace_id)
            : getLeverPartnerReadiness(selected.workspace_id),ticket
        );
        if (isCurrentDraft(ticket)) setPartnerReadiness(refreshed);
      } catch {
        if (isCurrentDraft(ticket)) setPartnerReadiness(null);
      }
    } catch (exc) {
      reportActionError(exc, "Unable to cancel the review.");
    } finally { if (isCurrentDraft(ticket)) setReviewBusy(false); }
  }

  /** A real employer API POST: no clipboard, only signed-in server preview. */
  async function sendPartnerApplication() {
    const provider = selected ? partnerKind(selected.application_url) : null;
    if (!selected || !provider || dirty || !handoff?.ready ||
        !finalReview?.review_recorded ||
        Date.parse(finalReview.expires_at) <= Date.now() ||
        !partnerReadiness?.eligible_for_explicit_partner_submit ||
        partnerReadiness.partner_provider !== provider ||
        employerAttempt?.previous_attempt_reserved || browserReceipt ||
        partnerReceipt || partnerBusy || partnerSendingRef.current ||
        !freshPartnerEvidence(partnerReadiness.review_evidence,selected)) return;
    const evidence=partnerReadiness.review_evidence;
    if (!window.confirm(
      "SEND THIS APPLICATION TO THE AUTHORIZED " +
            provider.toUpperCase() + " EMPLOYER?\n\n" +
      selected.role_title + " · " + selected.company + "\n\n" +
      "I have reviewed the exact CV PDF, cover letter, contact details, employer form " +
      "and employer data-processing terms. I approve transferring them to the employer " +
      "now. This can create a real job application. If the outcome is uncertain, " +
      "SmartPloy will NOT retry automatically."
    )) return;
    const ticket = captureDraft(selected);
    partnerSendingRef.current = true;
    setPartnerBusy(true); setError(""); setMessage("");
    try {
      const result = await runPrivateAction(
        () => (provider === "ashby"
          ? sendAshbyPartnerApplication : sendLeverPartnerApplication)(
          selected.workspace_id,selected.revision,
          evidence.document_sha256,evidence.cv_pdf_sha256,
          evidence.approved_fields_sha256,evidence.cv_pdf_size,
          props.expectedUserId
        ),ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setPartnerReadiness(previous => previous
        ? {...previous,prior_employer_attempt:true,eligible_for_explicit_partner_submit:false,
           review_evidence:null,provider_acknowledged:result.state==="provider_acknowledged"} : null);
      if (result.state==="provider_acknowledged") {
        // The receipt repository already committed provider acknowledgement
        // and workspace status together. Do not invent self-reported status.
        setWorkspaces(items => items.map(item =>
          item.workspace_id === selected.workspace_id
            ? {...item,status:"provider_acknowledged"} : item
        ));
        setPartnerReceipt(result);
        setMessage((result.provider === "ashby" ? "Ashby" : "Lever") +
          " confirmed creation of this job application. Reference: " +
          result.provider_application_id + ". This is not a hiring decision.");
      } else {
        setMessage("Employer response is uncertain. Do not retry; check the employer portal or contact support.");
      }
    } catch (exc) {
      // The HTTP response may have been lost after the employer accepted
      // an application. Fail closed; never send twice on a transient error.
      if (isCurrentDraft(ticket)) {
        setPartnerReadiness(previous => previous
          ? {...previous,eligible_for_explicit_partner_submit:false,
             review_evidence:null} : null);
      }
      reportActionError(exc,"The partner outcome is unknown. Do not retry automatically.");
    } finally {
      partnerSendingRef.current = false;
      if (isCurrentDraft(ticket)) setPartnerBusy(false);
    }
  }

  async function onImportObservedReceipt() {
    // A reserved employer claim prevents ANOTHER send, not importing
    // observation-only proof for the original reviewed application.
    if (!selected || selected.status !== "draft" || browserReceipt ||
        partnerReceipt) return;
    let parsed: BrowserReceiptImport;
    try {
      if (receiptInput.length < 30 || receiptInput.length > 5000) {
        throw new Error("Paste the bounded receipt generated by the SmartPloy browser companion.");
      }
      parsed = JSON.parse(receiptInput) as BrowserReceiptImport;
      if (parsed.schema !== "smartploy.browser_receipt.v1" ||
          parsed.workspace_id !== selected.workspace_id ||
          parsed.document_revision !== selected.revision ||
          parsed.confirmed_visible !== true) {
        throw new Error("This receipt is not for the current reviewed application revision.");
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Receipt is not valid JSON."); return;
    }
    if (!window.confirm(
      "Store this browser-observed employer confirmation? The employer has NOT independently "
      + "verified it through SmartPloy. This action does not count as a verified submission."
    )) return;
    const ticket = captureDraft(selected);
    setReceiptBusy(true); setError(""); setMessage("");
    try {
      const response = await runPrivateAction(() =>
        importBrowserReceipt(selected.workspace_id, parsed, props.expectedUserId),
        ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setBrowserReceipt(response.receipt);
      setReceiptOpen(false); setReceiptInput("");
      setMessage("Employer confirmation was recorded as browser-observed, not independently verified.");
    } catch (exc) {
      reportActionError(exc, "Unable to store this browser receipt.");
    } finally { if (isCurrentDraft(ticket)) setReceiptBusy(false); }
  }

  async function markApplied() {
    // Reconciliation of a consumed one-use attempt is NOT a second employer
    // transfer. The signed-in owner must personally confirm an actual send.
    if (!selected || selected.status !== "draft" || partnerReceipt) return;
    if (dirty) { setError("Save the document changes before updating its application status."); return; }
    const reserved = employerAttempt?.previous_attempt_reserved === true;
    if (reserved && !browserReceipt) {
      setError("Import a matching browser-observed confirmation before reporting a reserved attempt. If no confirmation exists, leave the attempt for human review; do not retry.");
      return;
    }
    if (!window.confirm(reserved
      ? "RECONCILE THIS PREVIOUS EMPLOYER ATTEMPT?\n\n" +
        "Only continue if you PERSONALLY CONFIRMED the employer received your application. " +
        "This records your own report; it does NOT verify an employer acknowledgement, " +
        "click Submit, or retry the reserved attempt. If the result is uncertain, CANCEL " +
        "and leave the application awaiting review."
      : "Confirm that you personally submitted this application on the employer's website. " +
        "SmartPloy has NOT submitted it or verified the employer's confirmation."
    )) return;
    const reference = window.prompt("Optional employer confirmation/reference (leave blank if unavailable):", "");
    if (reference === null) return;
    const ticket = captureDraft(selected);
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await runPrivateAction(() =>
        markApplicationManuallySent(
          selected.workspace_id, selected.revision, reference, props.expectedUserId
        ), ticket
      );
      if (!isCurrentDraft(ticket)) return;
      updateItem(result.workspace);
      setMessage("Recorded as personally reported applied, not independently verified by the employer.");
    } catch (exc) {
      reportActionError(exc, "Unable to record this application.");
    } finally { if (isCurrentDraft(ticket)) setBusy(false); }
  }

  async function remove() {
    if (!selected || !window.confirm(
      "Permanently delete this application workspace and its document text? " +
      "Previously delivered applications are NOT withdrawn, and the durable anti-duplicate " +
      "record and provider acknowledgment are preserved for reconciliation. " +
      "Original CV and approved profile facts remain."
    )) return;
    const ticket = captureDraft(selected);
    setBusy(true); setError(""); setMessage("");
    try {
      await runPrivateAction(() =>
        deleteApplicationWorkspace(selected.workspace_id, props.expectedUserId),
        ticket
      );
      if (!isCurrentDraft(ticket)) return;
      const remaining = workspaces.filter((item) => item.workspace_id !== selected.workspace_id);
      setWorkspaces(remaining);
      setSelectedId(remaining[0]?.workspace_id || "");
      setMessage("Draft removed from SmartPloy.");
    } catch (exc) {
      reportActionError(exc, "Unable to delete this draft.");
    } finally { if (isCurrentDraft(ticket)) setBusy(false); }
  }

  if (accountBlocked) {
    return <section className="panel studio-loading" role="alert">
      <LockKeyhole size={23}/>
      <h3>Account verification required</h3>
      <p>{ACCOUNT_CHANGED_NOTICE}</p>
    </section>;
  }

  if (loading) {
    return <section className="panel studio-loading">
      <RefreshCw size={21} className="rotate" />
      <p>Loading your private application drafts…</p>
    </section>;
  }

  return <section className="panel application-studio">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">PREPARE · REVIEW · DOWNLOAD</p>
        <h2>Application studio</h2>
        <p>Build application documents from your uploaded CV and verified career evidence.</p>
      </div>
      <button type="button" className="outline-btn compact" onClick={() => void reload()} aria-label="Refresh drafts"><RefreshCw size={16} /> Refresh</button>
    </div>
    {error ? <div className="studio-alert error" role="alert"><AlertCircle size={16}/>{error}</div> : null}
    {message ? <div className="studio-alert" role="status"><CheckCircle2 size={16}/>{message}</div> : null}
    {workspaces.length > 0 ? <>
      <ApplicationAgentInbox
        verifyAccount={verifyAccount} expectedUserId={props.expectedUserId}
        onOpen={(id) => void openInboxCase(id)}
      />
      <ApplicationAttemptAudit workspaces={workspaces}
        verifyAccount={verifyAccount}
        onOpen={(id) => pick(id)}
      />
    </> : null}
    {workspaces.length === 0 ? (
      <div className="studio-empty">
        <div className="studio-empty-icon"><FileCheck2 size={25}/></div>
        <h3>No application drafts yet</h3>
        <p>Go to Find jobs, choose a vacancy, then select <strong>Prepare documents</strong>. You can edit and download a CV and cover letter without ObumAI service access.</p>
        <button type="button" className="primary-btn" onClick={props.onFindJobs}>Choose a job <ArrowRight size={16}/></button>
      </div>
    ) : <div className="studio-layout">
      <section className="studio-review-queue" aria-label="Application review queue">
        <div className="studio-review-queue-heading">
          <div>
            <span className="section-kicker">WHAT NEEDS ATTENTION</span>
            <h3>Continue your applications</h3>
            <p>{reviewQueue.drafts} private draft{reviewQueue.drafts === 1 ? "" : "s"} to finish
              {" · "}{reviewQueue.selfReported} self-reported
              {" · "}{reviewQueue.providerAcknowledged} employer-acknowledged.
              A draft status alone does not prove employer receipt.</p>
          </div>
          {nextDraft ? <button className="navy-btn compact" type="button"
            aria-label={"Review next saved draft: " + nextDraft.role_title}
            onClick={() => pick(nextDraft.workspace_id)}>
            Review next draft <ArrowRight size={15} aria-hidden="true"/>
          </button> : selected?.status === "draft" ?
            <a className="navy-btn compact" href="#smartploy-cv-review">
              Continue this draft <ArrowRight size={15} aria-hidden="true"/>
            </a> : null}
        </div>
        <div className="studio-review-queue-filters" role="group"
          aria-label="Filter application statuses">
          {([
            ["all", "All", reviewQueue.totalLoaded],
            ["draft", "Drafts to finish", reviewQueue.drafts],
            ["self_reported_applied", "Self-reported", reviewQueue.selfReported],
            ["provider_acknowledged", "Employer acknowledged", reviewQueue.providerAcknowledged],
          ] as const).map(([key, label, count]) =>
            <button type="button" key={key}
              aria-pressed={reviewFilter === key}
              onClick={() => setReviewFilter(key)}>
              {label} <span>{count}</span>
            </button>)}
        </div>
        <p className="studio-review-queue-note">
          These are counts from {reviewQueue.totalLoaded} loaded private application
          {reviewQueue.totalLoaded === 1 ? "" : "s"}, not necessarily every older case.
          The filter changes only the list below; it does not contact any employer.
        </p>
      </section>
      <aside className="studio-list" aria-label="Your application drafts">
        <div className="studio-list-heading"><strong>My applications</strong>
          <span>{reviewQueue.filtered.length}</span></div>
        {reviewQueue.filtered.length === 0 ? <p className="studio-list-empty" role="status">
          No loaded applications in this category. Choose another status filter.
        </p> : null}
        {selected && !reviewQueue.filtered.some((item) =>
          item.workspace_id === selected.workspace_id) ? <p className="studio-list-filter-note">
          Your currently open application is outside this filter.
          Select a listed application to switch.
        </p> : null}
        {reviewQueue.filtered.map((item) => <button
          key={item.workspace_id} type="button"
          className={"studio-list-item" + (selectedId === item.workspace_id ? " selected" : "")}
          onClick={() => pick(item.workspace_id)}
          aria-current={selectedId === item.workspace_id ? "true" : undefined}
        >
          <span className="studio-list-icon"><BriefcaseBusiness size={17}/></span>
          <span className="studio-list-copy"><strong>{item.role_title}</strong><small>{item.company}</small>
            <em>{item.status === "provider_acknowledged"
              ? "Sent · " + (partnerKind(item.application_url) === "ashby" ? "Ashby" :
                 partnerKind(item.application_url) === "lever" ? "Lever" : "provider") + " acknowledged" :
              item.status === "self_reported_applied" ? "Applied · self-reported" :
              item.workspace_id === selectedId && browserReceipt
                ? "Confirmation observed · not verified" :
              item.workspace_id === selectedId && employerAttempt?.previous_attempt_reserved
                ? "Attempt reserved · review outcome" :
              "Draft · employer outcome unverified"}</em>
          </span>
        </button>)}
        <button type="button" className="secondary-btn studio-new" onClick={props.onFindJobs}>
          Find another job <ArrowRight size={15}/>
        </button>
      </aside>
      {selected ? <div className="studio-editor">
        <div className="studio-editor-head">
          <div>
            <span className="section-kicker">APPLICATION FOR</span>
            <h3>{selected.role_title}</h3><p>{selected.company}</p>
            {selected.status === "provider_acknowledged" ?
              <span className="state-pill good"><CheckCircle2 size={13}/>
                Employer system acknowledged your application</span> :
              selected.status === "self_reported_applied" ?
              <span className="state-pill waiting"><Clock3 size={13}/>
                User-reported applied · not employer-verified</span> :
              <span className={"state-pill " +
                (browserReceipt || employerAttempt?.previous_attempt_reserved ? "waiting" : "good")}>
                {browserReceipt ? "Confirmation observed · employer verification pending" :
                  employerAttempt?.previous_attempt_reserved
                    ? "Previous attempt · outcome needs review"
                    : "Editable draft · employer outcome unverified"}</span>}
          </div>
          {safePostingLink(selected.application_url) ? (
            <a href={safePostingLink(selected.application_url)} className="outline-btn compact"
              rel="noopener noreferrer" target="_blank">Employer site <ArrowUpRight size={15}/></a>
          ) : null}
        </div>
        <section className="studio-journey" aria-label="Your next steps for this application">
          <div className="studio-journey-header">
            <strong>One application · one next step</strong>
            <small>Private exact-job workspace · revision {selected.revision}</small>
          </div>
          {nextAction ? <div className={"studio-next-action state-" + nextAction.tone}
            aria-label="Application progress and next action" role="region">
            <div className="studio-next-action-copy">
              <span className="studio-next-action-state">{nextAction.statusLabel}</span>
              <strong>{nextAction.title}</strong>
              <p>{nextAction.detail}</p>
            </div>
            {nextAction.action.type === "save" ?
              <button type="button" className="navy-btn"
                disabled={busy || partnerBusy || !!browserReceipt || !!partnerReceipt ||
                  employerAttempt?.previous_attempt_reserved === true}
                onClick={() => void save()}><Save size={16} aria-hidden="true"/>
                {busy ? "Saving…" : nextAction.action.label}</button> :
              <a className="navy-btn" href={nextAction.action.target}>
                {nextAction.action.label} <ArrowRight size={16} aria-hidden="true"/>
              </a>}
          </div> : null}
          <ol>
            <li><span>1</span><div><strong>Review the CV & letter</strong>
              <small>Edit for this exact job and save your changes before using a document.</small></div></li>
            <li><span>2</span><div><strong>Complete the employer form</strong>
              <small>Use the employer link, supported reviewed browser help, or a separately authorized partner submission.</small></div></li>
            <li><span>3</span><div><strong>Confirm and track</strong>
              <small>Record the outcome. Only a verified employer acknowledgment counts as independently submitted.</small></div></li>
          </ol>
          <nav className="studio-journey-links" aria-label="Jump to application step">
            <a href="#smartploy-cv-review">Review CV</a>
            <a href="#smartploy-letter-review">Review letter</a>
            {selected.status === "draft" ?
              <a href="#smartploy-employer-step">Employer form options</a> : null}
            <a href="#smartploy-outcome-step">Record or verify outcome</a>
          </nav>
          <p className="studio-journey-boundary">
            Selecting Manual, Assisted or AutoApply never authorizes a send.
            The final employer action requires its own reviewed, allowed path.
          </p>
        </section>
        <div className="studio-info">
          <ShieldCheck size={18}/>
          <div><strong>Your content, your decision.</strong>
            <p>{selected.status === "provider_acknowledged"
                  ? "The authorized employer ATS confirmed creation of this application. Your approved CV/letter were sent. This is not a hiring decision."
                  : "SmartPloy has not independently verified submission of this draft. Review every CV and cover-letter claim before sending."}</p></div>
        </div>
        <ApplicationAgentCard
          key={props.expectedUserId + ":" + selected.workspace_id + ":" + selected.revision}
          workspaceId={selected.workspace_id}
          expectedUserId={props.expectedUserId}
          verifyAccount={verifyAccount}
        />
        <section className="studio-ai-card" aria-label="Optional local AI writing support">
          <div className="studio-ai-heading">
            <span className="studio-ai-icon"><Sparkles size={19}/></span>
            <div><strong>ObumAI local writing assistant</strong>
              <p>{aiStatus?.ready
                ? "Local model available · review-only suggestions from approved facts"
                : aiStatus?.configured
                  ? aiStatus.failure_category === "model_not_installed"
                    ? "Private Ollama is reachable, but the configured model is not installed"
                    : "Private Ollama endpoint is unavailable. Ask the operator to check its internal Docker bridge."
                  : "Local AI is not yet enabled on this server. The manual editor remains available."}</p>
            </div>
          </div>
          <button className="outline-btn studio-ai-trigger" type="button"
            disabled={!aiStatus?.ready || busy || aiBusy || dirty || selected.status !== "draft" ||
              !!browserReceipt || employerAttempt?.previous_attempt_reserved === true}
            onClick={() => void askLocalAI()}>
            <WandSparkles size={16}/> {aiBusy ? "Generating with the local model…" : "Suggest tailored wording"}
          </button>
          <p className="studio-ai-privacy">
            Explicit consent for each generation. Only the vacancy and approved profile facts
            reach the private model; no employer submission or external AI forwarding.
          </p>
          {aiSuggestion ? <div className="studio-ai-preview">
            <div className="studio-ai-preview-title">
              <strong>Unverified AI proposal · {aiSuggestion.model}</strong>
              <button className="navy-btn compact" type="button"
                onClick={() => void insertAISuggestion()}>Insert into editor <ArrowRight size={14}/></button>
            </div>
            <h4>{aiSuggestion.proposal.cv_headline}</h4>
            <p>{aiSuggestion.proposal.cv_summary}</p>
            <details><summary>Read generated cover letter</summary>
              <pre>{aiSuggestion.proposal.cover_letter}</pre></details>
            {aiSuggestion.proposal.highlights.length ? <details><summary>Evidence citations</summary>
              <ul>{aiSuggestion.proposal.highlights.map((row, index) =>
                <li key={index}>{row.text} <small>Evidence IDs: {row.evidence_fact_ids.join(", ")}</small></li>)}
              </ul></details> : null}
            {aiSuggestion.proposal.risks.length ? <div className="studio-ai-risks">
              <strong>Check before using</strong>
              <ul>{aiSuggestion.proposal.risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul>
            </div> : null}
          </div> : null}
        </section>
        <div className="studio-document" id="smartploy-cv-review">
          <div className="studio-document-head"><strong><FileText size={17}/> CV draft</strong><span>{cvText.length.toLocaleString()} / 30,000 characters</span></div>
          <textarea aria-label="Editable CV text" rows={15} maxLength={30000}
            readOnly={selected.status !== "draft" || !!browserReceipt ||
              employerAttempt?.previous_attempt_reserved === true} value={cvText}
            onChange={(event) => setCvText(event.target.value)}
            placeholder="Your reviewed CV content" />
          <small>Started from your uploaded CV, when available; otherwise only approved profile facts.</small>
          <div className="studio-export">
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "cv", "docx")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> Download CV · DOCX</a>
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "cv", "pdf")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> PDF</a>
          </div>
        </div>
        <div className="studio-document" id="smartploy-letter-review">
          <div className="studio-document-head"><strong><FileCheck2 size={17}/> Cover letter draft</strong><span>{letterText.length.toLocaleString()} / 10,000 characters</span></div>
          {selected.status === "draft" ? <div className="studio-letter-language" aria-label="Cover letter language">
            <span>Generate a complete letter from approved experience:</span>
            <button className="outline-btn compact" type="button"
              onClick={() => void redraftLetter("fi")}
              disabled={busy || aiBusy || letterBusy || !!browserReceipt ||
                !!partnerReceipt || !!employerAttempt?.previous_attempt_reserved}>
              {letterBusy ? "Preparing…" : "Finnish draft"}
            </button>
            <button className="outline-btn compact" type="button"
              onClick={() => void redraftLetter("en")}
              disabled={busy || aiBusy || letterBusy || !!browserReceipt ||
                !!partnerReceipt || !!employerAttempt?.previous_attempt_reserved}>
              {letterBusy ? "Preparing…" : "English draft"}
            </button>
          </div> : null}
          <textarea aria-label="Editable cover letter text" rows={13} maxLength={10000}
            readOnly={selected.status !== "draft" || !!browserReceipt ||
              employerAttempt?.previous_attempt_reserved === true} value={letterText}
            onChange={(event) => setLetterText(event.target.value)}
            placeholder="Your reviewed cover letter" />
          <small>New application drafts begin with real Finnish or English letter prose, not coaching placeholders. Only approved, job-matched facts are used. If your profile lacks a confirmed name or relevant experience, edit the letter or use a language button to see the missing-information report. Older saved drafts stay unchanged until you edit them. Review and save explicitly; no employer is contacted.</small>
          <div className="studio-export">
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "letter", "docx")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> Download letter · DOCX</a>
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "letter", "pdf")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> PDF</a>
          </div>
        </div>
        {selected.status === "draft" ? <section className="studio-handoff" id="smartploy-employer-step"
          aria-label="Browser application assistant">
          <div className="studio-handoff-header">
            <div><p className="section-kicker">EMPLOYER APPLICATION</p><h4>Fill the employer's form</h4>
              <p>Use the optional SmartPloy companion for reviewed contact details, ordinary answers and PDF assistance on supported Lever, Ashby and hosted Greenhouse forms. Greenhouse submission remains manual; Ashby requires separately authorized partner API rights and your fresh final approval.</p></div>
            <ExternalLink size={18} />
          </div>
          {employerAttempt?.previous_attempt_reserved ? (
            <div role="alert" aria-label="Reserved attempt reconciliation" className="studio-handoff-blockers">
              <strong>An attempt for this employer job is already reserved across devices.</strong>
              <p>Its outcome is {employerAttempt.state === "uncertain" ? "uncertain" : "unverified"}.
                Do not submit again or request a new browser packet.</p>
              <p>Check the employer page and confirmation email. If the companion produced
                a reference-bearing confirmation, import its observed receipt below FIRST.
                After importing it, you may confirm the outcome for this exact job.
                Without a matching receipt, leave the attempt awaiting review; SmartPloy never retries it.</p>
            </div>
          ) : (
            <p className="muted">
              {selectedPartner === "lever" && finalAction?.trusted_one_use_browser_redemption_available
                ? "For individually authorized Lever jobs, the browser companion can reserve a single " +
                  "server-checked attempt and click Submit once after you review the complete employer form. " +
                  "First record your CV review below, then verify it in the companion. " +
                  "You may still submit manually; an attempted click is not proof of acceptance."
                : "Automatic final submission is disabled here. You can prepare the reviewed employer " +
                  "form using the companion and submit manually on the employer's website."}
              {!employerAttempt ? " The server attempt status is currently unavailable." : ""}
            </p>
          )}
          {finalReview?.review_state === "stale" ? <div className="studio-handoff-blockers"
            role="alert">
            <strong>Your previous applicant review is outdated.</strong>
            <p>Approved contact details or application contents have changed.
              Cancel the old review and inspect the current CV, cover letter and
              approved contact details before recording a fresh review. Nothing
              was submitted to an employer.</p>
            <button className="outline-btn compact" type="button"
              disabled={reviewBusy} onClick={() => void cancelFinalReview()}>
              {reviewBusy ? "Cancelling…" : "Cancel outdated review"}
            </button>
          </div> : null}
          {handoff?.blockers.length ? <div className="studio-handoff-blockers">
            <strong>Before applying, complete:</strong>
            <ul>{handoff.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
          </div> : null}
          <div className="studio-handoff-actions">
            <button type="button" className="navy-btn"
              disabled={!handoff?.ready || dirty || busy || handoffBusy || !!browserReceipt ||
                employerAttempt?.previous_attempt_reserved === true}
              onClick={() => void copyBrowserPacket()}>
              <ClipboardCopy size={16}/> {handoffBusy ? "Preparing…" : "Copy approved autofill packet"}
            </button>
            <a className="outline-btn" href="/smartploy-apply-companion.zip"
              download="smartploy-apply-companion.zip"
              aria-label="Download Chrome companion ZIP from SmartPloy">
              <Download size={15}/> Download Chrome companion ZIP
            </a>
            <a className="outline-btn"
              href="https://github.com/galapoto/smartploy/blob/main/docs/BROWSER_APPLY_COMPANION.md"
              target="_blank" rel="noopener noreferrer">Installation instructions <ArrowUpRight size={15}/></a>
          </div>
          <p className="muted">
            Desktop Chrome or Chromium: download and extract the ZIP, open
            chrome://extensions, enable Developer mode and choose Load unpacked.
            Select the extracted folder containing manifest.json. The companion
            runs only when you click it; it does not submit jobs in the background.
            It is not a Chrome Web Store install and does not update automatically.
          </p>
          {handoffPacketText ? <div className="studio-packet-fallback">
            <label htmlFor="smartploy-browser-packet">Private packet for your browser companion</label>
            <textarea id="smartploy-browser-packet" readOnly rows={4}
              value={handoffPacketText} spellCheck={false}
              onFocus={(event) => event.currentTarget.select()}
              aria-label="Select and copy the private short-lived browser packet" />
            <p>Copied packets contain approved contact information. Never share them in chat or public issues.</p>
          </div> : null}
          {handoffPacketText ? <div className="studio-packet-fallback" aria-label="Exact application final review">
            <strong>Final review record · no application submitted</strong>
            <p className="muted">This records only your review of the exact CV PDF and letter for 10 minutes.
              It is not a browser permission, job application or employer receipt.</p>
            {finalReview?.review_recorded ? <>
              <p role="status">Review recorded until {new Date(finalReview.expires_at).toLocaleTimeString()}.
                Automatic employer submission remains unavailable.</p>
              <button type="button" className="outline-btn compact"
                disabled={reviewBusy} onClick={() => void cancelFinalReview()}>
                Cancel recorded review
              </button>
            </> : <button type="button" className="secondary-btn"
              disabled={reviewBusy || !finalReview || finalReview.review_state === "stale" ||
                !handoff?.ready || dirty ||
                employerAttempt?.previous_attempt_reserved === true}
              onClick={() => void recordFinalReview()}>
              {reviewBusy ? "Recording…" : "Record exact CV and job review (no submit)"}
            </button>}
            {!finalReview ? <p role="status">Durable review service unavailable. No authorization can be recorded.</p> : null}
          </div> : null}
          <div className="studio-packet-fallback" aria-label="Employer final-action permission">
            <strong>{selectedPartner === "lever" && finalAction?.trusted_one_use_browser_redemption_available
              ? "One-use reviewed employer final click"
              : "Automatic employer website click · currently unavailable"}</strong>
            {finalAction ? <>
              <p role="status">
                Independent employer automation rights: {finalAction.operator_permission_reviewed
                  ? "record reviewed" : "not attested"}.
                Current applicant review: {(finalReview?.review_recorded ??
                  finalAction.current_applicant_review_recorded) ? "recorded" : "pending"}.
              </p>
              <p className="muted">
                {finalAction.previous_employer_attempt_reserved
                  ? "A previous employer attempt exists and must be reconciled."
                  : selectedPartner === "lever" && finalAction.trusted_one_use_browser_redemption_available
                  ? "If the employer grants permission for this exact posting, review and fill the Lever form, " +
                    "then reserve ONE attempt from the signed-in SmartPloy tab using the companion. " +
                    "Return to the employer to perform the final click. No automatic retry."
                  : "One-use employer browser submission requires an operator-enabled deployment " +
                    "and independent per-job permission."}
              </p>
            </> : <p role="status">Policy verification unavailable. Automated final submission remains blocked.</p>}
            <p className="muted">This informational indicator never permits a browser click by
              itself: server review, employer rights, your explicit final decision and a one-use claim are required.</p>
          </div>
          {selectedPartner ? <>
          <div className="studio-packet-fallback" aria-label={selectedPartner === "ashby"
            ? "Official Ashby partner submission" : "Official Lever partner submission"}>
            <strong>Complete your reviewed job application through {
              selectedPartner === "ashby" ? "Ashby" : "Lever"
            }</strong>
            {partnerReceipt ? <>
              <p role="status">{partnerReceipt?.provider === "ashby" ? "Ashby" : "Lever"} acknowledged the application. Reference:
                <strong> {partnerReceipt.provider_application_id}</strong>.</p>
              <p className="muted">The employer's system confirmed creation of the application.
                This is not a hiring decision; do not submit the same job again.</p>
            </> : partnerReadiness?.partner_provider === selectedPartner &&
              partnerReadiness.partner_api_configured &&
                partnerReadiness.independent_partner_rights_reviewed &&
                selected && freshPartnerEvidence(partnerReadiness.review_evidence,selected) ? <>
              <p className="muted">This exact employer job has separately reviewed {
                selectedPartner === "ashby" ? "Ashby" : "Lever"
              } API
                permission. Review your CV and letter above, then record your review here.
                No extension, copied personal-data packet or clipboard is needed.</p>
              {!finalReview?.review_recorded ||
                  Date.parse(finalReview.expires_at) <= Date.now() ? <>
                <button type="button" className="secondary-btn"
                  disabled={reviewBusy || partnerBusy || !handoff?.ready || dirty ||
                    !finalReview || finalReview.review_state === "stale" ||
                    employerAttempt?.previous_attempt_reserved === true ||
                    !!browserReceipt}
                  onClick={() => void recordPartnerReview()}>
                  {reviewBusy ? "Recording review…" : "Record reviewed CV, letter and job (no submit)"}
                </button>
              </> : <>
                <p role="status">Your review was recorded; it does not send the application.
                  A separate final confirmation is required.</p>
                <button type="button" className="outline-btn compact"
                  disabled={reviewBusy || partnerBusy} onClick={() => void cancelFinalReview()}>
                  Cancel recorded review
                </button>
                {partnerReadiness.eligible_for_explicit_partner_submit ? <button
                  className="navy-btn" type="button"
                  disabled={partnerBusy || reviewBusy || !handoff?.ready || dirty ||
                    employerAttempt?.previous_attempt_reserved === true || !!browserReceipt}
                  onClick={() => void sendPartnerApplication()}>
                  {partnerBusy ? "Submitting once…" : "Submit reviewed application to authorized " +
                      (selectedPartner === "ashby" ? "Ashby" : "Lever") + " employer"}
                </button> : <p role="status">
                  Partner eligibility is not verified after review. No application may be sent.
                </p>}
              </>}
            </> : <p className="muted">
              {partnerReadiness?.prior_employer_attempt
                ? "An employer attempt already exists; contact support to reconcile. Do not retry."
                : "No authorized direct " +
                  (selectedPartner === "ashby" ? "Ashby" : "Lever") +
                  " submission is available for this job. " +
                  "Use the browser companion and submit manually on the employer website."}
            </p>}
            {!partnerReadiness ? <p role="status">Partner readiness unavailable. No employer transfer is permitted.</p> : null}
          </div>
          </> : <div className="studio-packet-fallback" aria-label="Manual-only employer application">
            <strong>Finish this job application on the employer website</strong>
            <p className="muted">SmartPloy has no direct employer API submission for this job.
              Review your prepared CV and letter, use browser assistance only if the
              employer form is supported, and personally complete its application form.
              Save the confirmation here afterward. SmartPloy did not send anything.</p>
          </div>}
          <p className="studio-handoff-disclaimer">
            Browser-only, 15-minute packet. Upload your CV on the employer's page and answer
            any employer-specific questions. Final submission needs a separate approval and
            must be verified from the employer's confirmation; preparing the packet is not applying.
          </p>
        </section> : null}
        {selected.status === "provider_acknowledged" ? <section
          className="studio-receipt" aria-label={partnerReceipt?.provider === "ashby"
            ? "Official Ashby provider acknowledgement" : partnerReceipt?.provider === "lever"
            ? "Official Lever provider acknowledgement" : "Employer provider acknowledgement"}>
          <div className="studio-receipt-header">
            <strong><CheckCircle2 size={16}/> {
              partnerReceipt?.provider === "ashby" ? "Ashby" :
              partnerReceipt?.provider === "lever" ? "Lever" : "Employer provider"
            } received this application</strong>
            <span className="state-pill good">Provider acknowledged</span>
          </div>
          {partnerReceipt ? <p role="status">
            Employer application reference: <strong>{partnerReceipt.provider_application_id}</strong>
          </p> : <p>Provider reference is stored in your private SmartPloy account. Refresh to retrieve it.</p>}
          <p className="muted">Your application was created at the employer's ATS.
            This confirms submission, not acceptance for the position or a hiring decision.</p>
        </section> : null}
        {selected.status !== "provider_acknowledged" ? <section
          className="studio-receipt" id="smartploy-observed-evidence"
          aria-label="Browser-observed employer confirmation">
          <div className="studio-receipt-header">
            <strong><CheckCircle2 size={16}/> Employer confirmation evidence</strong>
            <span className="state-pill waiting">Not independently verified</span>
          </div>
          {browserReceipt ? <div className="studio-receipt-record">
            <p>A confirmation was observed in your browser for this job. SmartPloy has not independently verified the employer's receipt.</p>
            <p><strong>Reference:</strong> {browserReceipt.reference}</p>
            <p><strong>Observed:</strong> {new Date(browserReceipt.observed_at).toLocaleString()}</p>
            <p><strong>Status:</strong> Browser-observed and awaiting your review</p>
          </div> : <>
            <p className="muted">After an approved Lever attempt or a manually submitted
              Lever, Ashby or hosted Greenhouse application, the companion may capture a visible, same-job,
              reference-bearing employer confirmation. Copy its private receipt packet
              and import it here. An attempted click or browser observation is never
              independently verified employer acknowledgment.</p>
            <p className="muted">If the employer shows no reference or redirects away from
              the exact job, keep its confirmation email and use I applied on employer site
              to record your own report.</p>
            <button className="outline-btn compact" type="button"
              onClick={() => setReceiptOpen((current) => !current)}
              disabled={selected.status !== "draft" || !!partnerReceipt}>
              {receiptOpen ? "Hide receipt import" : "Import observed receipt"}
            </button>
            {receiptOpen ? <div className="studio-receipt-import">
              <label htmlFor="browser-observed-receipt">Paste receipt from the companion</label>
              <textarea id="browser-observed-receipt" rows={5} maxLength={5000}
                value={receiptInput} onChange={(event) => setReceiptInput(event.target.value)}
                spellCheck={false} placeholder="Paste the private receipt JSON copied by the browser companion" />
              <button className="navy-btn compact" type="button"
                disabled={receiptBusy || receiptInput.length < 30}
                onClick={() => void onImportObservedReceipt()}>
                {receiptBusy ? "Checking…" : "Store observed confirmation"}
              </button>
            </div> : null}
          </>}
        </section> : null}
        <div className="studio-footer" id="smartploy-outcome-step">
          <span><LockKeyhole size={14}/> Private workspace · revision {selected.revision}</span>
          {selected.status === "draft" ? <div className="studio-actions">
            <button type="button" className="primary-btn" disabled={busy || !dirty || !!browserReceipt ||
                !!partnerReceipt || employerAttempt?.previous_attempt_reserved === true}
              onClick={() => void save()}><Save size={16}/>{busy ? "Working…" : "Save changes"}</button>
            <button type="button" className="navy-btn" disabled={busy ||
                !!partnerReceipt ||
                (employerAttempt?.previous_attempt_reserved === true && !browserReceipt)}
              onClick={() => void markApplied()}>
              {employerAttempt?.previous_attempt_reserved
                ? "Confirm outcome of previous attempt" : "I applied on employer site"}
              <CheckCircle2 size={16}/></button>
          </div> : selected.status === "provider_acknowledged" ?
            <p>{partnerReceipt?.provider === "ashby" ? "Ashby" :
              partnerReceipt?.provider === "lever" ? "Lever" : "Employer provider"} acknowledged your application{partnerReceipt ?
              " · Reference " + partnerReceipt.provider_application_id : ""}.
              Documents are locked to preserve the submitted version.</p> :
            <p>Self-reported applied {selected.self_reported_applied_at ? new Date(selected.self_reported_applied_at).toLocaleDateString() : ""}{selected.self_reported_reference ? " · " + selected.self_reported_reference : ""}</p>}
        </div>
        {nextDraft ? <div className="row-actions" aria-label="Continue application queue">
          <button type="button" className="outline-btn" aria-label="Next application"
            onClick={() => pick(nextDraft.workspace_id)}>
            Next application: {nextDraft.role_title} <ArrowRight size={16}/>
          </button>
          <small>Opens another saved draft only; nothing is sent.</small>
        </div> : null}
        <div className="studio-delete-row">
          <button type="button" className="text-btn studio-delete" disabled={busy} onClick={() => void remove()}>
            <Trash2 size={14}/> Delete this application workspace
          </button>
        </div>
      </div> : null}
    </div>}
  </section>;
}
