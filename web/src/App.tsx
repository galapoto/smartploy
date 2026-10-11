import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Activity, ArrowRight, ArrowUpRight, BriefcaseBusiness, Check, CheckCircle2,
  ChevronRight, Clock3, Database, Download, FileCheck2, FileText, Globe2,
  LayoutDashboard, ListFilter, LockKeyhole, MapPin, Menu, Plus, RefreshCw,
  Search, Settings2, ShieldCheck, Sparkles, Target, Trash2, UploadCloud,
  WandSparkles, X, ChartNoAxesColumn, AlertCircle, type LucideIcon
} from "lucide-react";
import {
  addManualJob, approveFact, createFact, deleteCV, deleteFact, getApplications,
  getCV, getDashboard, getHealth, getJobs, getProfileFacts, getSession,
  startApplicationWorkspace, uploadCV
} from "./api";
import {
  filterBySector, formatState, queueLabel, relativeFreshness, scoreBand,
  sectorLabel, type DisplayMode, type SectorFilter
} from "./lib";
import ApplicationStudio from "./ApplicationStudio";
import type {
  ApplicationRecord, CandidateFact, CVDocument, Dashboard, HealthResponse,
  ManualJobPayload, RankingCard, SavedJob, SessionInfo
} from "./types";

type Page = "dashboard" | "jobs" | "applications" | "profile" | "tools" | "insights" | "sources" | "settings";
type MatchView = "top" | "possible";

const NAV: Array<{ id: Page; label: string; icon: LucideIcon }> = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "jobs", label: "Find jobs", icon: Search },
  { id: "applications", label: "My applications", icon: FileText },
  { id: "profile", label: "CV & profile", icon: FileCheck2 },
  { id: "tools", label: "AI tools", icon: Sparkles },
  { id: "insights", label: "Career insights", icon: ChartNoAxesColumn },
  { id: "sources", label: "Job sources", icon: Database },
  { id: "settings", label: "Settings", icon: Settings2 }
];

const FACT_TYPES: Array<{ value: string; label: string }> = [
  { value: "identity", label: "Full name" }, { value: "contact", label: "Contact" },
  { value: "email", label: "Email address" }, { value: "phone", label: "Phone number" },
  { value: "linkedin", label: "LinkedIn profile URL" }, { value: "github", label: "GitHub profile URL" },
  { value: "skill", label: "Skill" }, { value: "experience", label: "Experience" },
  { value: "education", label: "Education" }, { value: "language", label: "Language" },
  { value: "certification", label: "Certification" }, { value: "project", label: "Project" },
  { value: "location", label: "Location" }, { value: "work_authorization", label: "Work authorization" },
  { value: "domain", label: "Industry" }, { value: "preference", label: "Preference" }
];

