import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ArrowRight, Bot, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";

import {
  getAshbyPartnerReadiness, getLeverPartnerReadiness, submitAuthorizedAutoApplyBatch,
} from "./api";
import type {
  AuthorizedAutoApplyItem, AuthorizedAutoApplyResult, LeverPartnerReadiness,
} from "./api";
import type { ApplicationWorkspace } from "./types";

const MAX_BATCH = 3;
const MAX_INSPECT = 12;

type Provider = "lever" | "ashby";
type BatchRow = {
  workspaceId: string;
  revision: number;
  applicationUrl: string;
  company: string;
  role: string;
  provider: Provider;
  state: "eligible" | "needs_review" | "not_authorized" | "unavailable";
  reason: string;
  item: AuthorizedAutoApplyItem | null;
};

type Props = {
  workspaces: ApplicationWorkspace[];
  expectedUserId: string;
  verifyAccount: () => Promise<void>;
  providerForUrl: (url: string) => Provider | null;
  hasUnsavedEdits: boolean;
  onOpen: (workspaceId: string) => void;
  onCompleted: (result: AuthorizedAutoApplyResult) => void;
};

/** Eligible means BOTH applicant intent and independently approved employer
 * API permission are current, in addition to a real saved CV/letter review.
 * No browser/LLM observation or client-side badge can give send authority.
 */
function eligibility(
  workspace: ApplicationWorkspace, provider: Provider,
  ready: LeverPartnerReadiness,
): BatchRow {
  const evidence = ready.review_evidence;
  const fresh = evidence !== null &&
    evidence.workspace_id === workspace.workspace_id &&
    evidence.revision === workspace.revision &&
    Date.parse(evidence.expires_at) > Date.now() + 20_000 &&
    /^[a-f0-9]{64}$/.test(evidence.document_sha256) &&
    /^[a-f0-9]{64}$/.test(evidence.cv_pdf_sha256) &&
    /^[a-f0-9]{64}$/.test(evidence.approved_fields_sha256) &&
    Number.isSafeInteger(evidence.cv_pdf_size) && evidence.cv_pdf_size >= 12;
  const isReady = workspace.status === "draft" && workspace.revision >= 2 &&
    ready.partner_provider === provider &&
    ready.partner_api_configured &&
    ready.independent_partner_rights_reviewed &&
    ready.current_applicant_review_recorded &&
    ready.current_document_and_posting_ready &&
    !ready.prior_employer_attempt && !ready.provider_acknowledged &&
    ready.eligible_for_explicit_partner_submit && fresh;
  return {
    workspaceId: workspace.workspace_id, revision: workspace.revision,
    applicationUrl: workspace.application_url,
    company: workspace.company, role: workspace.role_title, provider,
    state: isReady ? "eligible" :
      workspace.revision < 2 || (
        ready.partner_api_configured && ready.independent_partner_rights_reviewed &&
        !ready.current_applicant_review_recorded
      ) ? "needs_review" : "not_authorized",
    reason: isReady
      ? "Exact CV, letter, applicant review and employer API permission verified."
      : workspace.revision < 2
        ? "Open this job and confirm your CV and cover letter first."
        : !ready.partner_api_configured || !ready.independent_partner_rights_reviewed
          ? "No separately authorized employer API integration for this job."
          : ready.prior_employer_attempt || ready.provider_acknowledged
            ? "An employer application attempt already exists. Do not resend."
            : "Review expired or job/documents changed. Open the job to review again.",
    item: isReady && evidence ? {
      workspace_id: workspace.workspace_id,
      provider,
      expected_revision: workspace.revision,
      expected_document_sha256: evidence.document_sha256,
      expected_cv_pdf_sha256: evidence.cv_pdf_sha256,
      expected_fields_sha256: evidence.approved_fields_sha256,
      expected_cv_pdf_size: evidence.cv_pdf_size,
    } : null,
  };
}

