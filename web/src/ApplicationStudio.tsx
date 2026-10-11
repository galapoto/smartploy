import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight, ArrowUpRight, BriefcaseBusiness, CheckCircle2, Clock3,
  Download, FileCheck2, FileText, LockKeyhole, RefreshCw, Save, ShieldCheck,
  Trash2, AlertCircle, Sparkles, WandSparkles
} from "lucide-react";
import {
  applicationDownloadUrl, deleteApplicationWorkspace, editApplicationWorkspace,
  getApplicationWorkspaces, markApplicationManuallySent,
  getLocalAIStatus, requestLocalAISuggestions
} from "./api";
import type { ApplicationWorkspace, LocalAIStatus, LocalAISuggestion } from "./types";

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
