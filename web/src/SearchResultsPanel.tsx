import { useMemo, useState } from "react";
import { ArrowRight, ArrowUpRight, BriefcaseBusiness, ChevronDown, Globe2, MapPin, Search, SlidersHorizontal, Target } from "lucide-react";
import type { SearchResults, SearchJobCard } from "./types";
import { listingObservationLabels, safeExternalJobUrl, scoreBand, sectorLabel, type SectorFilter, type DisplayMode } from "./lib";

function JobCard(props: {
  item: SearchJobCard; displayMode: DisplayMode; busy: boolean; onPrepare: () => void;
  onChooseFlow?: () => void;
}) {
  const { item } = props;
  const [showWhy, setShowWhy] = useState(false);
  const job = item.job;
  const hasScore = typeof item.preference_score === "number";
  const sourceDates = listingObservationLabels(job.posted_at, job.first_seen_at, job.last_seen_at);
  const postingUrl = safeExternalJobUrl(job.application_url);
  return <article className="job-item search-result-card">
    <div className="job-avatar" aria-hidden="true">{(job.company || "J").slice(0,1).toUpperCase()}</div>
    <div className="job-details">
      <div className="job-title-line">
        <h3>{job.role_title}</h3>
        {hasScore ? <span className={"score-chip " + scoreBand(item.preference_score ?? 0)}>
          <Target size={13}/> {item.preference_score}% search match
        </span> : null}
      </div>
      <p className="job-byline"><strong>{job.company || "Employer"}</strong>
        {job.location ? <span><MapPin size={13}/>{job.location}</span> : null}
        {job.work_mode && job.work_mode !== "review" ? <span>{job.work_mode}</span> : null}
      </p>
      <div className="job-meta">
        <span className="quiet-chip">{item.lane === "all" ? "General listing" :
          item.lane === "recommended" ? "Matches search targets" : "Explore another role"}</span>
        <span>{sectorLabel(job.employer_sector)}</span>
        {job.opportunity_kind && job.opportunity_kind !== "job" ?
          <span className="quiet-chip">{job.opportunity_kind === "internship" ?
            "Internship" : job.opportunity_kind === "traineeship" ?
            "Traineeship" : "Graduate role"}</span> : null}
        <span>{sourceDates.origin}</span>
        <span>{sourceDates.observation}</span>
        {sourceDates.caution ? <span role="note" className="source-observation-caution">{sourceDates.caution}</span> : null}
        {job.source_attribution ? <span>· {job.source_attribution}</span> : null}
      </div>
      {hasScore && props.displayMode === "heatmap" ? <div
        className={"match-meter " + scoreBand(item.preference_score ?? 0)}>
        <span style={{width: Math.min(100, Math.max(0, item.preference_score ?? 0)) + "%"}} />
      </div> : null}
      {hasScore && showWhy ? <div className="job-expanded">
        <strong>Why this was shown</strong>
        {item.reasons.length ? <ul>{item.reasons.map((text) => <li key={text}>{text}</li>)}</ul>
        : <p>Few stated criteria align with the details available in this job.</p>}
        {item.unknown_fields.length ? <p className="muted">Not verified from the posting: {item.unknown_fields.join("; ")}.</p> : null}
        {item.mismatched_fields?.length ? <p className="muted">Differences from your preferences: {item.mismatched_fields.join("; ")}.</p> : null}
        <small>A search match is not a verified skills or eligibility assessment.</small>
      </div> : null}
    </div>
    <div className="job-buttons">
      {hasScore ? <button type="button" className="text-btn" onClick={() => setShowWhy(!showWhy)}>
        {showWhy ? "Hide explanation" : "Why shown"} <ChevronDown size={13}/>
      </button> : null}
      {postingUrl ? <a href={postingUrl} className="outline-btn compact"
        target="_blank" rel="noopener noreferrer">Job posting <ArrowUpRight size={14}/></a> :
        <span className="muted">Employer link unavailable — verify with the source.</span>}
      {props.onChooseFlow ? <button type="button" className="navy-btn compact"
        onClick={props.onChooseFlow} disabled={!job.source_current}>
        Manual / AutoApply <ArrowRight size={15}/>
      </button> : null}
      <button type="button" className="outline-btn compact" onClick={props.onPrepare} disabled={props.busy || !job.source_current}>
        {props.busy ? "Opening…" : "Prepare documents"} <ArrowRight size={15}/>
      </button>
    </div>
  </article>;
}

