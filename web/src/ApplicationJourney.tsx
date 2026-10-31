import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowUpRight, CheckCircle2, FileText, Loader2, Search, UploadCloud,
  WandSparkles, Bot, ShieldCheck, CircleHelp, ExternalLink, RefreshCw
} from "lucide-react";
import { getCVJobMatches, getSession } from "./api";
import { safeExternalJobUrl } from "./lib";
import { addCVShortlist, AUTOAPPLY_SELECTION_LIMIT, visibleCurrentKeys } from "./autoapplyShortlist";
import type {
  ApplicationAssistanceLevel, ApplicationFlowMode,
  CVDocument, CVJobMatches, SearchJobCard, AutoApplyBatchOutcome
} from "./types";

const CV_PAGE_SIZE = 40;

const MODE_INFO: Record<ApplicationFlowMode, {
  title: string; summary: string; responsibility: string; next: string;
}> = {
  manual: {
    title: "Apply manually",
    summary: "See CV-matched jobs, then open the original employer application.",
    responsibility: "You fill the employer form and press Submit.",
    next: "Next: choose a job and open the employer form.",
  },
  assisted: {
    title: "Apply with AI help",
    summary: "Get job-specific CV and letter support, with optional reviewed form filling.",
    responsibility: "You check every detail and decide whether to send.",
    next: "Next: choose the kind of assistance, then a job.",
  },
  automatic: {
    title: "AutoApply",
    summary: "Prepare multiple CV-matched applications, review them and send eligible authorized ATS batches.",
    responsibility: "Employer submission requires a separately approved Lever/Ashby job and your final review.",
    next: "Next: select jobs, prepare drafts and approve eligible submissions in My applications.",
  },
};

