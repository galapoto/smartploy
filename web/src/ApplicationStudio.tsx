import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowUpRight, BriefcaseBusiness, CheckCircle2, Clock3,
  Download, FileCheck2, FileText, LockKeyhole, RefreshCw, Save, ShieldCheck,
  Trash2, AlertCircle, Sparkles, WandSparkles, ClipboardCopy, ExternalLink
} from "lucide-react";
import {
  applicationDownloadUrl, deleteApplicationWorkspace, editApplicationWorkspace,
  getApplicationWorkspaces, markApplicationManuallySent,
  getLocalAIStatus, requestLocalAISuggestions,
  getBrowserHandoffReadiness, createBrowserHandoffPacket,
  getEmployerAttemptStatus, getEmployerReviewIntent,
  recordEmployerReviewIntent, cancelEmployerReviewIntent,
  getBrowserReceipt, importBrowserReceipt, getSession
} from "./api";
import type { ApplicationWorkspace, LocalAIStatus, LocalAISuggestion, BrowserHandoffReadiness, BrowserObservedReceipt, BrowserReceiptImport } from "./types";
import { safeExternalJobUrl } from "./lib";
import type { EmployerAttemptState, EmployerReviewIntentState } from "./api";

const ACCOUNT_CHANGED_NOTICE =
  "Your signed-in SmartPloy account changed or could not be verified. Reload SmartPloy to continue safely.";

class StudioAccountChanged extends Error {}
class StudioSelectionChanged extends Error {}

// A draft's identity is its workspace ID, revision, AND the viewer's
// selection epoch. Switching away and back must not resurrect late results.
type DraftTicket = { key: string; epoch: number };

const safePostingLink = safeExternalJobUrl;