export default function SearchResultsPanel(props: {
  data: SearchResults | null;
  search: string;
  sector: SectorFilter;
  onSector: (value: SectorFilter) => void;
  view: "top" | "possible";
  onView: (value: "top" | "possible") => void;
  displayMode: DisplayMode;
  onToggleDisplay: () => void;
  currentPage: "dashboard" | "jobs";
  busyKey: string;
  onPrepare: (canonicalKey: string) => void;
  onChooseFlow?: (canonicalKey: string) => void;
  onAllJobs: () => void;
  onChangeCriteria: () => void;
  onChangeMode: (value: "personalized" | "general") => void;
  autoDraftEnabled?: boolean;
  autoDraftWorkerStatus?: "not_configured" | "registered" | "degraded";
  autoDraftBusy?: boolean;
  onAutoDraft?: () => void;
}) {
  const data = props.data;
  const general = data?.mode === "general";
  // General browsing defaults to career-relevant job titles. All
  // occupations remain available without touching the stored source jobs.
  const [careerFocus, setCareerFocus] = useState<"it_planning" | "all">("it_planning");
  const [levelFocus, setLevelFocus] = useState<"junior_unspecified" | "all">("junior_unspecified");
  const [kindFocus, setKindFocus] = useState<"all" | "early_career" | "jobs">("all");
  const all = general ? data?.all_jobs || [] :
    props.view === "top" ? data?.recommendations || [] : data?.broader || [];
  const rows = useMemo(() => {
    const query = props.search.toLocaleLowerCase().trim();
    return all.filter((item) => {
      const sector = item.job.employer_sector || "unknown";
      if (props.sector !== "all" && sector !== props.sector) return false;
      // Published title only: a delivery driver mentioning apps or data
      // in the description is not a relevant technical vacancy.
      if (general && careerFocus === "it_planning" &&
          !["it_data", "planning"].includes(item.job.career_area || "other")) return false;
      // Never infer a junior level from an absent experience label.
      if (general && levelFocus === "junior_unspecified" &&
          item.job.title_experience === "senior") return false;
      // Trainee/graduate labels use published title or ATS employmentType,
      // never user profile or speculative text from the description.
      if (general && kindFocus === "early_career" &&
          !["traineeship", "internship", "graduate"].includes(item.job.opportunity_kind || "job")) return false;
      if (general && kindFocus === "jobs" &&
          item.job.opportunity_kind && item.job.opportunity_kind !== "job") return false;
      return !query || [item.job.role_title, item.job.company, item.job.location].some(
        (field) => (field || "").toLocaleLowerCase().includes(query)
      );
    });
  }, [all, props.sector, props.search, general, careerFocus, levelFocus, kindFocus]);
  const shown = props.currentPage === "dashboard" ? rows.slice(0, 8) : rows;
  return <section className="panel jobs-panel">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">{general ? "EXPLORE FINLAND" : "PERSONALIZED DISCOVERY"}</p>
        <h2>{props.currentPage === "jobs" ? general ? "IT, data & planning jobs in Finland" : "Opportunities for your goals" :
          general ? "IT & planning opportunities across Finland" : "Recommended opportunities"}</h2>
        <p>{general ? "Browse published vacancies across Finland by career category and experience level. No private profiling." :
          "Ranked by the search criteria you chose — not a verified qualification score."}</p>
      </div>
      {props.currentPage === "dashboard" ? <button className="text-link" onClick={props.onAllJobs} type="button">
        View all jobs <ArrowRight size={15}/></button> : null}
    </div>
    {!general && props.autoDraftEnabled && props.onAutoDraft ? <div className="studio-packet-fallback"
      aria-label="Automatic application drafts">
      <strong>IT job shortlist is on</strong>
      {props.autoDraftWorkerStatus === "registered" ? <p>
        A background draft task is registered on this server. It can prepare private matched drafts
        while your browser is closed, subject to worker health and your approved CV evidence.
        No employer application is submitted automatically.
      </p> : props.autoDraftWorkerStatus === "degraded" ? <p role="status">
        Background job preparation has reported failures. Some accounts may not have been checked.
        You can still run an immediate private scan; no employer application is submitted automatically.
      </p> : <p role="status">
        You opted into local application drafts, but background scheduling is not confirmed on this
        server. Automatic checks should not be assumed to run with your browser closed.
        You can still prepare matching private drafts now.
      </p>}
      <button type="button" className="secondary-btn" disabled={props.autoDraftBusy}
        onClick={props.onAutoDraft}>
        {props.autoDraftBusy ? "Checking matches…" : "Find and prepare matching drafts now"}
      </button>
    </div> : null}
    <div className="search-mode-bar" role="group" aria-label="Search experience">
      <div className="search-mode-choices">
        <button type="button" className={!general ? "active" : ""}
          onClick={() => props.onChangeMode("personalized")}><SlidersHorizontal size={15}/> Personalized</button>
        <button type="button" className={general ? "active" : ""}
          onClick={() => props.onChangeMode("general")}><Globe2 size={15}/> General search</button>
      </div>
      <button type="button" className="text-link" onClick={props.onChangeCriteria}>
        <SlidersHorizontal size={15}/> Edit criteria
      </button>
    </div>
    <div className="job-filter-bar">
      {!general ? <div className="tabs" role="group" aria-label="Match lists">
        <button type="button" className={props.view === "top" ? "active" : ""}
          onClick={() => props.onView("top")}>Recommended ({data?.recommendations.length || 0})</button>
        <button type="button" className={props.view === "possible" ? "active" : ""}
          onClick={() => props.onView("possible")}>Explore more ({data?.broader.length || 0})</button>
      </div> : <div className="general-job-count">
        <Search size={15}/> {data?.available_count ?? 0} current job listings
      </div>}
      <div className="filter-right">
        {general ? <><select aria-label="Career focus" value={careerFocus}
          onChange={(event) => setCareerFocus(event.target.value as "it_planning" | "all")}>
          <option value="it_planning">IT, data & planning</option>
          <option value="all">All occupations</option>
        </select>
        <select aria-label="Experience focus" value={levelFocus}
          onChange={(event) => setLevelFocus(event.target.value as "junior_unspecified" | "all")}>
          <option value="junior_unspecified">Junior + level unspecified</option>
          <option value="all">All experience levels</option>
        </select>
        <select aria-label="Opportunity type" value={kindFocus}
          onChange={(event) => setKindFocus(event.target.value as "all" | "early_career" | "jobs")}>
          <option value="all">Jobs and traineeships</option>
          <option value="early_career">Trainee, internship & graduate</option>
          <option value="jobs">Regular jobs</option>
        </select></> : null}
        <select aria-label="Employer sector" value={props.sector}
          onChange={(event) => props.onSector(event.target.value as SectorFilter)}>
          <option value="all">All sectors</option><option value="public">Public</option>
          <option value="private">Private</option><option value="unknown">Other</option>
        </select>
        {!general ? <button type="button" className="icon-btn" aria-label="Toggle score heatmap"
          onClick={props.onToggleDisplay}><Target size={18}/></button> : null}
      </div>
    </div>
    {general ? <p className="muted" role="status">
      Showing {rows.length} of {data?.available_count ?? 0} current listings.
      {careerFocus === "it_planning" ? " Unrelated driving and other titles are hidden in this view, not deleted." : " All occupations selected."}
      {levelFocus === "junior_unspecified" ? " Senior-labelled titles are hidden; missing experience labels are not treated as verified junior jobs." : ""}
    </p> : null}
    {general ? <section className="studio-packet-fallback" aria-label="Additional Finland job sources">
      <strong>Explore more Finland-wide vacancies</strong>
      <p>SmartPloy doesn't yet ingest Duunitori, Työmarkkinatori or LinkedIn listings automatically.
        These links open their independent searches; their jobs are not counted above or used for unattended applications.</p>
      <div className="row-actions">
        <a href="https://duunitori.fi/tyopaikat?haku=data%20engineer" target="_blank"
          rel="noopener noreferrer" className="text-link">Duunitori <ArrowUpRight size={15}/></a>
        <a href="https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat" target="_blank"
          rel="noopener noreferrer" className="text-link">Työmarkkinatori <ArrowUpRight size={15}/></a>
        <a href="https://www.linkedin.com/jobs/search/?keywords=junior%20data%20engineer&location=Finland"
          target="_blank" rel="noopener noreferrer" className="text-link">LinkedIn <ArrowUpRight size={15}/></a>
      </div>
    </section> : null}
    <div className="job-list">
      {shown.map((item) => <JobCard key={item.canonical_key} item={item}
        displayMode={props.displayMode}
        busy={props.busyKey === item.canonical_key}
        onPrepare={() => props.onPrepare(item.canonical_key)}
        onChooseFlow={props.onChooseFlow ? () => props.onChooseFlow!(item.canonical_key) : undefined}/>)}
      {!shown.length ? <div className="empty-state">
        <BriefcaseBusiness size={30}/>
        <h3>{general ? "No jobs for these filters" : props.view === "top" ?
          "No recommended roles in the current sources yet" : "No more jobs for these filters"}</h3>
        <p>{general ? "Try All occupations, All experience levels, another keyword or employer sector. Additional sources may require authorization." :
          "Adjust your titles, location, language or filters in Settings. You can also explore every current job with General search."}</p>
        <button type="button" className="secondary-btn" onClick={props.onChangeCriteria}>
          Adjust search criteria <ArrowRight size={15}/>
        </button>
      </div> : null}
      {props.currentPage === "dashboard" && rows.length > 8 ? <button type="button"
        className="secondary-btn search-more" onClick={props.onAllJobs}>
        See all {rows.length} jobs <ArrowRight size={15}/>
      </button> : null}
    </div>
  </section>;
}
