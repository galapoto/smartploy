import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowUpRight, CheckCircle2, FileText, Loader2, Search, UploadCloud,
  WandSparkles, Bot, ShieldCheck, CircleHelp, ExternalLink, RefreshCw
} from "lucide-react";
import { getCVJobMatches, getSession } from "./api";
import { safeExternalJobUrl } from "./lib";
import type {
  ApplicationAssistanceLevel, ApplicationFlowMode,
  CVDocument, CVJobMatches, SearchJobCard, AutoApplyBatchOutcome
} from "./types";

const CV_PAGE_SIZE = 40;

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
    summary: "Select jobs to prepare private drafts and start one in-app agent per job. Employer submission still needs separate authorization.",
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
  onPrepareSelected: (
    canonicalKeys: string[], onProgress: (completed: number, total: number) => void
  ) => Promise<AutoApplyBatchOutcome>;
}) {
  const [results, setResults] = useState<CVJobMatches | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [paging, setPaging] = useState(false);
  const [pagingError, setPagingError] = useState("");
  const requestEpoch = useRef(0);
  // Show weaker but potentially important planner-adjacent vacancies by
  // default, clearly distinguished from direct CV-text matches.
  const [showOther, setShowOther] = useState(true);
  const [assistance, setAssistance] = useState<ApplicationAssistanceLevel>("documents");
  const [selected, setSelected] = useState<string[]>([]);
  const [batchResult, setBatchResult] = useState<AutoApplyBatchOutcome | null>(null);
  const [batchProgress, setBatchProgress] = useState<{ completed: number; total: number } | null>(null);
  const queueInFlight = useRef(false);
  // In-flight batch results cannot restore choices from a replaced CV or
  // different account, even if their server calls already completed.
  const queueScope = useRef("");
  queueScope.current = JSON.stringify([props.userId, props.cv.sha256 || "", props.cv.present]);

  // Debounce only the read-only query. Ranking and filtering happen on the
  // entire current job ledger, NOT just the rows already in this browser.
  useEffect(() => {
    const timer = window.setTimeout(() => setActiveQuery(filter.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [filter]);

  useEffect(() => {
    setSelected([]);
    setBatchResult(null);
    setBatchProgress(null);
  }, [props.cv.sha256, props.cv.present, props.userId]);

  // No CV, session tokens, or profile contents are persisted in browser storage.
  // An account switch unmounts this keyed component in the parent. Epoch and
  // authenticated-user checks also protect delayed page and search responses.
  useEffect(() => {
    let active = true;
    const epoch = ++requestEpoch.current;
    setPaging(false);
    setPagingError("");
    if (!props.cv.present) {
      setResults(null);
      setLoading(false);
      return () => { active = false; };
    }
    setResults(null);
    setLoading(true);
    setError("");
    void (async () => {
      const data = await getCVJobMatches({
        limit: CV_PAGE_SIZE, query: activeQuery,
        selected_job_key: props.selectedJobKey,
      });
      const account = await getSession();
      if (!active || epoch !== requestEpoch.current) return;
      if (!account.authenticated || account.user_id !== props.userId ||
          !props.userId) {
        throw new Error("Your signed-in account changed. Reload before using private matches.");
      }
      setResults(data);
    })().catch((exc: unknown) => {
      if (!active || epoch !== requestEpoch.current) return;
      setError(exc instanceof Error ? exc.message : "Could not compare your CV with current jobs.");
    }).finally(() => {
      if (active && epoch === requestEpoch.current) setLoading(false);
    });
    return () => { active = false; };
  }, [props.cv.present, props.cv.sha256, props.userId,
      props.selectedJobKey, activeQuery, revision]);

  useEffect(() => {
    if (props.selectedJobKey && results?.selected_job?.canonical_key === props.selectedJobKey) {
      setShowOther(true);
    } else if (props.selectedJobKey && results?.other_jobs.some((row) =>
      row.canonical_key === props.selectedJobKey)) {
      setShowOther(true);
    }
  }, [props.selectedJobKey, results]);

  const jobs = useMemo(() => {
    const rows = [
      ...(results?.selected_job ? [results.selected_job] : []),
      ...(results?.recommended || []),
      ...(showOther ? results?.other_jobs || [] : []),
    ];
    const seen = new Set<string>();
    return rows.filter((row) => {
      if (seen.has(row.canonical_key)) return false;
      seen.add(row.canonical_key);
      return true;
    });
  }, [results, showOther]);

  const hasMore = !!results && (
    results.recommended.length < results.recommended_count ||
    (showOther && results.other_jobs.length <
      (results.other_jobs_count ?? results.other_jobs.length))
  );

  async function loadMore() {
    if (!results || paging || !props.cv.present || !hasMore) return;
    const epoch = requestEpoch.current;
    setPaging(true);
    setPagingError("");
    try {
      const next = await getCVJobMatches({
        limit: CV_PAGE_SIZE,
        recommended_offset: results.recommended.length,
        other_offset: results.other_jobs.length,
        query: activeQuery,
        selected_job_key: props.selectedJobKey,
      });
      const account = await getSession();
      if (epoch !== requestEpoch.current) return;
      if (!account.authenticated || account.user_id !== props.userId ||
          !props.userId || next.cv_filename !== results.cv_filename ||
          next.match_mode !== results.match_mode) {
        throw new Error("Your signed-in account or CV changed. Refresh private matches.");
      }
      const previousKeys = new Set([
        ...results.recommended.map((row) => row.canonical_key),
        ...results.other_jobs.map((row) => row.canonical_key),
      ]);
      if ([...next.recommended, ...next.other_jobs].length &&
          [...next.recommended, ...next.other_jobs].every((row) =>
            previousKeys.has(row.canonical_key))) {
        throw new Error("The job feed changed while loading. Retry matching for current results.");
      }
      setResults((current) => {
        if (epoch !== requestEpoch.current || !current) return current;
        return {
          ...current,
          recommended: [...current.recommended, ...next.recommended],
          other_jobs: [...current.other_jobs, ...next.other_jobs],
          recommended_count: next.recommended_count,
          other_jobs_count: next.other_jobs_count,
          current_jobs_count: next.current_jobs_count,
          selected_job: next.selected_job,
        };
      });
    } catch (exc) {
      if (epoch === requestEpoch.current) setPagingError(
        exc instanceof Error ? exc.message : "Could not load more current jobs.");
    } finally {
      if (epoch === requestEpoch.current) setPaging(false);
    }
  }

  function toggleSelected(key: string) {
    if (props.queueBusy || queueInFlight.current) return;
    setBatchResult(null);
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
    if (!selected.length || props.queueBusy || queueInFlight.current) return;
    const keys = [...selected]; // immutable exact selection for this one run
    const scope = queueScope.current;
    queueInFlight.current = true;
    setError("");
    setBatchResult(null);
    setBatchProgress({ completed: 0, total: keys.length });
    try {
      const outcome = await props.onPrepareSelected(keys, (completed, total) => {
        if (queueScope.current === scope) setBatchProgress({ completed, total });
      });
      if (queueScope.current !== scope) return;
      // A successful private draft is durable. Keep ONLY failed keys checked
      // so "Retry" never needlessly asks the server for already saved jobs.
      const succeeded = new Set(outcome.preparedKeys);
      setSelected((current) => current.filter((key) => !succeeded.has(key)));
      setBatchResult(outcome);
    } catch (exc) {
      if (queueScope.current === scope) {
        setError(exc instanceof Error ? exc.message : "Could not prepare the selected drafts.");
      }
    } finally {
      queueInFlight.current = false;
      if (queueScope.current === scope) setBatchProgress(null);
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
            disabled={props.queueBusy || !job.source_current ||
              (!chosen && selected.length >= 15)} />
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
        <p><strong>AutoApply preparation and private case agents are available.</strong>
          Select vacancies below to prepare saved drafts and start one in-app tracking agent per job.
          The agents cannot contact employers; background reminders depend on the server worker.
          Final submission still requires a separately authorized employer integration and approval.
          Missing authorization or uncertain forms always wait for review—not “Submitted”.</p>
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
      {props.cv.present ? <div className="flow-filter">
        <label><Search size={17} aria-hidden="true"/>
          <input aria-label="Filter matching jobs" type="search" value={filter}
            onChange={(event) => setFilter(event.target.value)}
            maxLength={120}
            placeholder="Search all current jobs by title, employer or location"/>
        </label>
        <button className="outline-btn compact" type="button"
          onClick={() => setShowOther(current => !current)}>
          {showOther ? "Hide other jobs" : "Include other current jobs (" +
            (results?.other_jobs_count ?? results?.other_jobs.length ?? 0) + ")"}
        </button>
      </div> : null}
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
        <p className="muted">Search filters the entire current job database. Load more to reach later results; a vacancy chosen from Search stays available above the pages.</p>
        {props.selectedJobKey && !results.selected_job &&
          !jobs.some((row) => row.canonical_key === props.selectedJobKey) ?
          <p className="flow-boundary" role="status">The selected vacancy is no longer current or available for CV matching. Choose another job from Search.</p> : null}
        {jobs.length ? <>
          <div className="flow-job-list">{jobs.map(resultCard)}</div>
          <p className="muted" role="status">Showing {jobs.length} current job cards.
            {" " + results.recommended_count + " ranked results"}
            {" · " + (showOther ? (results.other_jobs_count ?? results.other_jobs.length) : 0) + " exploratory results"}.
            {results.selected_job ? " Your Search-selected vacancy is pinned above." : ""}</p>
          {hasMore ? <button className="secondary-btn" type="button"
            disabled={paging} onClick={() => void loadMore()}>
            {paging ? "Loading more jobs…" : "Load more current jobs"}
            {paging ? <Loader2 size={15} className="rotate"/> : <ArrowRight size={15}/>}
          </button> : null}
          {pagingError ? <p role="alert" className="flow-error">{pagingError}</p> : null}
        </> : <div className="empty-state"><CircleHelp size={27}/><h3>No jobs match these filters</h3>
          <p>Include other current jobs, change the search or check again after source refresh.</p>
          <button className="secondary-btn" type="button" onClick={props.onFindJobs}>
            Browse all jobs <ArrowRight size={16}/>
          </button></div>}
        {props.mode === "automatic" ? <div className="flow-queue">
          <strong>{selected.length} of 15 vacancies selected</strong>
          <p>Each selected job gets its own private application draft and in-app agent.
            No email, call or employer application is sent. You can pause or close an agent later.</p>
          {batchProgress ? <p role="status" aria-live="polite">
            Checked {batchProgress.completed} of {batchProgress.total} selected jobs.
            A failed posting will not stop the remaining selections.
          </p> : null}
          {batchResult && batchResult.failedKeys.length > 0 ? <div className="flow-boundary" role="status">
            <strong>{batchResult.preparedKeys.length} private draft(s) ready;
              {" " + batchResult.failedKeys.length} job(s) need a retry.</strong>
            <p>Successful jobs were removed from this selection. Only failed jobs remain
              checked, and none were submitted to an employer.</p>
            {batchResult.preparedKeys.length ? <button className="outline-btn compact"
              type="button" onClick={props.onOpenApplications}>
              Open prepared applications <ArrowRight size={14}/>
            </button> : null}
          </div> : null}
          <button className="primary-btn" type="button" disabled={!selected.length || props.queueBusy}
            onClick={() => void queue()}>
            {props.queueBusy ? "Preparing selected drafts and agents…" :
              batchResult?.failedKeys.length &&
                selected.every((key) => batchResult.failedKeys.includes(key))
                ? "Retry " + selected.length + " failed job" + (selected.length === 1 ? "" : "s")
                : "Prepare applications & start agents"}
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
