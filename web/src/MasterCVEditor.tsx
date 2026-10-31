import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileText, History, Plus, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { getCVEditor, getSession } from "./api";
import type { CVDocument, CVEditorArchive, CVEditorDocument, CVEditorSaved } from "./types";

const HEADINGS = ["PROFILE", "EXPERIENCE", "EDUCATION", "SKILLS", "PROJECTS", "CERTIFICATIONS", "LANGUAGES"];
const MAX_CHARS = 30000;

export default function MasterCVEditor(props: {
  cv: CVDocument;
  expectedUserId: string;
  onSave: (text: string, currentSha256: string) => Promise<CVEditorSaved>;
  onSaved: (cv: CVDocument) => void;
}) {
  const { cv, expectedUserId, onSave, onSaved } = props;
  const [snapshot, setSnapshot] = useState<CVEditorDocument | null>(null);
  const [text, setText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const requestGeneration = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const verifyAccount = useCallback(async () => {
    const session = await getSession();
    if (!expectedUserId || !session.authenticated ||
        session.user_id !== expectedUserId) {
      throw new Error("Account verification changed. Reload your private CV.");
    }
  }, [expectedUserId]);

  const refresh = useCallback(async () => {
    const token = ++requestGeneration.current;
    setLoading(true); setError(""); setNotice("");
    try {
      await verifyAccount();
      const data = await getCVEditor();
      await verifyAccount();
      if (token !== requestGeneration.current) return;
      if (data.employer_actions_performed !== 0 ||
          data.approved_profile_facts_added !== 0 ||
          !/^(?:[0-9a-f]{64})?$/.test(data.sha256) ||
          !Array.isArray(data.history)) {
        throw new Error("Unsafe CV editor response received");
      }
      setSnapshot(data);
      setText(data.text);
      setOriginalText(data.text);
    } catch (exc) {
      if (token !== requestGeneration.current) return;
      // Don't keep showing private previous-account text on failure.
      setSnapshot(null); setText(""); setOriginalText("");
      setError(exc instanceof Error ? exc.message : "Unable to load your CV editor.");
    } finally {
      if (token === requestGeneration.current) setLoading(false);
    }
  }, [verifyAccount]);

  useEffect(() => {
    void refresh();
    return () => { requestGeneration.current += 1; };
  }, [refresh, cv.sha256]);

  const dirty = text !== originalText;
  const canSave = !!snapshot && !loading && !saving &&
    dirty && text.trim().length >= 20 && text.trim().length <= MAX_CHARS;

  function addHeading(heading: string) {
    if (loading || saving || !snapshot) return;
    if (!HEADINGS.includes(heading)) return;
    setText((current) => {
      const sep = current.trim() ? "\n\n" : "";
      return current.trimEnd() + sep + heading + "\n";
    });
    textareaRef.current?.focus();
  }

  async function save() {
    if (!canSave || !snapshot || inFlight.current) return;
    const start = snapshot;
    if (!window.confirm(
      "Save this text as your active SmartPloy CV? Your previous uploaded or " +
      "edited file will remain downloadable in the private version history. " +
      "No profile facts are approved and nothing is sent to an employer."
    )) return;
    inFlight.current = true;
    setSaving(true); setError(""); setNotice("");
    const token = ++requestGeneration.current;
    try {
      await verifyAccount();
      const response = await onSave(text, start.sha256);
      await verifyAccount();
      if (token !== requestGeneration.current) return;
      if (response.employer_actions_performed !== 0 ||
          response.approved_profile_facts_added !== 0 ||
          !response.cv.sha256 || !response.cv.present ||
          !Array.isArray(response.history)) {
        throw new Error("CV save response did not pass verification");
      }
      const fresh: CVEditorDocument = {
        present: true,
        sha256: response.cv.sha256,
        filename: response.cv.filename || "smartploy-master-cv.docx",
        text: text.trim().replace(/\r\n?/g, "\n"),
        created_by_editor: true,
        history: response.history,
        employer_actions_performed: 0,
        approved_profile_facts_added: 0,
      };
      setSnapshot(fresh);
      setText(fresh.text);
      setOriginalText(fresh.text);
      onSaved(response.cv);
      setNotice("Saved. Your active master CV is ready for matching, application documents and download.");
    } catch (exc) {
      if (token === requestGeneration.current) {
        setError(exc instanceof Error ? exc.message : "Could not save your CV.");
      }
    } finally {
      inFlight.current = false;
      if (token === requestGeneration.current) setSaving(false);
    }
  }

  const history: CVEditorArchive[] = snapshot?.history ?? [];
  return <section className="master-cv-editor panel" aria-label="Master CV editor">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">YOUR MASTER DOCUMENT</p>
        <h2>Create & edit your CV</h2>
        <p>Start from a blank page or edit the entire text of your uploaded CV. Save a new active version, without losing previous files.</p>
      </div>
    </div>
    {loading ? <p role="status">Loading your private CV editor…</p> : null}
    {error ? <p role="alert" className="master-cv-message error">{error}</p> : null}
    {snapshot && !loading ? <>
      <div className="master-cv-toolbar">
        <label htmlFor="master-cv-add-section">Add a section</label>
        <select id="master-cv-add-section" aria-label="Choose CV section to insert"
          defaultValue="" onChange={(event) => {
            if (event.target.value) addHeading(event.target.value);
            event.target.value = "";
          }}>
          <option value="">Choose section…</option>
          {HEADINGS.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <button className="outline-btn compact" type="button"
          onClick={() => { if (!dirty || window.confirm("Discard your unsaved CV edits?")) void refresh(); }}
          disabled={saving}>
          <RefreshCw size={15} /> Reload
        </button>
      </div>
      <div className="master-cv-columns">
        <div className="master-cv-edit">
          <label htmlFor="master-cv-text">Editable master CV text</label>
          <textarea id="master-cv-text" ref={textareaRef}
            value={text} onChange={(event) => setText(event.target.value)}
            rows={19} maxLength={MAX_CHARS} readOnly={saving}
            placeholder="Write your name, contact details, experience, education and skills. Insert section headings above as needed." />
          <div className="master-cv-metadata">
            <span>{text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters</span>
            <span>{dirty ? "Unsaved changes" : snapshot.present ? "Saved version" : "New document"}</span>
          </div>
        </div>
        <div className="master-cv-preview">
          <strong><FileText size={16} /> Live document preview</strong>
          <div className="master-cv-paper" aria-label="CV preview">
            <pre>{text || "Your CV will appear here as you write."}</pre>
          </div>
        </div>
      </div>
      <div className="master-cv-actions">
        <button type="button" className="primary-btn" disabled={!canSave}
          onClick={() => void save()}>
          <Save size={16} /> {saving ? "Saving…" : snapshot.present ? "Save updated CV" : "Create master CV"}
        </button>
        {snapshot.present && !dirty ? <>
          <a className="outline-btn compact" href="/api/v1/profile/cv/editor/download/pdf">
            <Download size={15} /> PDF
          </a>
          <a className="outline-btn compact" href="/api/v1/profile/cv/editor/download/docx">
            <Download size={15} /> DOCX
          </a>
        </> : null}
      </div>
      {notice ? <p className="master-cv-message" role="status">{notice}</p> : null}
      <p className="master-cv-privacy"><ShieldCheck size={15}/>
        The editor preserves the words you enter. It never invents qualifications, approves profile evidence or submits applications.
      </p>
      {history.length ? <details className="master-cv-history">
        <summary><History size={16}/> Previous CV versions ({history.length})</summary>
        <ul>{history.map((item) => (
          <li key={item.sha256}>
            <span>{item.filename} · {Math.round(item.size_bytes / 1024)} KB</span>
            <a href={"/api/v1/profile/cv/history/" + encodeURIComponent(item.sha256)}>
              <Download size={14}/> Download previous version
            </a>
          </li>
        ))}</ul>
      </details> : null}
      {!snapshot.present ? <p className="master-cv-starter">
        <Plus size={14}/> Start blank, insert section headings and write at least 20 characters to create your first CV.
      </p> : null}
    </> : null}
  </section>;
}