export default function ApplicationStudio(props: {
  focusId: string; expectedUserId: string; expectedAuthSource: string; onFindJobs: () => void;
}) {
  const [workspaces, setWorkspaces] = useState<ApplicationWorkspace[]>([]);
  const [selectedId, setSelectedId] = useState(props.focusId);
  const [cvText, setCvText] = useState("");
  const [letterText, setLetterText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAIBusy] = useState(false);
  const [aiStatus, setAIStatus] = useState<LocalAIStatus | null>(null);
  const [aiSuggestion, setAISuggestion] = useState<LocalAISuggestion | null>(null);
  const [handoff, setHandoff] = useState<BrowserHandoffReadiness | null>(null);
  const [employerAttempt, setEmployerAttempt] = useState<EmployerAttemptState | null>(null);
  const [finalReview, setFinalReview] = useState<EmployerReviewIntentState | null>(null);
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

  const isCurrentDraft = useCallback((ticket: DraftTicket) =>
    mountedRef.current && !accountBlockedRef.current &&
    selectedDraftRef.current.key === ticket.key &&
    selectedDraftRef.current.epoch === ticket.epoch, []);

  const captureDraft = (item: ApplicationWorkspace): DraftTicket => ({
    key: JSON.stringify([item.workspace_id, item.revision]),
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
    setHandoff(null); setEmployerAttempt(null); setFinalReview(null); setHandoffPacketText("");
    setBrowserReceipt(null); setReceiptOpen(false); setReceiptInput("");
    setMessage(""); setError(ACCOUNT_CHANGED_NOTICE);
    setBusy(false); setAIBusy(false); setHandoffBusy(false); setReceiptBusy(false); setReviewBusy(false);
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
      setWorkspaces(result.workspaces);
      setSelectedId((current) => {
        const wanted = props.focusId || current;
        return result.workspaces.some((item) => item.workspace_id === wanted)
          ? wanted : (result.workspaces[0]?.workspace_id || "");
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
  // Clear draft-local editor content, receipt/packet previews AND pending
  // indicators before a different draft can paint. The old draft's promise
  // may still finish; its completion must never unlock the new draft.
  useLayoutEffect(() => {
    const key = selected ? JSON.stringify([selected.workspace_id, selected.revision]) : "";
    if (selectedDraftRef.current.key !== key) {
      selectedDraftRef.current = { key, epoch: selectedDraftRef.current.epoch + 1 };
      setBusy(false); setAIBusy(false); setHandoffBusy(false); setReceiptBusy(false); setReviewBusy(false);
      setAISuggestion(null);
      setCvText(selected?.cv_text || "");
      setLetterText(selected?.cover_letter_text || "");
      setHandoffPacketText(""); setFinalReview(null);
      setReceiptOpen(false); setReceiptInput("");
      setHandoff(null); setBrowserReceipt(null); setEmployerAttempt(null); setFinalReview(null);
    }
  }, [selected?.workspace_id, selected?.revision]);

  useEffect(() => {
    if (!selected?.workspace_id || accountBlockedRef.current) return;
    let alive = true;
    const workspaceId = selected.workspace_id;
    void (async () => {
      try {
        await verifyAccount();
        if (!alive || accountBlockedRef.current) return;
        // Three tenant-scoped reads, with exact identity recheck both before
        // and after. Never publish a stale cross-account server attempt.
        const [handoffResult, receiptResult, attemptResult, reviewResult] = await Promise.allSettled([
          getBrowserHandoffReadiness(workspaceId),
          getBrowserReceipt(workspaceId),
          getEmployerAttemptStatus(workspaceId),
          getEmployerReviewIntent(workspaceId),
        ]);
        if (!alive || accountBlockedRef.current) return;
        await verifyAccount();
        if (!alive || accountBlockedRef.current) return;
        setHandoff(handoffResult.status === "fulfilled" ? handoffResult.value : null);
        setBrowserReceipt(receiptResult.status === "fulfilled" ? receiptResult.value.receipt : null);
        setEmployerAttempt(attemptResult.status === "fulfilled" ? attemptResult.value : null);
        setFinalReview(reviewResult.status === "fulfilled" ? reviewResult.value : null);
      } catch {
        // verifyAccount clears private state and blocks the editor on any
        // missing or different session. Ordinary API failures show no data.
        if (alive && !accountBlockedRef.current) {
          setHandoff(null); setBrowserReceipt(null); setEmployerAttempt(null); setFinalReview(null);
        }
      }
    })();
    return () => { alive = false; };
  }, [selected?.workspace_id, selected?.revision, verifyAccount]);

  const dirty = Boolean(selected && (
    cvText !== selected.cv_text || letterText !== selected.cover_letter_text
  ));

  function pick(id: string) {
    if (dirty && !window.confirm("Discard unsaved changes and open another draft?")) return;
    if (id !== selectedId) ++selectedDraftRef.current.epoch;
    setSelectedId(id);
    setMessage("");
    setError("");
  }

  function updateItem(item: ApplicationWorkspace) {
    setWorkspaces((items) => items.map((before) => before.workspace_id === item.workspace_id ? item : before));
    setSelectedId(item.workspace_id);
  }

  async function save() {
    if (!selected || selected.status !== "draft" || browserReceipt) return;
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

  async function askLocalAI() {
    if (!selected || dirty || selected.status !== "draft" || browserReceipt || !aiStatus?.ready) return;
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
    if (!selected || !aiSuggestion || selected.status !== "draft" || browserReceipt) return;
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

  /** Records exact reviewed CV/letter, but never authorizes an employer submission. */
  async function recordFinalReview() {
    if (!selected || !handoffPacketText || dirty || !handoff?.ready ||
        !finalReview || employerAttempt?.previous_attempt_reserved ||
        reviewBusy || browserReceipt) return;
    let packet;
    try {
      packet = JSON.parse(handoffPacketText) as {
        workspace_id: string; revision: number; expires_at: string;
        document_sha256: string; cv_pdf_sha256: string;
      };
      if (packet.workspace_id !== selected.workspace_id ||
          packet.revision !== selected.revision ||
          Date.parse(packet.expires_at) <= Date.now() ||
          !/^[a-f0-9]{64}$/.test(packet.document_sha256) ||
          !/^[a-f0-9]{64}$/.test(packet.cv_pdf_sha256)) {
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
      const item = await runPrivateAction(
        () => recordEmployerReviewIntent(
          selected.workspace_id, selected.revision,
          packet.document_sha256, packet.cv_pdf_sha256, props.expectedUserId
        ), ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setFinalReview(item);
      setMessage("Review recorded temporarily. No application was sent and no browser authorization was issued.");
    } catch (exc) {
      reportActionError(exc, "Review was not recorded.");
    } finally { if (isCurrentDraft(ticket)) setReviewBusy(false); }
  }

  async function cancelFinalReview() {
    if (!selected || !finalReview?.review_recorded || reviewBusy) return;
    const ticket = captureDraft(selected);
    setReviewBusy(true); setError(""); setMessage("");
    try {
      const result = await runPrivateAction(
        () => cancelEmployerReviewIntent(selected.workspace_id, props.expectedUserId), ticket
      );
      if (!isCurrentDraft(ticket)) return;
      setFinalReview(result);
      setMessage("Review cancelled. No employer application was submitted.");
    } catch (exc) {
      reportActionError(exc, "Unable to cancel the review.");
    } finally { if (isCurrentDraft(ticket)) setReviewBusy(false); }
  }

  async function onImportObservedReceipt() {
    if (!selected || selected.status !== "draft" || browserReceipt) return;
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
    if (!selected || selected.status !== "draft") return;
    if (dirty) { setError("Save the document changes before updating its application status."); return; }
    if (!window.confirm(
      "Confirm that you personally submitted this application on the employer's website. " +
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
      "Permanently delete this application workspace and its document text? Original CV and profile facts remain."
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
    {workspaces.length === 0 ? (
      <div className="studio-empty">
        <div className="studio-empty-icon"><FileCheck2 size={25}/></div>
        <h3>No application drafts yet</h3>
        <p>Go to Find jobs, choose a vacancy, then select <strong>Prepare documents</strong>. You can edit and download a CV and cover letter without ObumAI service access.</p>
        <button type="button" className="primary-btn" onClick={props.onFindJobs}>Choose a job <ArrowRight size={16}/></button>
      </div>
    ) : <div className="studio-layout">
      <aside className="studio-list" aria-label="Your application drafts">
        <div className="studio-list-heading"><strong>My drafts</strong><span>{workspaces.length}</span></div>
        {workspaces.map((item) => <button
          key={item.workspace_id} type="button"
          className={"studio-list-item" + (selectedId === item.workspace_id ? " selected" : "")}
          onClick={() => pick(item.workspace_id)}
          aria-current={selectedId === item.workspace_id ? "true" : undefined}
        >
          <span className="studio-list-icon"><BriefcaseBusiness size={17}/></span>
          <span className="studio-list-copy"><strong>{item.role_title}</strong><small>{item.company}</small>
            <em>{item.status === "self_reported_applied" ? "Applied · self-reported" : "Draft · not submitted"}</em>
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
            {selected.status === "self_reported_applied" ?
              <span className="state-pill waiting"><Clock3 size={13}/> User-reported applied · not employer-verified</span> :
              <span className="state-pill good">{browserReceipt ?
                "Confirmation observed · employer verification pending" :
                "Editable draft · not submitted"}</span>}
          </div>
          {safePostingLink(selected.application_url) ? (
            <a href={safePostingLink(selected.application_url)} className="outline-btn compact"
              rel="noopener noreferrer" target="_blank">Employer site <ArrowUpRight size={15}/></a>
          ) : null}
        </div>
        <div className="studio-info">
          <ShieldCheck size={18}/>
          <div><strong>Your content, your decision.</strong>
            <p>SmartPloy has not sent this application to anyone. The starter cover letter contains prompts that you must replace with accurate, personal details.</p></div>
        </div>
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
            disabled={!aiStatus?.ready || busy || aiBusy || dirty || selected.status !== "draft" || !!browserReceipt}
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
        <div className="studio-document">
          <div className="studio-document-head"><strong><FileText size={17}/> CV draft</strong><span>{cvText.length.toLocaleString()} / 30,000 characters</span></div>
          <textarea aria-label="Editable CV text" rows={15} maxLength={30000}
            readOnly={selected.status !== "draft" || !!browserReceipt} value={cvText}
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
        <div className="studio-document">
          <div className="studio-document-head"><strong><FileCheck2 size={17}/> Cover letter draft</strong><span>{letterText.length.toLocaleString()} / 10,000 characters</span></div>
          <textarea aria-label="Editable cover letter text" rows={13} maxLength={10000}
            readOnly={selected.status !== "draft" || !!browserReceipt} value={letterText}
            onChange={(event) => setLetterText(event.target.value)}
            placeholder="Your reviewed cover letter" />
          <small>Edit the draft to include specific, accurate examples. Draft language is not an AI quality guarantee.</small>
          <div className="studio-export">
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "letter", "docx")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> Download letter · DOCX</a>
            <a href={dirty ? undefined : applicationDownloadUrl(selected.workspace_id, "letter", "pdf")}
              className={"outline-btn compact" + (dirty ? " disabled" : "")}
              aria-disabled={dirty}><Download size={15}/> PDF</a>
          </div>
        </div>
        {selected.status === "draft" ? <section className="studio-handoff" aria-label="Browser application assistant">
          <div className="studio-handoff-header">
            <div><p className="section-kicker">EMPLOYER APPLICATION</p><h4>Fill the employer's form</h4>
              <p>Use the optional SmartPloy browser companion to fill approved contact fields on this specific job's website.</p></div>
            <ExternalLink size={18} />
          </div>
          {employerAttempt?.previous_attempt_reserved ? (
            <p role="alert" className="studio-handoff-blockers">
              An attempt for this employer job is already reserved across devices. Its outcome is
              {employerAttempt.state === "uncertain" ? " uncertain" : " unverified"}.
              Do not start another application; reconcile the employer result first.
            </p>
          ) : (
            <p className="muted">
              Automatic final submission is disabled until the companion can consume an
              authenticated one-time cross-device server claim. You can still prepare a reviewed
              form and submit manually on the employer website.
              {!employerAttempt ? " The server attempt status is currently unavailable." : ""}
            </p>
          )}
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
            <a className="outline-btn"
              href="https://github.com/galapoto/smartploy/blob/main/docs/BROWSER_APPLY_COMPANION.md"
              target="_blank" rel="noopener noreferrer">Browser companion instructions <ArrowUpRight size={15}/></a>
          </div>
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
              disabled={reviewBusy || !finalReview || !handoff?.ready || dirty ||
                employerAttempt?.previous_attempt_reserved === true}
              onClick={() => void recordFinalReview()}>
              {reviewBusy ? "Recording…" : "Record exact CV and job review (no submit)"}
            </button>}
            {!finalReview ? <p role="status">Durable review service unavailable. No authorization can be recorded.</p> : null}
          </div> : null}
          <p className="studio-handoff-disclaimer">
            Browser-only, 15-minute packet. Upload your CV on the employer's page and answer
            any employer-specific questions. Final submission needs a separate approval and
            must be verified from the employer's confirmation; preparing the packet is not applying.
          </p>
        </section> : null}
        <section className="studio-receipt" aria-label="Browser-observed employer confirmation">
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
            <p className="muted">If the companion displayed a reference-bearing employer confirmation,
              copy the private receipt packet and import it here. An attempt alone is not success.</p>
            <button className="outline-btn compact" type="button"
              onClick={() => setReceiptOpen((current) => !current)}
              disabled={selected.status !== "draft"}>
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
        </section>
        <div className="studio-footer">
          <span><LockKeyhole size={14}/> Private workspace · revision {selected.revision}</span>
          {selected.status === "draft" ? <div className="studio-actions">
            <button type="button" className="primary-btn" disabled={busy || !dirty || !!browserReceipt}
              onClick={() => void save()}><Save size={16}/>{busy ? "Working…" : "Save changes"}</button>
            <button type="button" className="navy-btn" disabled={busy}
              onClick={() => void markApplied()}>I applied on employer site <CheckCircle2 size={16}/></button>
          </div> : <p>Self-reported applied {selected.self_reported_applied_at ? new Date(selected.self_reported_applied_at).toLocaleDateString() : ""}{selected.self_reported_reference ? " · " + selected.self_reported_reference : ""}</p>}
        </div>
        <div className="studio-delete-row">
          <button type="button" className="text-btn studio-delete" disabled={busy} onClick={() => void remove()}>
            <Trash2 size={14}/> Delete this private draft
          </button>
        </div>
      </div> : null}
    </div>}
  </section>;
}
