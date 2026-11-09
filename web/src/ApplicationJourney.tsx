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
    summary: "Open the employer form and apply yourself.",
    responsibility: "You decide when to submit.",
    next: "Next: choose a job and open the employer form.",
  },
  assisted: {
    title: "Apply with AI help",
    summary: "Tailored documents and reviewed form help.",
    responsibility: "Review before sending.",
    next: "Next: choose the kind of assistance, then a job.",
  },
  automatic: {
    title: "AutoApply",
    summary: "Prepare private applications, then review.",
    responsibility: "No submission without separate approval.",
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
  onClearPinnedJob?: () => void;
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
  const [showMethodPicker, setShowMethodPicker] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  // An explicit Jobs-card AutoApply choice is offered once for this exact
  // account, CV and job. Deselecting or changing modes never reselects it.
  const pinnedAutoSelectionRef = useRef("");
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
    props.mode, props.selectedJobKey, filter.trim(), activeQuery, revision, showOther,
  ]);

  // Debounce only the read-only query. Ranking and filtering happen on the
  // entire current job ledger, NOT just the rows already in this browser.
  useEffect(() => {
    const timer = window.setTimeout(() => setActiveQuery(filter.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [filter]);

  useEffect(() => {
    // A changed CV/account invalidates the entire private shortlist, including
    // unfinished jobs. Parent-side job pin revocation does NOT change either.
    setSelected([]);
    setFocusedKey(props.cv.present ? props.selectedJobKey : "");
    setBatchResult(null);
    setBatchProgress(null);
    setStopRequested(false);
    stopRequestedRef.current = true; // old job loop must not continue on new CV
  }, [props.cv.sha256, props.cv.present, props.userId]);

  useEffect(() => {
    // An explicit NEW Jobs-card pin resets the old selection. Removing a pin
    // on deselect or successful preparation must preserve remaining job
    // selections and failed-job retry receipts in this ongoing journey.
    if (!props.selectedJobKey) {
      setFocusedKey("");
      return;
    }
    setSelected([]);
    setFocusedKey(props.cv.present ? props.selectedJobKey : "");
    setBatchResult(null);
    setBatchProgress(null);
    setStopRequested(false);
    stopRequestedRef.current = true;
  }, [props.selectedJobKey]);

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

  // Reuse the exact job returned by the existing authenticated CV/job
  // endpoint. Never infer a second job, create a draft, or submit on mount.
  // This restores the Jobs → Automatic → selected-job continuation without
  // carrying a choice into another account, CV or later mode switch.
  useEffect(() => {
    if (props.mode !== "automatic" || !props.cv.present || !props.userId ||
        !props.selectedJobKey || !results || loading || paging ||
        filter.trim() !== activeQuery || !!error ||
        props.queueBusy || queueInFlight.current) return;
    const pinned = jobs.find((row) =>
      row.canonical_key === props.selectedJobKey && row.job.source_current &&
      !!safeExternalJobUrl(row.job.application_url));
    if (!pinned) return;
    const identity = JSON.stringify([
      props.userId, props.cv.sha256 || "", props.selectedJobKey,
    ]);
    if (pinnedAutoSelectionRef.current === identity) return;
    pinnedAutoSelectionRef.current = identity;
    setSelected([pinned.canonical_key]);
  }, [props.mode, props.cv.present, props.cv.sha256, props.userId,
      props.selectedJobKey, results, loading, paging, filter, activeQuery,
      error, props.queueBusy, jobs]);

  // A Search-selected current vacancy is pinned by the original read-only
  // API. If filtering/source refresh removes it, no draft action remains
  // available until the applicant chooses a visible current vacancy.
  const focusedJob = jobs.find((row) => row.canonical_key === focusedKey &&
    row.job.source_current) || null;
  const currentSelection = visibleCurrentKeys(selected, jobs);
  const staleSelectionCount = selected.length - currentSelection.length;
  const shortlistSuggestion = addCVShortlist(selected, results?.recommended || []);
  const quickDraftKeys = addCVShortlist([], results?.recommended || []).selected;
  const queryPending = filter.trim() !== activeQuery;
  const hasChosenJob = props.cv.present && !!props.mode &&
    (props.mode === "automatic" ? currentSelection.length > 0 : !!focusedJob);
  // A single, explicitly pinned job can continue straight to its exact
  // private application. All other AutoApply choices use the batch controls.
  const canContinuePinnedAutoJob =
    props.mode === "automatic" && !!props.selectedJobKey &&
    selected.length === 1 && currentSelection.length === 1 &&
    currentSelection[0] === props.selectedJobKey && !!results &&
    !loading && !paging && !queryPending && !error &&
    !props.queueBusy && !queueInFlight.current;

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
    if (selected.includes(key) && key === props.selectedJobKey) props.onClearPinnedJob?.();
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
    // Clearing the parent pin here would trigger the CV/job selection reset
    // effect and discard the newly added shortlist before it can be used.
    setBatchResult(null);
    setSelected(proposal.selected);
  }

  function clearSelected() {
    if (props.queueBusy || queueInFlight.current) return;
    props.onClearPinnedJob?.();
    setSelected([]);
    setBatchResult(null);
  }

  function changeSearch(value: string) {
    // Do not cancel a possibly committed backend request. Stop *after* the
    // current job and require a newly reviewed source-current selection.
    if (queueInFlight.current) stopRequestedRef.current = true;
    props.onClearPinnedJob?.();
    setSelected([]);
    setBatchResult(null);
    setFilter(value);
  }

  function changeOtherVisibility() {
    if (props.queueBusy || queueInFlight.current) return;
    props.onClearPinnedJob?.();
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

  async function queue(exactKeys: string[] = runnableSelection) {
    // Both the manual shortlist and quick path reuse the SAME private,
    // account-verified, source-current per-job preparation loop. Neither
    // authorizes an employer submission.
    if (!exactKeys.length || exactKeys.length > AUTOAPPLY_SELECTION_LIMIT ||
        new Set(exactKeys).size !== exactKeys.length ||
        visibleCurrentKeys(exactKeys, jobs).length !== exactKeys.length ||
        exactKeys.some((key) => blockedKeys.has(key)) || accessInterrupted ||
        props.mode !== "automatic" || !results || !props.cv.present ||
        loading || paging || queryPending || !!error || staleSelectionCount ||
        props.queueBusy || queueInFlight.current) return;
    const keys = [...exactKeys]; // immutable exact selection for this run
    const previous = batchResult; // preserve earlier review-required job failures
    const scope = queueScope.current;
    const batchToken = Symbol("one-private-autoapply-selection");
    let preparedPinnedJob = false;
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
      // Do not consume the parent pin before recording the remaining jobs:
      // changing selectedJobKey changes queueScope and can drop retry receipts.
      preparedPinnedJob = !!props.selectedJobKey &&
        outcome.preparedKeys.includes(props.selectedJobKey) &&
        keys.includes(props.selectedJobKey);
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
          // After the full result and retries are recorded, consume the
          // successful shortcut in parent state, including if this view was
          // unmounted by its own preparer navigating to My applications.
          if (preparedPinnedJob) props.onClearPinnedJob?.();
        }
      }
    }
  }

  function prepareCVMatchedDraftsNow() {
    // No background mutation: a real user click and exact-job confirmation
    // are required before preparing even private drafts. Only title-matched,
    // source-current, linked rows from the loaded CV-derived result qualify.
    if (!props.cv.present || props.mode !== "automatic" || !results ||
        loading || paging || queryPending || !!error || accessInterrupted ||
        selected.length || batchResult || props.queueBusy ||
        queueInFlight.current || !quickDraftKeys.length) return;
    const freshKeys = addCVShortlist([], results.recommended).selected;
    if (freshKeys.length !== quickDraftKeys.length ||
        freshKeys.some((key, index) => key !== quickDraftKeys[index]) ||
        visibleCurrentKeys(freshKeys, jobs).length !== freshKeys.length) return;
    const exactJobs = freshKeys.map((key) => jobs.find((row) =>
      row.canonical_key === key));
    if (exactJobs.some((row) => !row || !row.job.source_current)) return;
    const summary = exactJobs.map((row, index) =>
      (index + 1) + ". " + row!.job.role_title + " · " + row!.job.company
    ).join("\n");
    if (!window.confirm(
      "PREPARE " + freshKeys.length + " PRIVATE JOB APPLICATION DRAFT(S)?\n\n" +
      summary + "\n\nSmartPloy will prepare job-specific CV/letter drafts and " +
      "in-app agents only. It will NOT contact an employer or submit a job application. " +
      "You must review each document and separately approve any authorized submission."
    )) return;
    // Populate the same visible selection as the reviewed two-click path
    // for retry/stop behaviour, while the already verified immutable keys
    // are passed directly to queue (React state is asynchronous).
    setSelected(freshKeys);
    void queue(freshKeys);
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
        {props.mode && props.mode !== "automatic" && !focused ? <button type="button"
          className="secondary-btn compact"
          disabled={!job.source_current}
          onClick={() => setFocusedKey(row.canonical_key)}>
          Choose this job <ArrowRight size={14}/>
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
        <h2>Apply with confidence</h2>
        <p>CV → Method → Job → Documents → Employer form.</p>
      </div></div>
      <ol className="flow-steps" aria-label="Application steps">
        <li className={props.cv.present ? "done" : "current"}
          aria-current={!props.cv.present ? "step" : undefined}>1 · Your CV</li>
        <li className={props.mode ? "done" : props.cv.present ? "current" : ""}
          aria-current={props.cv.present && !props.mode ? "step" : undefined}>2 · Choose method</li>
        <li className={batchResult?.preparedKeys.length ? "done" : props.mode && props.cv.present ? "current" : ""}
          aria-current={props.mode && props.cv.present && !batchResult?.preparedKeys.length ? "step" : undefined}>3 · Choose job</li>
        <li className={batchResult?.preparedKeys.length ? "current" : ""}
          aria-current={batchResult?.preparedKeys.length ? "step" : undefined}>4 · Review documents</li>
      </ol>
      <div className="flow-primary-next" aria-label="Your next action">
        <div className="flow-primary-next-copy">
          <span>Do this next</span>
          <strong>{!props.cv.present
            ? "Upload or create your CV"
            : !props.mode || showMethodPicker
              ? "Choose Manual, Assisted or Automatic"
              : !hasChosenJob
                ? "Choose a real vacancy that fits your CV"
                : props.mode === "automatic"
                  ? "Prepare the jobs you selected, then review their drafts"
                  : "Continue with your selected employer vacancy"}</strong>
          <small>{!props.cv.present
            ? "No employer receives your CV when you upload it."
            : !props.mode || showMethodPicker
              ? "Nothing is selected or sent until you decide."
              : !hasChosenJob
                ? "Matches come from stored job listings; no application is sent."
                : "Your CV and cover letter remain private until a separately reviewed employer action."}</small>
        </div>
        {!props.cv.present ? <button className="primary-btn" type="button"
          onClick={props.onUpload} disabled={props.uploading}>
          Upload CV <ArrowRight size={16} aria-hidden="true"/>
        </button> : (!props.mode || showMethodPicker) ? <a className="navy-btn" href="#smartploy-flow-choice">
          Choose application type <ArrowRight size={16} aria-hidden="true"/>
        </a> : canContinuePinnedAutoJob ? <button className="navy-btn" type="button"
          onClick={() => void queue([props.selectedJobKey])}
          disabled={accessInterrupted || blockedKeys.has(props.selectedJobKey) ||
            staleSelectionCount > 0}
          aria-label="Prepare and open the selected job application">
          Prepare &amp; open this job <ArrowRight size={16} aria-hidden="true"/>
        </button> : <a className="navy-btn" href={hasChosenJob && props.mode === "automatic"
            ? "#smartploy-flow-queue" : "#smartploy-flow-matches"}>
          {hasChosenJob
            ? props.mode === "automatic" ? "Prepare selected applications" : "Continue selected job"
            : "Choose matching jobs"} <ArrowRight size={16} aria-hidden="true"/>
        </a>}
      </div>
      {props.cv.present ? <div className="flow-session-tools" aria-label="Current application setup">
        <details>
          <summary><CheckCircle2 size={16} aria-hidden="true"/> CV ready · {props.cv.filename || "Your CV"}</summary>
          <div className="row-actions">
            <button className="outline-btn compact" type="button"
              onClick={props.onReviewCV}>Review CV</button>
            <button className="outline-btn compact" type="button"
              disabled={props.uploading} onClick={props.onUpload}>Replace CV</button>
          </div>
        </details>
        {props.mode && !showMethodPicker ? <button type="button"
          className="outline-btn compact"
          onClick={() => setShowMethodPicker(true)}>
          Change method · {MODE_INFO[props.mode].title}
        </button> : null}
      </div> : null}
    </section>
    <section className="panel flow-cv" id="smartploy-flow-cv" hidden={props.cv.present}>
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 1 OF 4</p>
        <h2>Start with your CV</h2>
        <p>Upload PDF/DOCX (up to 5 MB) or create a CV here.</p>
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

    <section id="smartploy-flow-choice" hidden={!props.cv.present || (!!props.mode && !showMethodPicker)} className={"panel flow-choice" +
      (!props.cv.present ? " flow-choice-locked" : !props.mode ? " flow-choice-needed" : "")}
      aria-labelledby="flow-choice-title">
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 2 OF 4 · YOUR DECISION</p>
        <h2 id="flow-choice-title">Choose how to apply</h2>
        <p>Select one. You remain in control of submission.</p>
      </div></div>
      {!props.cv.present ? <div className="flow-decision flow-cv-required" role="status">
        <CircleHelp size={20} aria-hidden="true"/>
        <p id="flow-choose-require-cv"><strong>All three application methods are visible below.</strong>
          {" "}First upload or create your CV in Step 1. The choices become active
          after your CV is saved; no method is preselected.</p>
      </div> : !props.mode ? <div className="flow-decision" role="status">
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
            data-flow-mode={choice}
            className={"flow-mode" + (props.mode === choice ? " selected" : "")}
            aria-pressed={props.mode === choice}
            disabled={!props.cv.present || props.queueBusy || !!queueInFlight.current}
            aria-describedby={!props.cv.present ? "flow-choose-require-cv" : undefined}
            onClick={() => { props.onMode(choice); setShowMethodPicker(false); }}>
            <span className="flow-mode-head">
              <Icon size={23} aria-hidden="true"/>
              <span className="flow-mode-label">{choice.toUpperCase()}</span>
              <span className="flow-mode-choice">{props.mode === choice ? "Selected" : "Choose"}</span>
            </span>
            <strong>{MODE_INFO[choice].title}</strong>
            <small>{MODE_INFO[choice].summary}</small>

          </button>;
        })}
      </div>
      {props.cv.present && props.mode === "assisted" ? <fieldset className="flow-assistance">
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
      {props.cv.present && props.mode === "automatic" ? <div className="flow-boundary" role="note">
        <ShieldCheck size={20} aria-hidden="true"/>
        <p><strong>Prepare first, apply after review.</strong>{" "}
          SmartPloy saves a CV and letter for each selected job.
          Review documents in My applications, then fill the employer form.
          Nothing is submitted automatically.</p>
      </div> : null}
    </section>
    <section className="panel flow-matches" id="smartploy-flow-matches"
      hidden={!props.cv.present || !props.mode || showMethodPicker}>
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 3 OF 4</p><h2>Jobs from your CV</h2>
        <p>Choose a current vacancy to prepare its application.</p>
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
              <p>{props.mode === "automatic" ? "Select jobs, then prepare and review their documents." :
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
        {props.mode === "automatic" && results && !loading ? (
          <div className="flow-quick-private-start"
            aria-label="Quick CV-matched private application preparation">
            <div className="flow-quick-copy">
              <strong>Prepare matching drafts now</strong>
              <p>SmartPloy can prepare up to {AUTOAPPLY_SELECTION_LIMIT} loaded, current
                role-title matches as private drafts with agents in one action.
                Review the exact jobs in the confirmation first. No employer is contacted.</p>
              {quickDraftKeys.length === 0 ?
                <p>No safe title-matched vacancies are loaded. Review jobs individually
                  or adjust your CV and search. Weak skill matches are not bulk-selected.</p> : null}
            </div>
            <button type="button" className="navy-btn"
              disabled={!quickDraftKeys.length || selected.length > 0 || !!batchResult ||
                loading || paging || queryPending || !!error || staleSelectionCount > 0 ||
                props.queueBusy || !!queueInFlight.current || accessInterrupted}
              onClick={prepareCVMatchedDraftsNow}>
              {props.queueBusy ? "Preparing private drafts…" :
                selected.length ? "Use your selected jobs below" :
                "Prepare " + quickDraftKeys.length + " private draft" +
                (quickDraftKeys.length === 1 ? "" : "s") + " now"}
              <ArrowRight size={16} aria-hidden="true"/>
            </button>
          </div>
        ) : null}
        {props.mode === "automatic" ? <div className="flow-queue" id="smartploy-flow-queue">
          <strong>{selected.length} of {AUTOAPPLY_SELECTION_LIMIT} vacancies selected</strong>
          <p>Prepare a CV and letter for each selected job. Review before applying.</p>
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
          <p className="flow-shortlist-note">Only current, linked CV-title matches are selected. Review each before preparing.</p>
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
    <section className="panel flow-next" id="smartploy-flow-next"
      hidden={!batchResult?.preparedKeys.length}>
      <div className="panel-heading"><div>
        <p className="section-kicker">STEP 4 OF 4</p><h2>Continue your applications</h2>
        <p>Your private documents are ready for review. Nothing has been sent.</p>
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