function cx(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

function Empty(props: { title: string; description: string; action?: string; onAction?: () => void; icon?: LucideIcon }) {
  const Icon = props.icon ?? BriefcaseBusiness;
  return (
    <div className="empty-state">
      <span className="empty-art"><Icon size={27} strokeWidth={1.6} /></span>
      <h3>{props.title}</h3>
      <p>{props.description}</p>
      {props.action && props.onAction ? (
        <button className="secondary-btn" type="button" onClick={props.onAction}>{props.action} <ArrowRight size={15} /></button>
      ) : null}
    </div>
  );
}

function Stat(props: { label: string; value: number; note: string; icon: LucideIcon; tone: string; onClick: () => void }) {
  const Icon = props.icon;
  return (
    <button className="stat-card" type="button" onClick={props.onClick}>
      <span className={cx("stat-icon", props.tone)}><Icon size={20} /></span>
      <span className="stat-copy"><span className="stat-label">{props.label}</span><strong>{props.value}</strong><small>{props.note}</small></span>
      <ChevronRight className="stat-arrow" size={17} />
    </button>
  );
}

function JobMatch(props: {
  item: RankingCard; mode: DisplayMode; expanded: boolean; busy: boolean;
  onToggle: () => void; onPrepare: () => void;
}) {
  const job = props.item.job;
  if (!job) return null;
  const color = scoreBand(props.item.fit_score);
  return (
    <article className="job-item">
      <div className="job-avatar" aria-hidden="true">{(job.company || "J").slice(0, 1).toUpperCase()}</div>
      <div className="job-details">
        <div className="job-title-line">
          <h3>{job.role_title}</h3>
          <span className={cx("score-chip", color)}><Target size={13} /> {props.item.fit_score}% fit</span>
        </div>
        <p className="job-byline"><strong>{job.company || "Employer not provided"}</strong>
          {job.location ? <span><MapPin size={13} /> {job.location}</span> : null}
          {job.work_mode ? <span>{job.work_mode}</span> : null}
        </p>
        <div className="job-meta">
          <span className="quiet-chip">{queueLabel(props.item.queue)}</span>
          <span>{sectorLabel(job.employer_sector)}</span>
          <span>{relativeFreshness(job.posted_at || job.first_seen_at)}</span>
          {job.source_attribution ? <span>· {job.source_attribution}</span> : null}
        </div>
        {props.mode === "heatmap" ? <div className={cx("match-meter", color)}><span style={{ width: String(Math.min(100, Math.max(0, props.item.fit_score))) + "%" }} /></div> : null}
        {props.expanded ? (
          <div className="job-expanded">
            <strong>Why it matches</strong>
            {props.item.matched_requirements.length ? <ul>{props.item.matched_requirements.map((text) => <li key={text}>{text}</li>)}</ul> : <p>No matched requirements recorded yet.</p>}
            {props.item.mandatory_gaps.length ? <p>Gaps: {props.item.mandatory_gaps.join("; ")}</p> : null}
            {job.source_ids.length ? <small>Sources: {job.source_ids.join(", ")}</small> : null}
          </div>
        ) : null}
      </div>
      <div className="job-buttons">
        <button type="button" className="text-btn" onClick={props.onToggle}>{props.expanded ? "Less" : "Match details"}</button>
        {job.application_url ? (
          <a className="outline-btn compact" href={job.application_url} target="_blank" rel="noopener noreferrer">
            Job posting <ArrowUpRight size={14} />
          </a>
        ) : null}
        <button className="navy-btn compact" type="button"
          disabled={props.busy || !job.source_current} onClick={props.onPrepare}>
          {props.busy ? "Opening…" : "Prepare documents"} <ArrowRight size={15}/>
        </button>
      </div>
    </article>
  );
}

function SavedJobCard(props: { item: SavedJob; busy: boolean; onPrepare: () => void }) {
  const job = props.item.job;
  return <article className="job-item">
    <div className="job-avatar" aria-hidden="true">{(job.company || "J").charAt(0).toUpperCase()}</div>
    <div className="job-details"><h3>{job.role_title}</h3><p className="job-byline"><strong>{job.company}</strong>{job.location ? <span><MapPin size={13} /> {job.location}</span> : null}</p>
      <div className="job-meta"><span className="quiet-chip">Awaiting evidence-based ranking</span><span>{props.item.source_ids.join(", ") || "Manual import"}</span></div>
    </div>
    <div className="job-buttons">
      {job.application_url ? <a className="outline-btn compact" href={job.application_url} target="_blank" rel="noopener noreferrer">Open job <ArrowUpRight size={14} /></a> : null}
      <button className="navy-btn compact" type="button" disabled={props.busy || !props.item.source_current} onClick={props.onPrepare}>
        {props.busy ? "Opening…" : "Prepare documents"} <ArrowRight size={15} />
      </button>
    </div>
  </article>;
}

function Tool(props: { title: string; description: string; icon: LucideIcon; ready: boolean; onClick: () => void }) {
  const Icon = props.icon;
  return <button className="tool-tile" type="button" onClick={props.onClick}>
    <span className="tool-icon"><Icon size={20} /></span>
    <span className="tool-copy"><strong>{props.title}</strong><small>{props.description}</small></span>
    <span className={cx("tool-indicator", props.ready ? "ready" : "pending")}>{props.ready ? "Open" : "Setup"}</span>
    <ChevronRight size={15} className="muted-icon" />
  </button>;
}

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [cv, setCV] = useState<CVDocument>({ present: false });
  const [facts, setFacts] = useState<CandidateFact[]>([]);
  const [jobs, setJobs] = useState<SavedJob[]>([]);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyCV, setBusyCV] = useState(false);
  const [busyFact, setBusyFact] = useState("");
  const [preparing, setPreparing] = useState("");
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState<SectorFilter>("all");
  const [view, setView] = useState<MatchView>("top");
  const [mode, setMode] = useState<DisplayMode>("heatmap");
  const [expandedJob, setExpandedJob] = useState("");
  const [cvPreview, setCVPreview] = useState(false);
  const [jobDialog, setJobDialog] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [newFactType, setNewFactType] = useState("skill");
  const [newFactValue, setNewFactValue] = useState("");
  const [confirmFact, setConfirmFact] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const [jobForm, setJobForm] = useState<ManualJobPayload>({
    company: "", role_title: "", location: "", description: "", application_url: ""
  });
  const uploadRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true); else setLoading(true);
    try {
      const [board, apps, ready, savedCV, profile, savedJobs, who] = await Promise.all([
        getDashboard(), getApplications(), getHealth(), getCV(), getProfileFacts(), getJobs(), getSession()
      ]);
      setDashboard(board); setApplications(apps.applications); setHealth(ready);
      setCV(savedCV); setFacts(profile.facts); setJobs(savedJobs.jobs); setSession(who);
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to reach SmartPloy.");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(true); }, 60000);
    return () => window.clearInterval(timer);
  }, [load]);

  const navigate = (target: Page) => { setPage(target); setMobileNav(false); setNotice(""); };
  const onUploadClick = () => uploadRef.current?.click();

  async function onCVUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusyCV(true); setNotice("");
    try {
      const uploaded = await uploadCV(file);
      setCV(uploaded); setCVPreview(true); navigate("profile");
      setNotice("Your CV was uploaded privately. Review its text and confirm facts before matching.");
      await load(true);
    } catch (exc) {
      navigate("profile");
      setNotice(exc instanceof Error ? exc.message : "CV upload failed.");
    } finally { setBusyCV(false); }
  }

  async function onDeleteCV() {
    if (!window.confirm("Remove your uploaded CV? Approved profile facts will remain until you remove them separately.")) return;
    setBusyCV(true);
    try {
      await deleteCV(); setCV({ present: false }); setCVPreview(false);
      setNotice("Your uploaded CV has been removed.");
    } catch (exc) { setNotice(exc instanceof Error ? exc.message : "Unable to remove CV."); }
    finally { setBusyCV(false); }
  }

  async function onAddFact(event: FormEvent) {
    event.preventDefault();
    if (!newFactValue.trim()) return;
    setBusyFact("new");
    try {
      await createFact(newFactType, newFactValue.trim(), confirmFact);
      setNewFactValue(""); setConfirmFact(false);
      setNotice(confirmFact ? "Approved profile evidence saved." : "Fact saved for review.");
      await load(true);
    } catch (exc) { setNotice(exc instanceof Error ? exc.message : "Unable to save fact."); }
    finally { setBusyFact(""); }
  }

  async function onFactApproval(fact: CandidateFact) {
    setBusyFact(fact.fact_id);
    try {
      await approveFact(fact.fact_id, !fact.approved);
      await load(true);
    } catch (exc) { setNotice(exc instanceof Error ? exc.message : "Unable to update fact."); }
    finally { setBusyFact(""); }
  }

  async function onFactDelete(fact: CandidateFact) {
    if (!window.confirm("Permanently remove this profile fact?")) return;
    setBusyFact(fact.fact_id);
    try { await deleteFact(fact.fact_id); await load(true); }
    catch (exc) { setNotice(exc instanceof Error ? exc.message : "Unable to delete fact."); }
    finally { setBusyFact(""); }
  }

  async function onManualJob(event: FormEvent) {
    event.preventDefault();
    if (!jobForm.company.trim() || !jobForm.role_title.trim() || !jobForm.description.trim()) return;
    if (jobForm.application_url.trim()) {
      try {
        const url = new URL(jobForm.application_url);
        if (!["http:", "https:"].includes(url.protocol)) throw new Error("invalid protocol");
      } catch { setNotice("The job posting link must be a valid HTTP or HTTPS URL."); return; }
    }
    setManualBusy(true);
    try {
      const result = await addManualJob(jobForm);
      if (result.status !== "discovered") throw new Error("The job was not accepted: " + result.status);
      setJobDialog(false); setJobForm({ company: "", role_title: "", location: "", description: "", application_url: "" });
      setNotice("Job added. Add approved evidence to unlock personalised ranking.");
      navigate("jobs"); await load(true);
      setNotice("Job added. Add approved evidence to unlock personalised ranking.");
    } catch (exc) { setNotice(exc instanceof Error ? exc.message : "Unable to add job."); }
    finally { setManualBusy(false); }
  }

  async function onPrepare(canonicalKey: string) {
    setPreparing(canonicalKey);
    try {
      const response = await startApplicationWorkspace(canonicalKey);
      setSelectedWorkspaceId(response.workspace.workspace_id);
      navigate("applications");
      setNotice(response.created
        ? "Application documents are ready to edit. Review the draft before downloading or applying."
        : "Opened your existing private application documents.");
    } catch (exc) {
      const detail = exc instanceof Error ? exc.message : "Unable to create application documents.";
      if (/Upload a CV|approve profile facts|uploaded CV/i.test(detail)) navigate("profile");
      setNotice(detail);
    } finally { setPreparing(""); }
  }

  const ranked = useMemo(() => {
    const items = view === "top" ? (dashboard?.top_matches || []) : (dashboard?.possible_matches || []);
    const query = search.toLocaleLowerCase().trim();
    return filterBySector(items, sector).filter((item) => !query || [
      item.job?.role_title, item.job?.company, item.job?.location
    ].some((field) => (field || "").toLocaleLowerCase().includes(query)));
  }, [dashboard, sector, view, search]);

  const unranked = useMemo(() => {
    const already = new Set([...(dashboard?.top_matches || []), ...(dashboard?.possible_matches || [])].map((x) => x.canonical_key));
    const query = search.toLocaleLowerCase().trim();
    return jobs.filter((item) => !already.has(item.canonical_key) && (
      !query || [item.job.role_title, item.job.company, item.job.location].some((field) => (field || "").toLocaleLowerCase().includes(query))
    ));
  }, [jobs, dashboard, search]);

  if (loading && !dashboard) return <div className="loading-screen"><img src="/smartploy-mark.png" alt="" /><span className="spinner" /><p>Preparing your workspace…</p></div>;
  if (!dashboard) return <div className="loading-screen"><img src="/smartploy-mark.png" alt="" /><h1>SmartPloy isn't available</h1><p>{error}</p><button className="primary-btn" onClick={() => void load()} type="button">Try again</button></div>;

  const approved = facts.filter((item) => item.approved);
  const skills = approved.filter((item) => item.fact_type === "skill");
  const sourcesReady = dashboard.source_health.some((s) => s.status === "healthy");
  const obumReady = Boolean(health?.obumai_configured);
  const selectedNav = NAV.find((item) => item.id === page);
  const avatar = (session?.email?.charAt(0) || "U").toUpperCase();
  const counts = dashboard.applications;
  const onTool = (name: string) => {
    if (name === "CV Tailor" || name === "Cover Letter") {
      if (!cv.present && !facts.some((item) => item.approved)) { navigate("profile"); setNotice("Upload your CV or approve your career evidence to begin."); }
      else { navigate("jobs"); setNotice("Choose a job and select Prepare documents. ObumAI-enhanced drafting is not connected yet."); }
    } else if (name === "Application prep") navigate("applications");
    else if (name === "Career insights") navigate("insights");
    else { navigate("tools"); setNotice("Interactive interview practice is planned, but not active yet."); }
  };

  const jobsSection = <section className="panel jobs-panel">
    <div className="panel-heading">
      <div><p className="section-kicker">OPPORTUNITY FINDER</p><h2>{page === "jobs" ? "Find opportunities" : "Latest opportunities for you"}</h2>
        <p>Real listings and evidence-based matches — no sample jobs.</p></div>
      <button className="text-link" type="button" onClick={() => navigate("jobs")}>View all jobs <ArrowRight size={15} /></button>
    </div>
    <div className="job-filter-bar">
      <div className="tabs" role="group" aria-label="Match list">
        <button type="button" className={view === "top" ? "active" : ""} onClick={() => setView("top")}>Top matches</button>
        <button type="button" className={view === "possible" ? "active" : ""} onClick={() => setView("possible")}>Possible matches</button>
      </div>
      <div className="filter-right">
        <select aria-label="Employer sector" value={sector} onChange={(event) => setSector(event.target.value as SectorFilter)}>
          <option value="all">All sectors</option><option value="public">Public</option><option value="private">Private</option><option value="unknown">Other</option>
        </select>
        <button type="button" className={cx("icon-btn", mode === "heatmap" && "selected")} aria-label="Toggle heatmap" onClick={() => setMode(mode === "heatmap" ? "percentage" : "heatmap")}><ListFilter size={18} /></button>
      </div>
    </div>
    <div className="job-list">
      {ranked.map((item) => <JobMatch
        key={item.canonical_key} item={item} mode={mode} expanded={expandedJob === item.canonical_key}
        busy={preparing === item.canonical_key}
        onToggle={() => setExpandedJob(expandedJob === item.canonical_key ? "" : item.canonical_key)}
        onPrepare={() => void onPrepare(item.canonical_key)}
      />)}
      {unranked.map((item) => <SavedJobCard key={item.canonical_key} item={item}
        busy={preparing === item.canonical_key} onPrepare={() => void onPrepare(item.canonical_key)} />)}
      {!ranked.length && !unranked.length ? (
        <Empty title={jobs.length ? "No matches for these filters" : "Your opportunity list is ready to grow"}
          description={jobs.length ? "Try clearing the search or changing the match filter. Add verified evidence to improve ranking." : "Live job sources aren't configured yet. Add a job manually to start preparing your profile while we connect verified Finnish sources."}
          icon={BriefcaseBusiness} action="Add a job" onAction={() => setJobDialog(true)} />
      ) : null}
    </div>
  </section>;

  const cvBlock = <section className="panel cv-panel">
    <div className="panel-heading"><div><p className="section-kicker">YOUR CAREER EVIDENCE</p><h2>Your CV</h2><p>Private, on this SmartPloy account.</p></div></div>
    {cv.present ? <div className="uploaded-file">
      <span className="file-icon"><FileText size={24} /></span>
      <div className="uploaded-file-name"><strong>{cv.filename}</strong><small><CheckCircle2 size={13} /> Uploaded · {Math.round((cv.size_bytes ?? 0) / 1024)} KB</small></div>
      <a className="icon-btn" title="Download CV" aria-label="Download your CV" href="/api/v1/profile/cv/download"><Download size={19} /></a>
    </div> : <div className="cv-no-file"><UploadCloud size={23} /><strong>No CV uploaded yet</strong><span>Upload a PDF or DOCX to create your private profile workspace.</span></div>}
    <div className="row-actions">
      <button className="primary-btn" type="button" onClick={onUploadClick} disabled={busyCV}><UploadCloud size={17} /> {busyCV ? "Uploading…" : cv.present ? "Replace CV" : "Upload CV"}</button>
      {cv.present ? <button className="outline-btn" type="button" onClick={() => setCVPreview(!cvPreview)}>{cvPreview ? "Hide preview" : "Review text"}</button> : null}
      {cv.present ? <button className="icon-btn danger" type="button" aria-label="Delete CV" title="Delete uploaded CV" onClick={() => void onDeleteCV()} disabled={busyCV}><Trash2 size={18} /></button> : null}
    </div>
    {cv.present && cvPreview ? <div className="cv-text-preview"><strong>Extracted text for your review</strong><p>Text is not added to your approved profile automatically.</p><pre>{cv.text_preview || "No preview available."}</pre></div> : null}
    <p className="privacy-note"><LockKeyhole size={14} /> Your CV stays in SmartPloy. It is not submitted to employers or sent to ObumAI automatically.</p>
  </section>;

  const factPanel = <section className="panel facts-panel">
    <div className="panel-heading"><div><p className="section-kicker">VERIFIED PROFILE</p><h2>Skills & experience</h2><p>Only facts you approve affect job matching and AI drafts.</p></div><span className="subtle-count">{approved.length} approved</span></div>
    {facts.length ? <div className="facts-list">{facts.map((fact) => (
      <div className="fact-row" key={fact.fact_id}>
        <div><span className="fact-type">{fact.fact_type.replaceAll("_", " ")}</span><strong>{fact.value}</strong><small>{fact.approved ? "Verified by you" : "Needs your review"}</small></div>
        <button className={cx("fact-toggle", fact.approved && "approved")} type="button" disabled={busyFact === fact.fact_id} onClick={() => void onFactApproval(fact)} title={fact.approved ? "Mark unapproved" : "Approve this fact"}>{fact.approved ? <><Check size={15} /> Approved</> : "Approve"}</button>
        <button className="icon-btn subtle" type="button" title="Delete profile fact" aria-label="Delete profile fact" disabled={busyFact === fact.fact_id} onClick={() => void onFactDelete(fact)}><Trash2 size={16} /></button>
      </div>
    ))}</div> : <p className="muted padding-note">You have no profile evidence yet. Add a confirmed skill, qualification, language, or experience below.</p>}
    <form className="fact-form" onSubmit={(event) => void onAddFact(event)}>
      <div className="fact-inputs">
        <label>Fact type<select value={newFactType} onChange={(event) => setNewFactType(event.target.value)}>{FACT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>What should SmartPloy know?<input type="text" maxLength={700} required placeholder="e.g. Python, Finnish B2, data analytics" value={newFactValue} onChange={(event) => setNewFactValue(event.target.value)} /></label>
      </div>
      <label className="check-confirm"><input type="checkbox" checked={confirmFact} onChange={(event) => setConfirmFact(event.target.checked)} /> I confirm this information is accurate and may be used for matching.</label>
      <button className="navy-btn" type="submit" disabled={busyFact === "new"}><Plus size={16} /> {busyFact === "new" ? "Saving…" : confirmFact ? "Save approved fact" : "Save for review"}</button>
    </form>
  </section>;

  const toolsPanel = <section className="panel tools-panel">
    <div className="panel-heading"><div><p className="section-kicker">YOUR WORKSPACE</p><h2>Career tools</h2><p>Practical tools built around your own evidence.</p></div></div>
    <div className="tool-grid">
      <Tool title="CV editor" description="Review and export a job-specific CV in PDF/DOCX" icon={FileText} ready={cv.present || approved.length > 0} onClick={() => onTool("CV Tailor")} />
      <Tool title="Cover letter editor" description="Edit and download a role-specific letter" icon={WandSparkles} ready={cv.present || approved.length > 0} onClick={() => onTool("Cover Letter")} />
      <Tool title="Application prep" description="Track and review draft packages" icon={FileCheck2} ready={true} onClick={() => onTool("Application prep")} />
      <Tool title="Interview prep" description="AI-assisted practice (planned)" icon={Sparkles} ready={false} onClick={() => onTool("Interview prep")} />
      <Tool title="Career insights" description="Explore your evidence and gaps" icon={ChartNoAxesColumn} ready={true} onClick={() => onTool("Career insights")} />
    </div>
    {!obumReady ? <div className="info-strip"><AlertCircle size={17} /> ObumAI service integration is not configured. AI generation tools stay unavailable until secure machine authentication is enabled.</div> : null}
  </section>;

  const sourcePanel = <section className="panel sources-panel">
    <div className="panel-heading"><div><p className="section-kicker">SOURCE MONITOR</p><h2>Job sources</h2><p>Actual ingestion status — not estimated job counts.</p></div><span className={cx("state-pill", sourcesReady ? "good" : "waiting")}>{sourcesReady ? "Receiving jobs" : "Not active"}</span></div>
    {dashboard.source_health.length ? <div className="source-list">{dashboard.source_health.map((item) =>
      <div className="source-row" key={item.source_id}><span className="source-emblem"><Globe2 size={18} /></span><div><strong>{item.source_id}</strong><small>{item.last_item_count} jobs at last poll · {item.last_success_at ? relativeFreshness(item.last_success_at) : "No successful poll yet"}</small></div><span className={cx("state-pill", item.status === "healthy" ? "good" : "waiting")}>{item.status}</span></div>
    )}</div> : <Empty title="No live sources connected" description="Job Market Finland, Kuntarekry and public ATS integrations require an approved configuration before polling. No fake job numbers are displayed." icon={Database} action="Add a job manually" onAction={() => setJobDialog(true)} />}
  </section>;

  const sidePanel = <aside className="dashboard-side">
    <section className="panel profile-summary">
      <div className="small-heading"><h3>Your profile</h3><button className="text-link" type="button" onClick={() => navigate("profile")}>Edit profile <ArrowRight size={14} /></button></div>
      {cv.present ? <div className="profile-document"><FileText size={23} /><div><strong>{cv.filename}</strong><small><CheckCircle2 size={13} /> CV uploaded</small></div><button type="button" className="icon-btn" onClick={() => navigate("profile")} aria-label="View CV"><ChevronRight size={18} /></button></div> :
      <button type="button" className="profile-upload-placeholder" onClick={onUploadClick}><UploadCloud size={20} /> Upload your CV to get started <ArrowRight size={16} /></button>}
      <h4>Approved skills</h4>
      <div className="skill-tags">{skills.length ? skills.slice(0, 8).map((fact) => <span key={fact.fact_id}>{fact.value}</span>) : <small>No verified skills yet</small>}{skills.length > 8 ? <span>+{skills.length - 8}</span> : null}</div>
      <div className="evidence-summary"><span className="evidence-count">{approved.length}</span><div><strong>approved profile facts</strong><small>Used for matching, never inferred without review.</small></div></div>
      <button className="text-link" type="button" onClick={() => navigate("profile")}>Review your evidence <ArrowRight size={14} /></button>
    </section>
    <section className="panel compact-tools">
      <div className="small-heading"><h3>Your tools</h3><button className="text-link" type="button" onClick={() => navigate("tools")}>View all <ArrowRight size={14} /></button></div>
      <Tool title="CV documents" description="Editable PDF/DOCX application CV" icon={FileText} ready={cv.present || approved.length > 0} onClick={() => onTool("CV Tailor")} />
      <Tool title="Cover letters" description="Prepare and review a letter" icon={WandSparkles} ready={cv.present || approved.length > 0} onClick={() => onTool("Cover Letter")} />
      <Tool title="Applications" description="Review your pipeline" icon={BriefcaseBusiness} ready={true} onClick={() => navigate("applications")} />
    </section>
    <section className="panel source-overview">
      <div className="small-heading"><h3>Source activity</h3><button className="text-link" type="button" onClick={() => navigate("sources")}>Details <ArrowRight size={14} /></button></div>
      <span className={cx("state-pill", sourcesReady ? "good" : "waiting")}>{sourcesReady ? "Active source data" : "Awaiting configuration"}</span>
      <p>{dashboard.source_health.length ? String(dashboard.source_health.length) + " source status records available." : "No Finnish job feeds have completed a poll yet."}</p>
      <button className="text-link" type="button" onClick={() => setJobDialog(true)}>Add a job yourself <ArrowRight size={14} /></button>
    </section>
  </aside>;

  return <div className="smartploy-app">
    <input ref={uploadRef} type="file" className="visually-hidden" aria-label="Select CV to upload" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void onCVUpload(event)} />
    <button className={cx("sidebar-scrim", mobileNav && "visible")} type="button" onClick={() => setMobileNav(false)} aria-label="Close navigation" />
    <aside className={cx("sidebar", mobileNav && "open")}>
      <button className="site-brand" type="button" onClick={() => navigate("dashboard")} aria-label="SmartPloy dashboard">
        <img src="/smartploy-mark.png" alt="SmartPloy mark" /><span><strong>SmartPloy</strong><small>Job intelligence for Finland</small></span>
      </button>
      <nav className="sidebar-nav" aria-label="Main navigation">
        <div className="nav-label">WORKSPACE</div>
        {NAV.slice(0, 6).map((item) => { const Icon = item.icon; return <button type="button" key={item.id} className={cx("nav-item", page === item.id && "active")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}><Icon size={19} strokeWidth={1.9} /><span>{item.label}</span></button>; })}
        <div className="nav-divider" />
        <div className="nav-label">MANAGE</div>
        {NAV.slice(6).map((item) => { const Icon = item.icon; return <button type="button" key={item.id} className={cx("nav-item", page === item.id && "active")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}><Icon size={19} strokeWidth={1.9} /><span>{item.label}</span></button>; })}
      </nav>
      <div className="sidebar-bottom"><span className="country-chip"><span className="flag-finland" aria-hidden="true" /> Finland</span><span className="session-profile"><span className="avatar">{avatar}</span><span><strong>{session?.email ? session.email.split("@")[0] : "Your workspace"}</strong><small>{session?.authenticated ? "Signed in" : "Private workspace"}</small></span></span></div>
    </aside>
    <div className="main-column">
      <header className="site-header">
        <button className="icon-btn menu-toggle" aria-label="Open menu" type="button" onClick={() => setMobileNav(!mobileNav)}><Menu size={21} /></button>
        <div className="header-search"><Search size={19} /><input type="search" value={search} onChange={(event) => { setSearch(event.target.value); if (event.target.value) setPage("jobs"); }} placeholder="Search jobs, companies or locations…" aria-label="Search jobs" /></div>
        <span className="header-country"><MapPin size={16} /> Finland</span>
        <div className="header-tools">
          <a className="obumai-brand" href="https://app.obumai.com/" target="_self" title="Open ObumAI"><img src="/obumai-mark.svg" alt="" /> <strong>ObumAI</strong></a>
          <span className={cx("connection-status", obumReady ? "connected" : "disconnected")}><span />{obumReady ? "Connected" : "Setup needed"}</span>
          <button className="icon-btn header-refresh" type="button" onClick={() => void load(true)} disabled={refreshing} aria-label="Refresh workspace"><RefreshCw size={19} className={refreshing ? "rotate" : ""} /></button>
          <span className="avatar header-avatar" title={session?.email || "Your account"}>{avatar}</span>
        </div>
      </header>
      <main className="content">
        {notice ? <div className="toast-notice" role="status"><Activity size={16} /><span>{notice}</span><button type="button" onClick={() => setNotice("")} aria-label="Dismiss notice"><X size={17} /></button></div> : null}
        {error ? <div className="toast-notice error" role="alert"><AlertCircle size={16} /><span>{error}</span><button type="button" onClick={() => void load()} aria-label="Retry"><RefreshCw size={17} /></button></div> : null}
        {page === "dashboard" ? <>
          <section className="welcome-banner">
            <div className="welcome-copy"><p className="section-kicker">YOUR NORDIC CAREER WORKSPACE</p><h1>Make your next move.<br /><em>With clarity.</em></h1><p>Discover Finnish opportunities, build a trusted career profile and prepare the next step with SmartPloy.</p></div>
            <img className="helsinki-art" src="/helsinki-skyline.svg" alt="" />
            <div className="hero-tag"><span className="flag-finland" aria-hidden="true" /> Built for the Finnish job market</div>
          </section>
          <div className="action-grid">
            <button type="button" className="action-card featured" onClick={onUploadClick}><span className="action-icon"><UploadCloud size={22} /></span><span><strong>{cv.present ? "Replace your CV" : "Upload your CV"}</strong><small>{cv.present ? "Update your career evidence" : "Start with your experience"}</small></span><ArrowRight size={18} /></button>
            <button type="button" className="action-card" onClick={() => { navigate("profile"); setNotice("LinkedIn account sync is not available yet. You can upload a CV or add your evidence directly."); }}><span className="action-icon"><BriefcaseBusiness size={21} /></span><span><strong>Build your profile</strong><small>Confirm skills and experience</small></span><ArrowRight size={18} /></button>
            <button type="button" className="action-card" onClick={() => void load(true)} disabled={refreshing}><span className="action-icon"><RefreshCw size={21} className={refreshing ? "rotate" : ""} /></span><span><strong>Refresh listings</strong><small>Check available job data</small></span><ArrowRight size={18} /></button>
            <button type="button" className="action-card" onClick={() => navigate("tools")}><span className="action-icon"><Sparkles size={21} /></span><span><strong>Open AI tools</strong><small>CV, letters & applications</small></span><ArrowRight size={18} /></button>
          </div>
          <div className="stats-grid">
            <Stat label="Top matches" value={dashboard.top_matches.length} note="Best evidence-based fit" icon={Target} tone="blue" onClick={() => { setView("top"); navigate("jobs"); }} />
            <Stat label="Possible matches" value={dashboard.possible_matches.length} note="Worth a closer look" icon={BriefcaseBusiness} tone="orange" onClick={() => { setView("possible"); navigate("jobs"); }} />
            <Stat label="Awaiting review" value={counts.awaiting_review} note="Drafts, not submitted" icon={Clock3} tone="violet" onClick={() => navigate("applications")} />
            <Stat label="Actually submitted" value={counts.actually_submitted} note="Evidence of submission" icon={CheckCircle2} tone="green" onClick={() => navigate("applications")} />
          </div>
          <div className="dashboard-grid"><div>{jobsSection}</div>{sidePanel}</div>
        </> : null}
        {page !== "dashboard" ? <>
          <div className="page-intro"><div><p className="section-kicker">SMARTPLOY / {selectedNav?.label.toUpperCase()}</p><h1>{selectedNav?.label}</h1><p>Personal, evidence-based career intelligence for Finland.</p></div>
            {page === "jobs" ? <button type="button" className="primary-btn" onClick={() => setJobDialog(true)}><Plus size={17} /> Add job</button> : null}
            {page === "profile" ? <button type="button" className="primary-btn" onClick={onUploadClick}><UploadCloud size={17} /> {cv.present ? "Replace CV" : "Upload CV"}</button> : null}
          </div>
          {page === "jobs" ? <div className="secondary-grid">{jobsSection}<aside>{sourcePanel}</aside></div> : null}
          {page === "profile" ? <div className="secondary-grid"><div className="stacked">{cvBlock}{factPanel}</div><aside>{sidePanel}</aside></div> : null}
          {page === "tools" ? <div className="secondary-grid">{toolsPanel}<aside>{cvBlock}</aside></div> : null}
          {page === "sources" ? <div className="secondary-grid">{sourcePanel}<aside><section className="panel"><h3>Continuous worker</h3><p className="muted">{dashboard.worker.ready ? "Worker available" : "Worker unavailable"} · {dashboard.worker.count} registered tasks</p>{dashboard.worker.tasks.map((task) => <div className="source-row" key={task.task_id}><span><strong>{formatState(task.task_kind)}</strong><small>{formatState(task.last_status)}</small></span></div>)}</section></aside></div> : null}
          {page === "applications" ? <div className="stacked">
            <ApplicationStudio focusId={selectedWorkspaceId} onFindJobs={() => navigate("jobs")} />
            <section className="panel"><div className="panel-heading"><div><p className="section-kicker">APPLICATION TRACKER</p><h2>Your application pipeline</h2><p>A preparation draft is never counted as submitted.</p></div><span className="subtle-count">{applications.length} records</span></div>
            {applications.length ? <div className="applications-list">{applications.map((item) => <div className="application-list-row" key={item.application_id}><FileText size={20} /><div><strong>{formatState(item.state)}</strong><small>Job {item.canonical_key} · {item.updated_at ? relativeFreshness(item.updated_at) : "Updated time unknown"}</small></div><span className={cx("state-pill", item.has_been_submitted ? "good" : "waiting")}>{item.has_been_submitted ? "Submitted" : "Not submitted"}</span></div>)}</div> :
              <Empty title="No applications yet" description="When you've reviewed a job and prepared an application, the draft will appear here. No submissions are claimed without external evidence." icon={FileCheck2} action="Find jobs" onAction={() => navigate("jobs")} />}
            </section></div> : null}
          {page === "insights" ? <div className="secondary-grid"><section className="panel insights-panel"><p className="section-kicker">PROFILE INSIGHTS</p><h2>Your evidence, at a glance</h2><p className="muted">These figures come from your own verified profile, not estimates.</p><div className="insight-numbers"><div><strong>{facts.length}</strong><span>Total facts</span></div><div><strong>{approved.length}</strong><span>Approved facts</span></div><div><strong>{dashboard.top_matches.length + dashboard.possible_matches.length}</strong><span>Ranked matches</span></div></div><button className="primary-btn" type="button" onClick={() => navigate("profile")}>Improve profile <ArrowRight size={16} /></button></section><aside>{sourcePanel}</aside></div> : null}
          {page === "settings" ? <div className="secondary-grid"><section className="panel settings-panel"><h2>Privacy and account</h2><p>Your CV and approved facts are scoped to your signed-in SmartPloy profile. No automatic job submission is enabled.</p><p><ShieldCheck size={17} /> Account access is protected with the configured identity provider.</p><p><LockKeyhole size={17} /> You control CV removal and fact approval.</p><button className="outline-btn" type="button" onClick={() => navigate("profile")}>Manage personal data <ArrowRight size={16} /></button></section><aside>{sourcePanel}</aside></div> : null}
        </> : null}
        <footer className="site-footer"><span>SmartPloy · Job intelligence for Finland</span><span>Powered by ObumAI · No automatic applications submitted</span></footer>
      </main>
    </div>
    {jobDialog ? <div className="modal-backdrop" role="presentation" onClick={() => setJobDialog(false)}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="add-job-title" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-heading"><div><p className="section-kicker">MANUAL IMPORT</p><h2 id="add-job-title">Add a job opportunity</h2><p>Save a job you've already found. It won't be submitted anywhere.</p></div><button className="icon-btn" type="button" onClick={() => setJobDialog(false)} aria-label="Close"><X size={21} /></button></div>
        <form className="dialog-form" onSubmit={(event) => void onManualJob(event)}>
          <label>Job title<input required maxLength={160} value={jobForm.role_title} onChange={(event) => setJobForm({ ...jobForm, role_title: event.target.value })} placeholder="e.g. Junior Data Analyst" /></label>
          <label>Company<input required maxLength={160} value={jobForm.company} onChange={(event) => setJobForm({ ...jobForm, company: event.target.value })} placeholder="Employer name" /></label>
          <label>Location<input maxLength={160} value={jobForm.location} onChange={(event) => setJobForm({ ...jobForm, location: event.target.value })} placeholder="e.g. Helsinki / Remote" /></label>
          <label>Job posting URL<input type="url" value={jobForm.application_url} onChange={(event) => setJobForm({ ...jobForm, application_url: event.target.value })} placeholder="https://..." /></label>
          <label>Description or key requirements<textarea required rows={5} maxLength={12000} value={jobForm.description} onChange={(event) => setJobForm({ ...jobForm, description: event.target.value })} placeholder="Paste the responsibilities and key requirements here." /></label>
          <button className="primary-btn" type="submit" disabled={manualBusy}><Plus size={17} /> {manualBusy ? "Saving…" : "Save job"}</button>
        </form>
      </div>
    </div> : null}
  </div>;
}
