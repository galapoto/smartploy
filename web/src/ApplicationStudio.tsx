import { useCallback, useEffect, useMemo, useState } from "react";
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
  getBrowserReceipt, importBrowserReceipt
} from "./api";
import type { ApplicationWorkspace, LocalAIStatus, LocalAISuggestion, BrowserHandoffReadiness, BrowserObservedReceipt, BrowserReceiptImport } from "./types";

function safePostingLink(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
  } catch {
    return "";
  }
}

export default function ApplicationStudio(props: {
  focusId: string; onFindJobs: () => void;
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
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [handoffPacketText, setHandoffPacketText] = useState("");
  const [browserReceipt, setBrowserReceipt] = useState<BrowserObservedReceipt | null>(null);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [receiptInput, setReceiptInput] = useState("");
  const [receiptBusy, setReceiptBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const result = await getApplicationWorkspaces();
      setWorkspaces(result.workspaces);
      setSelectedId((current) => {
        const wanted = props.focusId || current;
        return result.workspaces.some((item) => item.workspace_id === wanted)
          ? wanted : (result.workspaces[0]?.workspace_id || "");
      });
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load your application drafts.");
    } finally { setLoading(false); }
  }, [props.focusId]);

  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    void getLocalAIStatus().then(setAIStatus).catch(() => setAIStatus(null));
  }, []);

  const selected = useMemo(
    () => workspaces.find((item) => item.workspace_id === selectedId) || null,
    [workspaces, selectedId]
  );
  useEffect(() => {
    setAISuggestion(null);
    setCvText(selected?.cv_text || "");
    setLetterText(selected?.cover_letter_text || "");
  }, [selected?.workspace_id, selected?.revision]);

  useEffect(() => {
    setHandoffPacketText("");
    if (!selected) { setHandoff(null); return; }
    let alive = true;
    setHandoff(null);
    void getBrowserHandoffReadiness(selected.workspace_id).then((result) => {
      if (alive) setHandoff(result);
    }).catch(() => {
      if (alive) setHandoff(null);
    });
    return () => { alive = false; };
  }, [selected?.workspace_id, selected?.revision]);

  useEffect(() => {
    setReceiptOpen(false);
    setReceiptInput("");
    setBrowserReceipt(null);
    if (!selected?.workspace_id) return;
    let alive = true;
    void getBrowserReceipt(selected.workspace_id).then((state) => {
      if (alive) setBrowserReceipt(state.receipt);
    }).catch(() => {
      if (alive) setBrowserReceipt(null);
    });
    return () => { alive = false; };
  }, [selected?.workspace_id]);

  const dirty = Boolean(selected && (
    cvText !== selected.cv_text || letterText !== selected.cover_letter_text
  ));

  function pick(id: string) {
    if (dirty && !window.confirm("Discard unsaved changes and open another draft?")) return;
    setSelectedId(id);
    setMessage("");
    setError("");
  }

  function updateItem(item: ApplicationWorkspace) {
    setWorkspaces((items) => items.map((before) => before.workspace_id === item.workspace_id ? item : before));
    setSelectedId(item.workspace_id);
  }

  async function save() {
    if (!selected || selected.status !== "draft") return;
    setBusy(true); setMessage(""); setError("");
    try {
      const result = await editApplicationWorkspace(
        selected.workspace_id, selected.revision, cvText, letterText
      );
      updateItem(result.workspace);
      setMessage("Your edits were saved. Downloaded documents will contain this version.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Draft could not be saved.");
    } finally { setBusy(false); }
  }

  async function askLocalAI() {
    if (!selected || dirty || selected.status !== "draft" || !aiStatus?.ready) return;
    const ok = window.confirm(
      "Send the job description and your approved profile facts to the configured " +
      "private local ObumAI/Ollama model? Your uploaded CV file, unapproved profile " +
      "facts, and employer applications will NOT be sent. The response is a draft " +
      "proposal only and must be reviewed before saving."
    );
    if (!ok) return;
    setAIBusy(true); setError(""); setMessage(""); setAISuggestion(null);
    try {
      const response = await requestLocalAISuggestions(selected.workspace_id, selected.revision);
      setAISuggestion(response.suggestion);
      setMessage("Local AI returned draft suggestions. Review them and choose whether to insert them.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Local AI is currently unavailable.");
    } finally { setAIBusy(false); }
  }

  function insertAISuggestion() {
    if (!selected || !aiSuggestion || selected.status !== "draft") return;
    const draft = aiSuggestion.proposal;
    if (!window.confirm(
      "Insert these AI suggestions into your editable CV and cover letter? " +
      "They may contain mistakes. Nothing is saved or sent until you review and click Save changes."
    )) return;
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
    if (!selected || dirty || !handoff?.ready || selected.status !== "draft") return;
    let origin = "the employer website";
    try { origin = new URL(selected.application_url).origin; } catch { /* disabled by API validation */ }
    if (!window.confirm(
      "Prepare a short-lived job-application packet for " + origin + "? " +
      "This copies your approved name and contact fields, and reviewed cover letter, " +
      "to your computer clipboard. Keep it private; you will paste it into the " +
      "optional SmartPloy browser companion. No form is filled or submitted by this action."
    )) return;
    setHandoffBusy(true); setError(""); setMessage("");
    try {
      const response = await createBrowserHandoffPacket(selected.workspace_id, selected.revision);
      const json = JSON.stringify(response.packet);
      setHandoffPacketText(json);
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(json);
          setMessage("Private packet copied. Open the employer posting and use the browser companion within 15 minutes. Review and attach CV before submitting.");
        } catch {
          setMessage("Your private packet is ready below. Select and copy it manually, then open the employer posting and browser companion.");
        }
      } else {
        setMessage("Your private packet is ready below. Select and copy it manually into the browser companion.");
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to copy the application packet.");
    } finally { setHandoffBusy(false); }
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
    setReceiptBusy(true); setError(""); setMessage("");
    try {
      const response = await importBrowserReceipt(selected.workspace_id, parsed);
      setBrowserReceipt(response.receipt);
      setReceiptOpen(false); setReceiptInput("");
      setMessage("Employer confirmation was recorded as browser-observed, not independently verified.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to store this browser receipt.");
    } finally { setReceiptBusy(false); }
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
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await markApplicationManuallySent(
        selected.workspace_id, selected.revision, reference
      );
      updateItem(result.workspace);
      setMessage("Recorded as personally reported applied, not independently verified by the employer.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to record this application.");
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!selected || !window.confirm(
      "Permanently delete this application workspace and its document text? Original CV and profile facts remain."
    )) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await deleteApplicationWorkspace(selected.workspace_id);
      const remaining = workspaces.filter((item) => item.workspace_id !== selected.workspace_id);
      setWorkspaces(remaining);
      setSelectedId(remaining[0]?.workspace_id || "");
      setMessage("Draft removed from SmartPloy.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to delete this draft.");
    } finally { setBusy(false); }
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
              <span className="state-pill good">Editable draft · not submitted</span>}
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
                  ? "Local model configured but not reachable or the model is not installed"
                  : "Local AI is not yet enabled on this server. The manual editor remains available."}</p>
            </div>
          </div>
          <button className="outline-btn studio-ai-trigger" type="button"
            disabled={!aiStatus?.ready || busy || aiBusy || dirty || selected.status !== "draft"}
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
                onClick={insertAISuggestion}>Insert into editor <ArrowRight size={14}/></button>
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
            readOnly={selected.status !== "draft"} value={cvText}
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
            readOnly={selected.status !== "draft"} value={letterText}
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
          {handoff?.blockers.length ? <div className="studio-handoff-blockers">
            <strong>Before applying, complete:</strong>
            <ul>{handoff.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
          </div> : null}
          <div className="studio-handoff-actions">
            <button type="button" className="navy-btn"
              disabled={!handoff?.ready || dirty || busy || handoffBusy}
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
            <button type="button" className="primary-btn" disabled={busy || !dirty}
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
