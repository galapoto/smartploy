import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, ArrowUpRight, CheckCircle2, FileText, Loader2, Search, UploadCloud,
  WandSparkles, Bot, ShieldCheck, CircleHelp, ExternalLink, RefreshCw
} from "lucide-react";
import { getCVJobMatches, getSession } from "./api";
import { safeExternalJobUrl } from "./lib";
import type {
  ApplicationAssistanceLevel, ApplicationFlowMode,
  CVDocument, CVJobMatches, SearchJobCard
} from "./types";

const MODE_INFO: Record<ApplicationFlowMode, { title: string; summary: string }> = {
  manual: {
    title: "Apply manually",
    summary: "We match your CV to jobs. You complete the employer application yourself.",
  },
  assisted: {
    title: "Apply with AI help",
    summary: "Choose whether to filter jobs, prepare a CV and letter, or get reviewed form assistance.",
  },
  automatic: {
    title: "AutoApply",
    summary: "Select jobs for automatic private preparation. Employer submission only works with authorized connectors; others wait for you.",
  },
};

export default function ApplicationJourney(props: {
  userId: string;
  cv: CVDocument;
  mode: ApplicationFlowMode;
  selectedJobKey: string;
  uploading: boolean;
  preparing: string;
  queueBusy: boolean;
  onMode: (mode: ApplicationFlowMode) => void;
  onUpload: () => void;
  onReviewCV: () => void;
  onFindJobs: () => void;
  onOpenApplications: () => void;
  onPrepare: (canonicalKey: string) => Promise<void>;
  onPrepareSelected: (canonicalKeys: string[]) => Promise<void>;
}) {
  const [results, setResults] = useState<CVJobMatches | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState("");
  const [showOther, setShowOther] = useState(false);
  const [assistance, setAssistance] = useState<ApplicationAssistanceLevel>("documents");
  const [selected, setSelected] = useState<string[]>([]);

  // No CV or profile contents are persisted in browser storage.
  // An account switch unmounts this keyed component in the parent.
  useEffect(() => {
    let active = true;
    if (!props.cv.present) {
      setResults(null);
      setLoading(false);
      return () => { active = false; };
    }
    setResults(null);
    setLoading(true);
    setError("");
    void (async () => {
      const data = await getCVJobMatches();
      const account = await getSession();
      if (!active) return;
      if (!account.authenticated || account.user_id !== props.userId ||
          !props.userId) {
        throw new Error("Your signed-in account changed. Reload before using private matches.");
      }
      setResults(data);
    })().catch((exc: unknown) => {
      if (!active) return;
      setError(exc instanceof Error ? exc.message : "Could not compare your CV with current jobs.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [props.cv.present, props.cv.sha256, props.userId, revision]);

  const jobs = useMemo(() => {
    const rows = [...(results?.recommended || []), ...(showOther ? results?.other_jobs || [] : [])];
    const query = filter.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      if (!query) return true;
      return [row.job.company, row.job.role_title, row.job.location]
        .join(" ").toLocaleLowerCase().includes(query);
    });
  }, [results, showOther, filter]);

  function toggleSelected(key: string) {
    setSelected((current) => current.includes(key)
      ? current.filter((row) => row !== key)
      : [...current, key].slice(0, 15));
  }

  async function prepareOne(key: string) {
    setError("");
    try { await props.onPrepare(key); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "Unable to open your draft."); }
  }

  async function queue() {
    if (!selected.length || props.queueBusy) return;
    setError("");
    try { await props.onPrepareSelected(selected); }
    catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not prepare the selected drafts.");
    }
  }

  function resultCard(row: SearchJobCard) {
    const job = row.job;
    const link = safeExternalJobUrl(job.application_url);
    const chosen = selected.includes(row.canonical_key);
    const isMatch = row.lane === "recommended";
    const matches = row.reasons.filter((reason) =>
      !reason.toLowerCase().includes("your stated skills")).slice(0, 2);
    return <article className={"flow-job" + (props.selectedJobKey === row.canonical_key ? " highlighted" : "")}
      key={row.canonical_key}>
      <div className="flow-job-heading">
        <div>
          <h3>{job.role_title}</h3>
          <p>{job.company} · {job.location || "Location not stated"}</p>
          <small>{isMatch ? "CV text match — qualifications not verified" :
            "Explore: weaker or uncertain CV alignment"}{job.source_attribution ? " · " + job.source_attribution : ""}</small>
        </div>
        {typeof row.preference_score === "number" ?
          <span className="quiet-chip">{row.preference_score}% CV-text alignment</span> :
          <span className="quiet-chip">Unranked</span>}
      </div>
      {matches.length > 0 ? <p className="flow-job-why">{matches.join(" · ")}</p> : null}
      <div className="flow-job-actions">
        {props.mode === "automatic" ? <label className="flow-select">
          <input type="checkbox" checked={chosen}
            onChange={() => toggleSelected(row.canonical_key)}
            disabled={!job.source_current || (!chosen && selected.length >= 15)} />
          {chosen ? "Selected" : "Select for preparation"}
        </label> : null}
        {link ? <a className="outline-btn compact" href={link}
          target="_blank" rel="noopener noreferrer">
          {props.mode === "manual" || (props.mode === "assisted" && assistance === "filter")
            ? "Apply on employer site" : "View employer posting"}
          <ExternalLink size={14}/>
        </a> : <small>Original employer link unavailable</small>}
        {props.mode === "manual" ? <button className="navy-btn compact" type="button"
          disabled={props.preparing === row.canonical_key}
          onClick={() => void prepareOne(row.canonical_key)}>
          {props.preparing === row.canonical_key ? "Saving…" : "Save application draft"}
          <ArrowRight size={14}/>
        </button> : null}
        {props.mode === "assisted" && assistance !== "filter" ? <button
          className="navy-btn compact" type="button"
          disabled={props.preparing === row.canonical_key}
          onClick={() => void prepareOne(row.canonical_key)}>
          {props.preparing === row.canonical_key ? "Opening…" : "Prepare CV & application"}
          <ArrowRight size={14}/>
        </button> : null}
      </div>
    </article>;
  }

  return <div className="application-flow stacked" aria-label="Guided application journey">
    <section className="panel flow-intro">
      <div className="panel-heading"><div>
        <p className="section-kicker">ONE SIMPLE APPLICATION JOURNEY</p>
        <h2>Upload your CV. Choose a job. Apply.</h2>
        <p>SmartPloy handles the discovery and preparation steps you choose. You can switch methods any time.</p>
      </div></div>
      <ol className="flow-steps" aria-label="Application steps">
        <li className="done">1 · Choose mode</li>
        <li className={props.cv.present ? "done" : "current"}>2 · Upload CV</li>
        <li className={results?.cv_present ? "done" : ""}>3 · Select a job</li>
        <li>4 · Apply or review</li>
      </ol>
      <div className="flow-mode-grid" role="group" aria-label="How to apply">
        {(["manual", "assisted", "automatic"] as const).map((choice) => {
          const Icon = choice === "manual" ? FileText : choice === "assisted" ? WandSparkles : Bot;
          return <button type="button" key={choice}
            className={"flow-mode" + (props.mode === choice ? " selected" : "")}
            aria-pressed={props.mode === choice} onClick={() => props.onMode(choice)}>
            <Icon size={22} aria-hidden="true" />
            <strong>{MODE_INFO[choice].title}</strong>
            <small>{MODE_INFO[choice].summary}</small>
          </button>;
        })}
      </div>
      {props.mode === "assisted" ? <fieldset className="flow-assistance">
        <legend>How much help do you want?</legend>
        {([
          ["filter", "Filter jobs only"],
          ["documents", "Match + tailored documents"],
          ["full", "Help fill supported forms"],
        ] as const).map(([value,label]) =>
          <label key={value}><input type="radio" name="assist-level" value={value}
            checked={assistance === value} onChange={() => setAssistance(value)}/>{label}</label>)}
        <p>Form filling is currently available only through the reviewed browser companion on supported employer pages. Final browser submission remains manual.</p>
      </fieldset> : null}
      {props.mode === "automatic" ? <div className="flow-boundary" role="note">
        <ShieldCheck size={20} aria-hidden="true"/>
        <p><strong>AutoApply preparation is available.</strong> Select vacancies below to create private drafts.
          Fully automated employer submission is not yet available for arbitrary websites.
          A missing employer authorization or uncertain form goes to review—never falsely to “Submitted”.</p>
      </div> : null}
    </section>

    <section className="panel flow-cv">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 2 OF 4</p>
        <h2>Your CV</h2>
        <p>One CV for searching and application preparation. PDF or DOCX up to 5 MB.</p>
      </div></div>
      {props.cv.present ? <div className="flow-uploaded">
        <CheckCircle2 size={23} aria-hidden="true"/>
        <div><strong>{props.cv.filename || "Your CV"} is ready</strong>
          <small>Text extracted locally. Matching does not approve your qualifications or send CV details to employers.</small></div>
      </div> : <p className="flow-instruction">Start here: upload a CV and SmartPloy will automatically find matching current vacancies from its database.</p>}
      <div className="row-actions">
        <button className="primary-btn" type="button" disabled={props.uploading} onClick={props.onUpload}>
          {props.uploading ? <Loader2 size={16} className="rotate"/> : <UploadCloud size={16}/>}
          {props.uploading ? "Uploading and reading your CV…" :
            props.cv.present ? "Replace CV" : "Upload CV & find jobs"}
        </button>
        {props.cv.present ? <button className="outline-btn" type="button" onClick={props.onReviewCV}>
          Review CV text & facts <ArrowRight size={16}/>
        </button> : null}
      </div>
    </section>

    <section className="panel flow-matches">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 3 OF 4</p><h2>Jobs from your CV</h2>
        <p>These are current jobs in SmartPloy's own database, not web results invented for your CV.</p>
      </div></div>
      {!props.cv.present ? <div className="empty-state">
        <UploadCloud size={28}/><h3>Your matching jobs appear here</h3>
        <p>Upload your CV above to continue. If you just want to browse, use Find Jobs without uploading anything.</p>
        <button className="secondary-btn" type="button" onClick={props.onFindJobs}>Browse all jobs <ArrowRight size={16}/></button>
      </div> : loading ? <p className="muted" role="status">
        <Loader2 size={16} className="rotate"/> Comparing your CV with current vacancies…
      </p> : error ? <div role="alert" className="flow-error">{error}
        <button className="outline-btn compact" type="button" onClick={() => setRevision(n => n+1)}>
          Retry matching <RefreshCw size={14}/>
        </button>
      </div> : results ? <>
        {results.match_mode === "no_recognized_cv_signals" ?
          <p className="flow-boundary" role="status">Your CV was imported, but clear job-search cues were not found. All current jobs are available below as unranked options; this is not a qualification match.</p> :
          <p className="flow-match-count" role="status"><strong>{results.recommended_count} CV-text matches</strong>
            {" · " + results.current_jobs_count + " current jobs in database"}. Results are suggestions, not confirmed eligibility.</p>}
        {results.detected_roles.length > 0 || results.detected_topics.length > 0 ?
          <p className="flow-signal-summary">Search cues detected in CV: {[...results.detected_roles, ...results.detected_topics].slice(0,10).join(", ")}.
            <span> Review these before applying; the upload did not approve them as profile facts.</span></p> : null}
        <div className="flow-filter">
          <label><Search size={17} aria-hidden="true"/>
            <input aria-label="Filter matching jobs" type="search" value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Job title, employer or location"/>
          </label>
          <button className="outline-btn compact" type="button" onClick={() => setShowOther(current => !current)}>
            {showOther ? "Hide other jobs" : "Include other current jobs (" + results.other_jobs.length + ")"}
          </button>
        </div>
        {jobs.length ? <div className="flow-job-list">{jobs.slice(0,80).map(resultCard)}</div> :
          <div className="empty-state"><CircleHelp size={27}/><h3>No jobs match these filters</h3>
            <p>Include other current jobs, remove the text filter or check again after source refresh.</p>
            <button className="secondary-btn" type="button" onClick={props.onFindJobs}>
              Browse all jobs <ArrowRight size={16}/>
            </button></div>}
        {props.mode === "automatic" ? <div className="flow-queue">
          <strong>{selected.length} of 15 vacancies selected</strong>
          <p>Selection prepares saved documents one job at a time. It does not send applications to employers.</p>
          <button className="primary-btn" type="button" disabled={!selected.length || props.queueBusy}
            onClick={() => void queue()}>
            {props.queueBusy ? "Preparing selected drafts…" : "Prepare selected applications"}
            <ArrowRight size={16}/>
          </button>
        </div> : null}
      </> : null}
    </section>
    <section className="panel flow-next">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 4 OF 4</p><h2>Continue your applications</h2>
        <p>Saved applications keep your CV, letter and status in one place. You can return to the next job at any time.</p>
      </div></div>
      <div className="row-actions">
        <button className="secondary-btn" type="button" onClick={props.onOpenApplications}>
          Open My applications <ArrowRight size={16}/>
        </button>
        <button className="outline-btn" type="button" onClick={props.onFindJobs}>
          Search all jobs <ArrowUpRight size={16}/>
        </button>
      </div>
    </section>
  </div>;
}