export default function ApplicationJourney(props: {
  userId: string;
  cv: CVDocument;
  mode: ApplicationFlowMode | null;
  selectedJobKey: string;
  uploading: boolean;
  preparing: string;
  queueBusy: boolean;
  onMode: (mode: ApplicationFlowMode) => void;
  onUpload: () => void;
  onReviewCV: () => void;
  onFindJobs: () => void;
  onOpenApplications: (workspaceId?: string) => void;
  onPrepare: (canonicalKey: string) => Promise<void>;
  onPrepareSelected: (
    canonicalKeys: string[], onProgress: (completed: number, total: number) => void,
    shouldStop?: () => boolean, keepOnApply?: boolean
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
  // A deliberate single-job choice for Manual/Assisted. This is UI-only:
  // choosing never creates a private workspace or contacts an employer.
  const [focusedKey, setFocusedKey] = useState(props.cv.present ? props.selectedJobKey : "");
  const [batchResult, setBatchResult] = useState<AutoApplyBatchOutcome | null>(null);
  const [batchProgress, setBatchProgress] = useState<{ completed: number; total: number } | null>(null);
  const queueInFlight = useRef<symbol | null>(null);
  const stopRequestedRef = useRef(false);
  const [stopRequested, setStopRequested] = useState(false);
  // In-flight batch results cannot restore choices from a replaced CV or
  // different account, even if their server calls already completed.
  const queueScope = useRef("");
  // A search/filter/view change must invalidate pending selection work in
  // addition to the original account/CV boundary. A job from a previous
  // query cannot silently become an application in the new result set.
  queueScope.current = JSON.stringify([
    props.userId, props.cv.sha256 || "", props.cv.present,
    props.mode, filter.trim(), activeQuery, revision, showOther,
  ]);

  // Debounce only the read-only query. Ranking and filtering happen on the
  // entire current job ledger, NOT just the rows already in this browser.
  useEffect(() => {
    const timer = window.setTimeout(() => setActiveQuery(filter.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [filter]);

  useEffect(() => {
    setSelected([]);
    setFocusedKey(props.cv.present ? props.selectedJobKey : "");
    setBatchResult(null);
    setBatchProgress(null);
    setStopRequested(false);
    stopRequestedRef.current = true; // old job loop must not continue on new CV
  }, [props.cv.sha256, props.cv.present, props.userId, props.selectedJobKey]);

  // A mode change must not silently re-use a previous AutoApply selection.
  // If a parent forces a mode change during a running batch, stop before
  // the next private job; never imply that a mode switch revoked the server
  // request already in flight.
  useEffect(() => {
    if (props.mode !== "automatic") {
      if (queueInFlight.current) stopRequestedRef.current = true;
      setSelected([]);
    }
  }, [props.mode]);

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

  // A Search-selected current vacancy is pinned by the original read-only
  // API. If filtering/source refresh removes it, no draft action remains
  // available until the applicant chooses a visible current vacancy.
  const focusedJob = jobs.find((row) => row.canonical_key === focusedKey &&
    row.job.source_current) || null;
  const currentSelection = visibleCurrentKeys(selected, jobs);
  const staleSelectionCount = selected.length - currentSelection.length;
  const shortlistSuggestion = addCVShortlist(selected, results?.recommended || []);
  const queryPending = filter.trim() !== activeQuery;
  const hasChosenJob = props.cv.present && !!props.mode &&
    (props.mode === "automatic" ? currentSelection.length > 0 : !!focusedJob);

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
    if (props.queueBusy || queueInFlight.current || batchResult?.accessInterrupted ||
        loading || paging || queryPending || !!error ||
        !jobs.some((row) => row.canonical_key === key && row.job.source_current &&
          !!safeExternalJobUrl(row.job.application_url))) return;
    setBatchResult(null);
    setSelected((current) => current.includes(key)
      ? current.filter((row) => row !== key)
      : [...current, key].slice(0, AUTOAPPLY_SELECTION_LIMIT));
  }

  function selectCVShortlist() {
    if (props.mode !== "automatic" || !results || props.queueBusy ||
        !!queueInFlight.current || loading || paging || queryPending || !!error ||
        batchResult?.accessInterrupted || staleSelectionCount > 0) return;
    const proposal = addCVShortlist(selected, results.recommended);
    if (!proposal.added.length) return;
    setBatchResult(null);
    setSelected(proposal.selected);
  }

  function clearSelected() {
    if (props.queueBusy || queueInFlight.current) return;
    setSelected([]);
    setBatchResult(null);
  }

  function changeSearch(value: string) {
    // Do not cancel a possibly committed backend request. Stop *after* the
    // current job and require a newly reviewed source-current selection.
    if (queueInFlight.current) stopRequestedRef.current = true;
    setSelected([]);
    setBatchResult(null);
    setFilter(value);
  }

  function changeOtherVisibility() {
    if (props.queueBusy || queueInFlight.current) return;
    setShowOther((current) => !current);
    setSelected([]);
    setBatchResult(null);
  }

  async function prepareOne(key: string) {
    setError("");
    try { await props.onPrepare(key); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "Unable to open your draft."); }
  }

  const blockedKeys = new Set(
    (batchResult?.issues || []).filter((issue) => !issue.retryable)
      .map((issue) => issue.canonicalKey)
  );
  const accessInterrupted = batchResult?.accessInterrupted === true;
  const runnableSelection = accessInterrupted ? [] :
    currentSelection.filter((key) => !blockedKeys.has(key));

  async function queue() {
    if (!runnableSelection.length || props.mode !== "automatic" || !results ||
        loading || paging || queryPending || !!error || staleSelectionCount ||
        props.queueBusy || queueInFlight.current) return;
    const keys = [...runnableSelection]; // immutable exact selection for this run
    const previous = batchResult; // preserve earlier review-required job failures
    const scope = queueScope.current;
    const batchToken = Symbol("one-private-autoapply-selection");
    queueInFlight.current = batchToken;
    stopRequestedRef.current = false;
    setStopRequested(false);
    setError("");
    // Keep earlier blocked reasons visible while a separate retry is running.
    setBatchProgress({ completed: 0, total: keys.length });
    try {
      const outcome = await props.onPrepareSelected(keys, (completed, total) => {
        if (queueScope.current === scope) setBatchProgress({ completed, total });
      }, () => stopRequestedRef.current || queueScope.current !== scope,
      blockedKeys.size > 0);
      if (queueScope.current !== scope) return;
      // A successful private draft is durable. Never retry it just because
      // another exact job failed or the user stopped the remaining batch.
      const succeeded = new Set(outcome.preparedKeys);
      setSelected((current) => current.filter((key) => !succeeded.has(key)));
      const attempted = new Set(keys);
      const preparedKeys = [...new Set([
        ...(previous?.preparedKeys || []), ...outcome.preparedKeys,
      ])];
      // Preserve successful job->workspace identity across selected retries
      // instead of opening an unrelated "latest" draft from the owner list.
      const successful = new Set(preparedKeys);
      const preparedByKey = new Map<string, string>();
      for (const item of [
        ...(previous?.preparedWorkspaces || []), ...(outcome.preparedWorkspaces || []),
      ]) {
        if (successful.has(item.canonicalKey) && item.workspaceId) {
          preparedByKey.set(item.canonicalKey, item.workspaceId);
        }
      }
      const merged: AutoApplyBatchOutcome = {
        ...outcome,
        preparedKeys,
        preparedWorkspaces: [...preparedByKey].map(([canonicalKey, workspaceId]) =>
          ({ canonicalKey, workspaceId })),
        failedKeys: [
          ...(previous?.failedKeys || []).filter((key) => !attempted.has(key)),
          ...outcome.failedKeys,
        ],
        skippedKeys: [
          ...(previous?.skippedKeys || []).filter((key) => !attempted.has(key)),
          ...(outcome.skippedKeys || []),
        ],
        issues: [
          ...(previous?.issues || []).filter((item) => !attempted.has(item.canonicalKey)),
          ...(outcome.issues || []),
        ],
      };
      setBatchResult(merged);
    } catch (exc) {
      if (queueScope.current === scope) {
        setError(exc instanceof Error ? exc.message : "Could not prepare the selected drafts.");
      }
    } finally {
      // Do not let an old CV/account batch clear the in-flight flag for
      // another selected run that started after its scope was replaced.
      if (queueInFlight.current === batchToken) {
        queueInFlight.current = null;
        if (queueScope.current === scope) {
          setBatchProgress(null);
          setStopRequested(false);
        }
      }
    }
  }

  function stopAfterCurrentJob() {
    if (!queueInFlight.current || stopRequestedRef.current) return;
    stopRequestedRef.current = true;
    setStopRequested(true);
  }

  function resultCard(row: SearchJobCard) {
    const job = row.job;
    const link = safeExternalJobUrl(job.application_url);
    const chosen = selected.includes(row.canonical_key);
    const focused = props.mode !== "automatic" && focusedJob?.canonical_key === row.canonical_key;
    const isMatch = row.lane === "recommended";
    const matches = row.reasons.filter((reason) =>
      !reason.toLowerCase().includes("your stated skills")).slice(0, 2);
    return <article className={"flow-job" + (focused ? " highlighted" : "")}
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
            disabled={props.queueBusy || !!queueInFlight.current ||
              accessInterrupted || loading || paging || queryPending ||
              !job.source_current || !link ||
              (!chosen && selected.length >= AUTOAPPLY_SELECTION_LIMIT)} />
          {chosen ? "Selected" : "Select for preparation"}
        </label> : null}
        {props.mode && props.mode !== "automatic" ? <button type="button"
          className={focused ? "navy-btn compact" : "secondary-btn compact"}
          aria-pressed={focused} disabled={!job.source_current}
          onClick={() => setFocusedKey(row.canonical_key)}>
          {focused ? "Selected job" : "Choose this job"}
          {focused ? <CheckCircle2 size={14}/> : <ArrowRight size={14}/>}
        </button> : null}
        {link && !focused ? <a className="outline-btn compact" href={link}
          target="_blank" rel="noopener noreferrer">
          View employer posting <ExternalLink size={14}/>
        </a> : !link ? <small>Original employer link unavailable</small> : null}
      </div>
      {focused && props.mode ? <div className="flow-job-next"
        aria-label={"Next step for " + job.role_title}>
        <div className="flow-job-next-copy">
          <strong><CheckCircle2 size={17}/> Selected for {props.mode === "manual" ? "Manual" : "Assisted"} application</strong>
          <p>{props.mode === "manual"
            ? "You fill and submit on the original employer website. Save a private draft first if you want SmartPloy to track the result; opening the website alone does not create a case."
            : assistance === "filter"
              ? "Filter-only opens the employer website; it does not create an application case or track a submission. For tracked documents, switch to Match + tailored documents."
              : "Next, open the private job-specific CV and cover-letter editor. Review everything before any employer submission."}</p>
        </div>
        <div className="flow-job-next-actions">
          {props.mode === "manual" || (props.mode === "assisted" && assistance === "filter")
            ? link ? <a href={link} target="_blank" rel="noopener noreferrer"
              className="navy-btn compact">Apply on employer site <ExternalLink size={14}/></a> :
              <span className="muted">Employer link unavailable. This job cannot be submitted here.</span>
            : null}
          {props.mode === "manual" ? <button className="outline-btn compact" type="button"
            disabled={!!props.preparing || !job.source_current}
            onClick={() => void prepareOne(row.canonical_key)}>
            {props.preparing === row.canonical_key ? "Saving…" : "Save application draft"}
            <ArrowRight size={14}/>
          </button> : null}
          {props.mode === "assisted" && assistance !== "filter" ? <button
            className="navy-btn compact" type="button"
            disabled={!!props.preparing || !job.source_current}
            onClick={() => void prepareOne(row.canonical_key)}>
            {props.preparing === row.canonical_key ? "Opening…" : "Prepare CV & application"}
            <ArrowRight size={14}/>
          </button> : null}
          {props.mode === "assisted" && assistance !== "filter" && link ?
            <a className="outline-btn compact" href={link}
              target="_blank" rel="noopener noreferrer">
              View employer posting <ExternalLink size={14}/>
            </a> : null}
        </div>
      </div> : null}
    </article>;
  }

  return <div className="application-flow stacked" aria-label="Guided application journey">
    <section className="panel flow-intro">
      <div className="panel-heading"><div>
        <p className="section-kicker">YOUR APPLICATION GUIDE</p>
        <h2>Upload your CV. Choose your method. Apply.</h2>
        <p>One clear route, from your connected CV to an application outcome.
          Pick how much work SmartPloy should do; no mode choice sends anything to an employer.</p>
      </div></div>
      <ol className="flow-steps" aria-label="Application steps">
        <li className={props.cv.present ? "done" : "current"}
          aria-current={!props.cv.present ? "step" : undefined}>1 · Your CV</li>
        <li className={props.mode ? "done" : props.cv.present ? "current" : ""}
          aria-current={props.cv.present && !props.mode ? "step" : undefined}>2 · Choose method</li>
        <li className={hasChosenJob ? "done" : props.mode && props.cv.present ? "current" : ""}
          aria-current={props.mode && props.cv.present && !hasChosenJob ? "step" : undefined}>3 · Choose job & prepare</li>
        <li className={hasChosenJob ? "current" : ""}
          aria-current={hasChosenJob ? "step" : undefined}>4 · Review & submit</li>
      </ol>
      <div className="flow-next-action" role="status">
        {props.cv.present ? <CheckCircle2 size={24} aria-hidden="true"/> :
          <UploadCloud size={24} aria-hidden="true"/>}
        <div>
          <strong>{!props.cv.present ? "First: connect your CV." :
            !props.mode ? "CV connected. Now choose Manual, Assisted or Automatic." :
              hasChosenJob ? "Job choice recorded. Follow its next action below." :
                "Next: choose a current job from the matches."}</strong>
          <p>{!props.cv.present ? "Upload a PDF/DOCX or create a CV in Step 1. The Manual, Assisted and Automatic choices unlock only after a CV is connected." :
            !props.mode ? "The three paths are explained in Step 2 below. Nothing will be applied for until you take the appropriate next action." :
              hasChosenJob ? (props.mode === "automatic" ?
                selected.length + " jobs selected for private preparation. Use the preparation button below; no employer send has occurred." :
                "Selected: " + focusedJob!.job.role_title + " · " + focusedJob!.job.company +
                ". Follow the highlighted job's next action. No employer send has occurred.") :
                "Your chosen method is " + MODE_INFO[props.mode].title +
                ". Pick an exact current vacancy in Step 3 to continue."}</p>
        </div>
      </div>
    </section>
    <section className="panel flow-cv">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 1 OF 4</p>
        <h2>Your CV</h2>
        <p>One CV for searching and application preparation. PDF or DOCX up to 5 MB.</p>
      </div></div>
      {props.cv.present ? <div className="flow-uploaded">
        <CheckCircle2 size={23} aria-hidden="true"/>
        <div><strong>{props.cv.filename || "Your CV"} is ready</strong>
          <small>CV text is available for private matching. Review extracted facts before sending any application; uploading did not approve or share them.</small></div>
      </div> : <p className="flow-instruction">Start here: upload a CV and SmartPloy will automatically find matching current vacancies from its database.</p>}
      <div className="row-actions">
        <button className="primary-btn" type="button" disabled={props.uploading} onClick={props.onUpload}>
          {props.uploading ? <Loader2 size={16} className="rotate"/> : <UploadCloud size={16}/>}
          {props.uploading ? "Uploading and reading your CV…" :
            props.cv.present ? "Replace CV" : "Upload CV & find jobs"}
        </button>
        <button className="outline-btn" type="button" onClick={props.onReviewCV}>
          {props.cv.present ? "Review CV text & facts" : "Create CV from scratch"} <ArrowRight size={16}/>
        </button>
      </div>
    </section>

    <section className={"panel flow-choice" +
      (!props.cv.present ? " flow-choice-locked" : !props.mode ? " flow-choice-needed" : "")}
      aria-labelledby="flow-choice-title">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 2 OF 4 · YOUR DECISION</p>
        <h2 id="flow-choice-title">How do you want to apply?</h2>
        <p>This choice controls the next job actions. You can switch methods anytime;
          selecting a method never authorizes an employer submission.</p>
      </div></div>
      {!props.cv.present ? <div className="flow-decision flow-cv-required" role="status">
        <CircleHelp size={20} aria-hidden="true"/>
        <p><strong>Step 2 is locked until your CV is saved.</strong> Return to Step 1
          to upload your CV or create one from scratch. Your application
          method is not selected automatically.</p>
      </div> : <>
      {!props.mode ? <div className="flow-decision" role="status">
        <CircleHelp size={20} aria-hidden="true"/>
        <p><strong>Your CV is connected. Choose a method to continue.</strong>
          {" "}Manual means you submit; Assisted supports CV/letter and forms;
          Automatic prepares private batches and offers employer-authorized submissions after review.</p>
      </div> : <div className="flow-selection-confirmation" role="status">
        <CheckCircle2 size={19} aria-hidden="true"/>
        <span><strong>{MODE_INFO[props.mode].title} selected.</strong> {MODE_INFO[props.mode].next}
          {" "}No employer application has been sent.</span>
      </div>}
      <div className="flow-mode-grid" role="group" aria-label="Choose application method">
        {(["manual", "assisted", "automatic"] as const).map((choice) => {
          const Icon = choice === "manual" ? FileText : choice === "assisted" ? WandSparkles : Bot;
          return <button type="button" key={choice}
            className={"flow-mode" + (props.mode === choice ? " selected" : "")}
            aria-pressed={props.mode === choice}
            disabled={props.queueBusy || !!queueInFlight.current}
            onClick={() => props.onMode(choice)}>
            <span className="flow-mode-head">
              <Icon size={23} aria-hidden="true"/>
              <span className="flow-mode-label">{choice.toUpperCase()}</span>
              <span className="flow-mode-choice">{props.mode === choice ? "Selected" : "Choose"}</span>
            </span>
            <strong>{MODE_INFO[choice].title}</strong>
            <small>{MODE_INFO[choice].summary}</small>
            <span className="flow-mode-responsibility">{MODE_INFO[choice].responsibility}</span>
            <span className="flow-mode-next">{MODE_INFO[choice].next}</span>
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
        <p>Supported browser form filling requires a reviewed handoff. Final browser submission stays manual;
          authorized partner submission has separate per-job approval and confirmation.</p>
      </fieldset> : null}
      {props.mode === "automatic" ? <div className="flow-boundary" role="note">
        <ShieldCheck size={20} aria-hidden="true"/>
        <p><strong>AutoApply prepares selected jobs first.</strong>{" "}
          It saves a CV and letter for review, with an in-app tracking agent per job.
          After reviewing the exact drafts, My applications offers a one-action
          batch of up to three employer-authorized Lever/Ashby submissions.
          Jobs without rights remain Assisted/Manual. No automatic background
          employer send, unknown-form answers or retries occur here.</p>
      </div> : null}
      </>}
    </section>
    <section className="panel flow-matches">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 3 OF 4</p><h2>Jobs from your CV</h2>
        <p>These are current jobs in SmartPloy's own database, not web results invented for your CV.</p>
      </div></div>
      {props.cv.present && !props.mode ? <div className="flow-choice-gate" role="note">
        <CircleHelp size={19} aria-hidden="true"/>
        <p><strong>Matching jobs are ready to browse.</strong> Choose Manual, Assisted or Automatic
          in Step 2 above before creating drafts or starting an application.</p>
      </div> : null}
      {props.cv.present ? <div className="flow-filter">
        <label><Search size={17} aria-hidden="true"/>
          <input aria-label="Filter matching jobs" type="search" value={filter}
            onChange={(event) => changeSearch(event.target.value)}
            maxLength={120}
            placeholder="Search all current jobs by title, employer or location"/>
        </label>
        <button className="outline-btn compact" type="button"
          disabled={props.queueBusy || !!queueInFlight.current}
          onClick={changeOtherVisibility}>
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
          {props.mode ? <div className="flow-job-instruction" role="status">
            <CheckCircle2 size={19} aria-hidden="true"/>
            <div><strong>{props.mode === "automatic"
              ? selected.length ? selected.length + " jobs selected for private preparation" :
                "Choose jobs for AutoApply preparation"
              : focusedJob ? "Selected: " + focusedJob.job.role_title + " at " +
                focusedJob.job.company : "Choose one job to continue"}</strong>
              <p>{props.mode === "automatic" ? "Tick up to 15 current vacancies, then select Prepare applications & start agents below. No employer is contacted." :
                focusedJob ? "Use the buttons inside the highlighted job to take the next step. Choosing a job did not create or send an application." :
                "Click Choose this job on a vacancy. SmartPloy then shows the next action for your chosen method; choosing alone does not create a draft or submit."}</p>
            </div>
          </div> : null}
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
          <strong>{selected.length} of {AUTOAPPLY_SELECTION_LIMIT} vacancies selected</strong>
          <p>Each selected job gets its own private application draft and in-app agent.
            No email, call or employer application is sent. You can pause or close an agent later.</p>
          <div className="flow-shortlist-actions" role="group" aria-label="CV-matched AutoApply shortlist">
            <button className="navy-btn compact" type="button"
              disabled={!shortlistSuggestion.added.length || !results || loading ||
                paging || queryPending || !!error || staleSelectionCount > 0 ||
                props.queueBusy || !!queueInFlight.current || accessInterrupted}
              onClick={selectCVShortlist}>
              Select {shortlistSuggestion.added.length} CV-title matched job{shortlistSuggestion.added.length === 1 ? "" : "s"}
              <CheckCircle2 size={15} aria-hidden="true"/>
            </button>
            <button className="outline-btn compact" type="button"
              disabled={!selected.length || props.queueBusy || !!queueInFlight.current}
              onClick={clearSelected}>Clear selected jobs</button>
          </div>
          <p className="flow-shortlist-note">
            This selects only loaded, current vacancies with a direct role-title match
            and a valid employer link. Weaker skill-only matches and unrelated jobs
            require individual review. No selection starts an application automatically.
          </p>
          {results && results.recommended_count > results.recommended.length ?
            <p className="flow-shortlist-note">Only currently loaded recommendations are eligible.
              Use Load more current jobs to include later matches.</p> : null}
          {staleSelectionCount > 0 ? <div role="alert" className="flow-boundary">
            {staleSelectionCount} selected job{staleSelectionCount === 1 ? " is" : "s are"}
            no longer visible and eligible. Clear and reselect current vacancies before preparing.
          </div> : null}
          {selected.length > 0 && staleSelectionCount === 0 ?
            <details className="flow-shortlist-review">
              <summary>Review {selected.length} selected job{selected.length === 1 ? "" : "s"} before preparing</summary>
              <ol>{selected.map((key) => {
                const row = jobs.find((item) => item.canonical_key === key);
                return row ? <li key={key}><strong>{row.job.role_title}</strong> · {row.job.company}</li> : null;
              })}</ol>
            </details> : null}
          {batchProgress ? <div className="row-actions">
            <p role="status" aria-live="polite">
              Checked {batchProgress.completed} of {batchProgress.total} selected jobs.
              {stopRequested ? " Stop requested; current job may still complete." :
                " A failed posting will not stop other jobs."}
            </p>
            <button className="outline-btn compact" type="button"
              disabled={stopRequested} onClick={stopAfterCurrentJob}>
              {stopRequested ? "Stopping after current job…" : "Stop after current job"}
            </button>
          </div> : null}
          {batchResult && (batchResult.failedKeys.length > 0 ||
            (batchResult.skippedKeys?.length ?? 0) > 0) ? <div className="flow-boundary" role="status">
            <strong>{batchResult.preparedKeys.length} private draft(s) ready;
              {batchResult.failedKeys.length ? " " + batchResult.failedKeys.length +
                (blockedKeys.size ? " job(s) require attention." : " job(s) need a retry.") :
                " no job failures."}</strong>
            <p>Successful jobs were removed from this selection.
              {batchResult.skippedKeys?.length
                ? " " + batchResult.skippedKeys.length +
                  " job(s) were not started after Stop and remain selected." : ""}
              {" "}No application was submitted to an employer.</p>
            {accessInterrupted ? <p role="alert">Access was denied during private preparation.
              Already prepared drafts remain saved, and no further jobs were attempted.
              Restore access and reload SmartPloy before continuing this queue.</p> : null}
            {(batchResult.issues || []).length > 0 ? <ul aria-label="Job preparation issues">
              {batchResult.issues!.map((issue) => {
                const matching = jobs.find((row) => row.canonical_key === issue.canonicalKey);
                return <li key={issue.canonicalKey}>
                  <strong>{matching?.job.role_title || "Previously selected job"}</strong>
                  {" — " + issue.guidance}
                </li>;
              })}
            </ul> : null}
            {blockedKeys.size > 0 ? <p>
              {blockedKeys.size} job(s) require review or a fresh posting;
              they will not be retried without a new selection.
              <button className="outline-btn compact" type="button" onClick={props.onFindJobs}>
                Find current vacancies <ArrowRight size={14}/>
              </button>
            </p> : null}
            {batchResult.preparedKeys.length ? <>
              <button className="outline-btn compact" type="button"
                onClick={() => props.onOpenApplications(
                  batchResult.preparedWorkspaces?.[0]?.workspaceId)}>
                Open prepared applications <ArrowRight size={14}/>
              </button>
              {(batchResult.preparedWorkspaces?.length || 0) > 0 ? (
                <details className="flow-prepared-details">
                  <summary>Review each saved application individually</summary>
                  <div className="row-actions" aria-label="Prepared application review links">
                    {batchResult.preparedWorkspaces!.map((entry) => {
                      const match = jobs.find((row) => row.canonical_key === entry.canonicalKey);
                      const label = match
                        ? match.job.role_title + " · " + match.job.company
                        : "Prepared job application";
                      return <button key={entry.canonicalKey} type="button"
                        className="outline-btn compact"
                        aria-label={"Review prepared " + label}
                        onClick={() => props.onOpenApplications(entry.workspaceId)}>
                        Review {label} <ArrowRight size={14}/>
                      </button>;
                    })}
                  </div>
                  <p>Opens the exact private draft for review. No application is sent.</p>
                </details>
              ) : null}
            </> : null}
          </div> : null}
          <button className="primary-btn" type="button"
            disabled={!runnableSelection.length || props.queueBusy || !!queueInFlight.current ||
              loading || paging || queryPending || !!error || staleSelectionCount > 0}
            onClick={() => void queue()}>
            {props.queueBusy ? "Preparing selected drafts and agents…" :
              accessInterrupted ? "Access denied · reload to continue" :
              !runnableSelection.length && blockedKeys.size
                ? "Review blocked jobs first" :
              batchResult?.skippedKeys?.length
                ? "Continue " + runnableSelection.length + " remaining job" +
                  (runnableSelection.length === 1 ? "" : "s") :
              batchResult?.failedKeys.length &&
                runnableSelection.every((key) => batchResult.failedKeys.includes(key))
                ? "Retry " + runnableSelection.length + " failed job" +
                  (runnableSelection.length === 1 ? "" : "s")
                : "Prepare applications & start agents"}
            <ArrowRight size={16}/>
          </button>
        </div> : null}
      </> : null}
    </section>
    <section className="panel flow-next">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 4 OF 4</p><h2>Continue your applications</h2>
        <p>Only an independently confirmed employer submission counts as submitted.
          Return here to review documents, resolve blocked forms, and track the outcome.</p>
      </div></div>
      <p className="flow-next-guidance" role="note">
        {!props.mode ? "First choose an application method in Step 2. Matching jobs can be browsed without submitting." :
          props.mode === "manual" ? "Manual: save a private draft first if you want to track the outcome here. Otherwise, open and submit the employer form independently." :
          props.mode === "assisted" ? "Assisted: prepare a tracked job-specific CV and letter, review form answers, then submit yourself or use a separately authorized route." :
            "Automatic: prepare selected private drafts and agents, review each result and handle any Needs Review items. This screen does not automatically send to employers."}
      </p>
      <div className="row-actions">
        <button className="secondary-btn" type="button"
          onClick={() => props.onOpenApplications()}>
          Open My applications <ArrowRight size={16}/>
        </button>
        <button className="outline-btn" type="button" onClick={props.onFindJobs}>
          Search all jobs <ArrowUpRight size={16}/>
        </button>
      </div>
    </section>
  </div>;
}