export default function AuthorizedAutoApplyBatch(props: Props) {
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [reviewChecked, setReviewChecked] = useState(false);
  const [transferChecked, setTransferChecked] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const serial = useRef(0);
  const inFlight = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; ++serial.current; };
  }, []);
  // A different signed-in subject, document revision or employer posting
  // invalidates every old preview/checkbox. Nothing is stored persistently.
  const fingerprint = useMemo(() => props.workspaces.map((w) =>
    [w.workspace_id, w.revision, w.status, w.application_url].join("\u0000")
  ).join("\u0001"), [props.workspaces]);
  useEffect(() => {
    ++serial.current;
    setRows([]); setPicked([]); setReviewChecked(false);
    setTransferChecked(false); setError(""); setMessage("");
  }, [props.expectedUserId, fingerprint]);

  const candidates = useMemo(() =>
    props.workspaces.filter((w) => w.status === "draft" &&
      props.providerForUrl(w.application_url) !== null).slice(0, MAX_INSPECT),
    [props.workspaces, props.providerForUrl]);
  const eligible = rows.filter((row) => row.state === "eligible" && row.item);
  const chosen = eligible.filter((row) => picked.includes(row.workspaceId));
  const readyToSend = chosen.length > 0 && chosen.length <= MAX_BATCH &&
    reviewChecked && transferChecked && !props.hasUnsavedEdits &&
    !inspecting && !sending;

  async function inspect() {
    if (inFlight.current || props.hasUnsavedEdits) return;
    inFlight.current = true; setInspecting(true); setError(""); setMessage("");
    const ticket = ++serial.current;
    const current = () => alive.current && ticket === serial.current;
    try {
      await props.verifyAccount();
      const next: BatchRow[] = [];
      for (const workspace of candidates) {
        if (!current()) return;
        const provider = props.providerForUrl(workspace.application_url);
        if (!provider) continue;
        if (workspace.revision < 2) {
          next.push({
            workspaceId: workspace.workspace_id, revision: workspace.revision,
            applicationUrl: workspace.application_url, company: workspace.company,
            role: workspace.role_title, provider, state: "needs_review",
            reason: "Open this job and save your reviewed CV and letter first.", item: null,
          });
          continue;
        }
        try {
          const ready = await (provider === "ashby"
            ? getAshbyPartnerReadiness(workspace.workspace_id)
            : getLeverPartnerReadiness(workspace.workspace_id));
          await props.verifyAccount();
          if (!current()) return;
          next.push(eligibility(workspace, provider, ready));
        } catch {
          // A changed login is handled by verifyAccount's owner boundary,
          // not downgraded to an innocent-looking partner API error.
          await props.verifyAccount();
          if (!current()) return;
          next.push({
            workspaceId: workspace.workspace_id, revision: workspace.revision,
            applicationUrl: workspace.application_url, company: workspace.company,
            role: workspace.role_title, provider, state: "unavailable",
            reason: "Could not verify employer rights or current review. No send permitted.",
            item: null,
          });
        }
      }
      await props.verifyAccount();
      if (!current()) return;
      setRows(next); setPicked([]); setReviewChecked(false); setTransferChecked(false);
      if (!next.some((row) => row.state === "eligible")) {
        setMessage("No reviewed, authorized employer submissions are available. Assisted application is still available.");
      }
    } catch {
      if (current()) { setRows([]); setPicked([]); setError("Unable to verify your signed-in account or job permissions."); }
    } finally {
      inFlight.current = false;
      if (current()) setInspecting(false);
    }
  }

  function toggle(id: string, checked: boolean) {
    if (sending || inspecting) return;
    setPicked((current) => checked
      ? (current.includes(id) || current.length >= MAX_BATCH ? current : [...current, id])
      : current.filter((value) => value !== id));
    setReviewChecked(false); setTransferChecked(false);
    setError(""); setMessage("");
  }

  async function submit() {
    if (!readyToSend || inFlight.current) return;
    const items = chosen.map((row) => row.item).filter(
      (x): x is AuthorizedAutoApplyItem => x !== null
    );
    // Immutable before confirmation; never silently add a newly eligible job.
    if (items.length !== chosen.length || items.length > MAX_BATCH) return;
    const jobs = chosen.map((row) => row.role + " — " + row.company).join("\n");
    if (!window.confirm(
      "SUBMIT " + items.length + " REVIEWED JOB APPLICATION(S)?\n\n" + jobs +
      "\n\nI approve transferring the exact saved CV, cover letter and contact " +
      "details to each listed employer now. Every approved employer API call " +
      "will run once and cannot be automatically retried. An uncertain outcome " +
      "stops the remaining jobs. No unsupported jobs will be sent."
    )) return;
    inFlight.current = true;
    const ticket = ++serial.current;
    const current = () => alive.current && ticket === serial.current;
    setSending(true); setError(""); setMessage("");
    try {
      await props.verifyAccount();
      if (!current()) return;
      // Revalidate every review receipt/rights snapshot immediately before
      // submitting. The server performs the authoritative atomic checks again.
      for (const row of chosen) {
        const latest = await (row.provider === "ashby"
          ? getAshbyPartnerReadiness(row.workspaceId)
          : getLeverPartnerReadiness(row.workspaceId));
        await props.verifyAccount();
        if (!current()) return;
        const renewed = eligibility(
          props.workspaces.find((w) => w.workspace_id === row.workspaceId)!,
          row.provider, latest,
        );
        if (!renewed.item || JSON.stringify({
          ...renewed.item, expected_cv_pdf_size: renewed.item.expected_cv_pdf_size,
        }) !== JSON.stringify(row.item)) {
          throw new Error("A selected employer job or review changed. Check eligibility again.");
        }
      }
      await props.verifyAccount();
      if (!current()) return;
      const result = await submitAuthorizedAutoApplyBatch(items, props.expectedUserId);
      await props.verifyAccount();
      if (!current()) return;
      setPicked([]); setReviewChecked(false); setTransferChecked(false); setRows([]);
      setMessage(result.provider_acknowledged_count + " employer-acknowledged application(s). " +
        (result.stopped
          ? "Batch stopped: " + result.stop_reason.replaceAll("_", " ") +
            ". Do not retry an uncertain application; check your employer receipt."
          : "All selected jobs completed. No automatic retry is scheduled."));
      props.onCompleted(result);
    } catch (error) {
      if (!current()) return;
      try { await props.verifyAccount(); } catch { return; }
      if (current()) {
        setPicked([]); setReviewChecked(false); setTransferChecked(false);
        setRows([]); // A POST may already have reached the provider. Never offer repeat send.
        setError(error instanceof Error ? error.message :
          "An employer outcome may be uncertain. Check My applications; do not retry.");
      }
    } finally {
      inFlight.current = false;
      if (current()) setSending(false);
    }
  }

  return <section className="studio-automation" aria-label="Authorized AutoApply batch">
    <div className="studio-automation-header">
      <Bot size={22} aria-hidden="true" />
      <div><h3>AutoApply · authorized employer submissions</h3>
        <p>Send up to three already-reviewed applications with one explicit approval. SmartPloy uses real employer API acknowledgments, not draft counts. Only independently authorized Lever and Ashby postings qualify.</p></div>
    </div>
    {props.hasUnsavedEdits ? <p role="status" className="muted">
      Save or discard your current CV and letter edits before checking AutoApply.
    </p> : null}
    <div className="row-actions">
      <button type="button" className="outline-btn"
        onClick={() => void inspect()}
        disabled={sending || inspecting || props.hasUnsavedEdits}>
        <RefreshCw size={16} aria-hidden="true"/>
        {inspecting ? "Checking exact employer rights…" : "Check eligible reviewed jobs"}
      </button>
      <span className="muted">{candidates.length} supported ATS draft(s) loaded · maximum {MAX_BATCH} submissions per batch</span>
    </div>
    {error ? <p role="alert" className="studio-alert error"><AlertCircle size={16}/>{error}</p> : null}
    {message ? <p role="status" className="studio-alert"><CheckCircle2 size={16}/>{message}</p> : null}
    {rows.length > 0 ? <div className="studio-automation-cases" aria-label="Exact job eligibility results">
      {rows.map((row) => <div key={row.workspaceId} className="studio-automation-case">
        <label>
          <input type="checkbox" disabled={row.state !== "eligible" || sending ||
            (picked.length >= MAX_BATCH && !picked.includes(row.workspaceId))}
            checked={picked.includes(row.workspaceId)}
            onChange={(event) => toggle(row.workspaceId, event.target.checked)}/>
          <span><strong>{row.role}</strong> · {row.company} <small>({row.provider})</small></span>
        </label>
        <p>{row.state === "eligible" ? "Ready · " : "Blocked · "}{row.reason}</p>
        {row.state !== "eligible" ? <button type="button" className="text-btn"
          onClick={() => props.onOpen(row.workspaceId)}>Open application <ArrowRight size={14}/></button> : null}
      </div>)}
    </div> : null}
    {chosen.length > 0 ? <div className="studio-automation-approval">
      <p><ShieldCheck size={16}/> {chosen.length} exact employer job(s) selected.</p>
      <label><input type="checkbox" checked={reviewChecked}
        disabled={sending} onChange={(event) => setReviewChecked(event.target.checked)}/>
        I personally reviewed each selected job, employer form, saved CV and cover letter.</label>
      <label><input type="checkbox" checked={transferChecked}
        disabled={sending} onChange={(event) => setTransferChecked(event.target.checked)}/>
        I authorize one real application submission to each listed employer and understand uncertain results will not be retried.</label>
      <button type="button" className="navy-btn" disabled={!readyToSend}
        onClick={() => void submit()}>
        <ShieldCheck size={16}/>
        {sending ? "Submitting authorized applications…" :
          "Approve and AutoApply to " + chosen.length + " employer" + (chosen.length === 1 ? "" : "s")}
      </button>
    </div> : null}
    <p className="muted">No unattended background sends, no LinkedIn/Workday/CAPTCHA bypass and no implied employer consent. Jobs without documented employer API rights remain Assisted or Manual. A server-side one-shot claim is committed before each actual transfer.</p>
  </section>;
}
