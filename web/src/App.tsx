import { useCallback, useEffect, useMemo, useState } from "react";
import { getApplications, getDashboard, getHealth, prepareJob } from "./api";
import {
  filterBySector,
  formatCadence,
  formatState,
  queueLabel,
  relativeFreshness,
  relativeSchedule,
  scoreBand,
  sectorLabel,
  type DisplayMode,
  type SectorFilter
} from "./lib";
import type {
  ApplicationRecord,
  Dashboard,
  HealthResponse,
  RankingCard
} from "./types";

type MatchView = "top" | "possible";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function ScoreBadge(props: { label: string; score: number; mode: DisplayMode }) {
  const klass = props.mode === "heatmap" ? scoreBand(props.score) : "numeric";
  return (
    <div className={cx("score-badge", klass)}>
      <span>{props.label}</span>
      <strong>{props.score}%</strong>
    </div>
  );
}

function Breakdown(props: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(props.values);
  if (!entries.length) return null;
  return (
    <div className="breakdown">
      <h4>{props.title}</h4>
      {entries.map(([key, value]) => (
        <div className="breakdown-row" key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <b>{value}%</b>
        </div>
      ))}
    </div>
  );
}

function MatchCard(props: {
  item: RankingCard;
  displayMode: DisplayMode;
  expanded: boolean;
  preparing: boolean;
  onToggle: () => void;
  onPrepare: () => void;
}) {
  const item = props.item;
  const job = item.job;
  const sector = job?.employer_sector ?? "unknown";
  const cardBand = props.displayMode === "heatmap" ? scoreBand(item.fit_score) : "";

  return (
    <article className={cx("job-card", cardBand)}>
      <div className="job-card-top">
        <div className="job-identity">
          <div className="pill-row">
            <span className={cx("queue-pill", "queue-" + item.queue)}>{queueLabel(item.queue)}</span>
            <span className="sector-pill">{sectorLabel(sector)}</span>
            {job?.work_mode ? <span className="sector-pill">{job.work_mode}</span> : null}
          </div>
          <h3>{job?.role_title ?? "Unknown role"}</h3>
          <p className="company-line">
            {job?.company ?? "Unknown employer"}
            {job?.location ? <span> · {job.location}</span> : null}
          </p>
          <p className="freshness">
            {relativeFreshness(job?.posted_at || job?.first_seen_at || "")}
            {job?.source_ids?.length ? <span> · {job.source_ids.join(", ")}</span> : null}
          </p>
          {job?.source_attribution ? (
            <p className="freshness">Source: {job.source_attribution}</p>
          ) : null}
        </div>
        <div className="score-pair">
          <ScoreBadge label="Fit" score={item.fit_score} mode={props.displayMode} />
          <ScoreBadge label="Priority" score={item.priority_score} mode={props.displayMode} />
        </div>
      </div>

      <div className="match-evidence">
        {item.matched_requirements.slice(0, 5).map((match) => (
          <span className="match-chip" key={match}>✓ {match}</span>
        ))}
        {item.mandatory_gaps.slice(0, 3).map((gap) => (
          <span className="gap-chip" key={gap}>! {gap}</span>
        ))}
      </div>

      <div className="job-actions">
        <button className="button secondary" type="button" onClick={props.onToggle}>
          {props.expanded ? "Hide analysis" : "Analyse match"}
        </button>
        {job?.application_url ? (
          <a className="button secondary" href={job.application_url} target="_blank" rel="noreferrer">
            Open job
          </a>
        ) : null}
        {item.prepare_recommended && job?.ai_preparation_allowed !== false ? (
          <button
            className="button primary"
            type="button"
            onClick={props.onPrepare}
            disabled={props.preparing}
          >
            {props.preparing ? "Preparing…" : "Prepare application"}
          </button>
        ) : null}
        {item.prepare_recommended && job?.ai_preparation_allowed === false ? (
          <span className="gap-chip">AI preparation restricted by source terms</span>
        ) : null}
      </div>

      {props.expanded ? (
        <div className="analysis-panel">
          <div className="analysis-grid">
            <Breakdown title="Fit breakdown" values={item.fit_breakdown} />
            <Breakdown title="Priority breakdown" values={item.priority_breakdown} />
          </div>
          <div className="gap-lists">
            <div>
              <h4>Mandatory gaps</h4>
              {item.mandatory_gaps.length ? (
                <ul>{item.mandatory_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
              ) : <p className="muted">No detected mandatory gaps.</p>}
            </div>
            <div>
              <h4>Preferred gaps</h4>
              {item.preferred_gaps.length ? (
                <ul>{item.preferred_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
              ) : <p className="muted">No detected preferred gaps.</p>}
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function StatCard(props: { label: string; value: number | string; hint: string }) {
  return (
    <div className="stat-card">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <small>{props.hint}</small>
    </div>
  );
}

export default function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("heatmap");
  const [sector, setSector] = useState<SectorFilter>("all");
  const [view, setView] = useState<MatchView>("top");
  const [expanded, setExpanded] = useState("");
  const [preparing, setPreparing] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const result = await Promise.all([getDashboard(), getApplications(), getHealth()]);
      setDashboard(result[0]);
      setApplications(result[1].applications);
      setHealth(result[2]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load Smartploy.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 60000);
    return () => window.clearInterval(timer);
  }, [load]);

  const visibleMatches = useMemo(() => {
    if (!dashboard) return [];
    const items = view === "top" ? dashboard.top_matches : dashboard.possible_matches;
    return filterBySector(items, sector);
  }, [dashboard, sector, view]);

  async function onPrepare(item: RankingCard) {
    setPreparing(item.canonical_key);
    setNotice("");
    try {
      const result = await prepareJob(item.canonical_key);
      setNotice(
        "Application package " + result.package_id + " is " + formatState(result.status) + "."
      );
      await load(true);
    } catch (exc) {
      setNotice(exc instanceof Error ? exc.message : "Application preparation failed.");
    } finally {
      setPreparing("");
    }
  }

  if (loading && !dashboard) {
    return (
      <main className="center-state">
        <div className="loader" />
        <p>Loading Smartploy…</p>
      </main>
    );
  }

  if (error && !dashboard) {
    return (
      <main className="center-state">
        <div className="brand-mark">S</div>
        <h1>Smartploy is unavailable</h1>
        <p>{error}</p>
        <button className="button primary" type="button" onClick={() => void load()}>
          Retry
        </button>
      </main>
    );
  }

  if (!dashboard) return null;

  const apps = dashboard.applications;
  const approvedFacts = Number(dashboard.profile.approved_fact_count ?? 0);
  const sectorValues: SectorFilter[] = ["all", "public", "private", "unknown"];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div>
            <strong>Smartploy</strong>
            <span>Job intelligence for Finland</span>
          </div>
        </div>
        <div className="header-actions">
          <span className={cx("connection", health?.obumai_configured ? "online" : "offline")}>
            <i />
            {health?.obumai_configured ? "ObumAI connected" : "ObumAI not configured"}
          </span>
          <button
            className="button secondary"
            type="button"
            onClick={() => void load(true)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <main className="dashboard">
        <section className="hero">
          <div>
            <span className="eyebrow">Your ranked job market</span>
            <h1>Apply where your evidence is strongest.</h1>
            <p>
              Smartploy ranks fresh opportunities by verified fit and career priority, then uses
              ObumAI to prepare evidence-backed application drafts.
            </p>
          </div>
          <div className="profile-readiness">
            <span>Profile evidence</span>
            <strong>
              {dashboard.profile.ready ? approvedFacts + " approved facts" : "Needs setup"}
            </strong>
            <small>
              {dashboard.profile.ready
                ? "Used for scoring and drafting"
                : "Import an approved profile before scoring"}
            </small>
          </div>
        </section>

        {!dashboard.external_actions_authorized ? (
          <div className="truth-banner">
            <strong>Preparation mode.</strong>
            <span> Smartploy can prepare application packages, but final submission is not yet authorized.</span>
          </div>
        ) : null}

        {notice ? <div className="notice">{notice}</div> : null}
        {error ? <div className="notice error">{error}</div> : null}

        <section className="stats-grid" aria-label="Pipeline summary">
          <StatCard
            label="Top matches"
            value={dashboard.top_matches.length}
            hint="Exceptional, auto-prepare and review"
          />
          <StatCard
            label="Possible matches"
            value={dashboard.possible_matches.length}
            hint="Worth another look"
          />
          <StatCard
            label="Awaiting review"
            value={apps.awaiting_review}
            hint="Prepared, not submitted"
          />
          <StatCard
            label="Actually submitted"
            value={apps.actually_submitted}
            hint="Requires external evidence"
          />
        </section>

        <section className="workspace">
          <div className="workspace-main">
            <div className="section-header">
              <div>
                <span className="eyebrow">Opportunity queue</span>
                <h2>{view === "top" ? "Highest-value jobs" : "Possible matches"}</h2>
              </div>
              <div className="controls">
                <div className="segmented" aria-label="Match list">
                  <button
                    className={view === "top" ? "active" : ""}
                    onClick={() => setView("top")}
                    type="button"
                  >
                    Top
                  </button>
                  <button
                    className={view === "possible" ? "active" : ""}
                    onClick={() => setView("possible")}
                    type="button"
                  >
                    Possible
                  </button>
                </div>
                <div className="segmented" aria-label="Score display">
                  <button
                    className={displayMode === "heatmap" ? "active" : ""}
                    onClick={() => setDisplayMode("heatmap")}
                    type="button"
                  >
                    Heatmap
                  </button>
                  <button
                    className={displayMode === "percentage" ? "active" : ""}
                    onClick={() => setDisplayMode("percentage")}
                    type="button"
                  >
                    %
                  </button>
                </div>
              </div>
            </div>

            <div className="sector-filters" aria-label="Employer sector">
              {sectorValues.map((value) => (
                <button
                  className={sector === value ? "active" : ""}
                  key={value}
                  onClick={() => setSector(value)}
                  type="button"
                >
                  {value === "all" ? "All sectors" : value[0].toUpperCase() + value.slice(1)}
                </button>
              ))}
            </div>

            <div className="job-list">
              {visibleMatches.length ? (
                visibleMatches.map((item) => (
                  <MatchCard
                    key={item.canonical_key}
                    item={item}
                    displayMode={displayMode}
                    expanded={expanded === item.canonical_key}
                    preparing={preparing === item.canonical_key}
                    onToggle={() => setExpanded(expanded === item.canonical_key ? "" : item.canonical_key)}
                    onPrepare={() => void onPrepare(item)}
                  />
                ))
              ) : (
                <div className="empty-state">
                  <h3>No jobs in this view</h3>
                  <p>Try another sector or wait for the next healthy source poll.</p>
                </div>
              )}
            </div>
          </div>

          <aside className="workspace-side">
            <section className="side-card">
              <div className="side-heading">
                <h3>Continuous worker</h3>
                <span>{dashboard.worker.count}</span>
              </div>
              {!dashboard.worker.configured ? (
                <p className="muted">Worker is not configured in this environment.</p>
              ) : !dashboard.worker.ready ? (
                <div className="worker-warning">
                  <strong>Worker status unavailable</strong>
                  <small>{dashboard.worker.error || "Scheduler schema is not ready."}</small>
                </div>
              ) : dashboard.worker.tasks.length ? (
                <div className="worker-list">
                  {dashboard.worker.tasks.map((task) => (
                    <div className="worker-row" key={task.task_id}>
                      <div>
                        <strong>{formatState(task.task_id)}</strong>
                        <small>
                          {task.lease_active
                            ? "Running"
                            : relativeSchedule(task.next_run_at)}
                          {" · "}
                          {formatCadence(task.cadence_seconds)}
                        </small>
                      </div>
                      <span
                        className={cx(
                          "health-status",
                          task.lease_active ? "status-running" : "status-" + task.last_status
                        )}
                      >
                        {task.lease_active ? "running" : task.last_status}
                      </span>
                      {task.consecutive_failures ? (
                        <p>
                          {task.consecutive_failures} consecutive failure
                          {task.consecutive_failures === 1 ? "" : "s"}
                          {task.last_error ? " · " + task.last_error : ""}
                        </p>
                      ) : task.last_error ? (
                        <p>{task.last_error}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">Worker is ready but no tasks are registered yet.</p>
              )}
            </section>

            <section className="side-card">
              <div className="side-heading">
                <h3>Source health</h3>
                <span>{dashboard.source_health.length}</span>
              </div>
              {dashboard.source_health.length ? (
                dashboard.source_health.map((source) => (
                  <div className="health-row" key={source.source_id}>
                    <div>
                      <strong>{source.source_id}</strong>
                      <small>{source.last_item_count} items last run</small>
                    </div>
                    <span className={cx("health-status", "status-" + source.status)}>
                      {source.status}
                    </span>
                    {source.last_error ? <p>{source.last_error}</p> : null}
                  </div>
                ))
              ) : (
                <p className="muted">No source polls recorded yet.</p>
              )}
            </section>

            <section className="side-card">
              <div className="side-heading">
                <h3>Applications</h3>
                <span>{applications.length}</span>
              </div>
              {applications.length ? (
                applications.map((application) => (
                  <div className="application-row" key={application.application_id}>
                    <div>
                      <strong>{formatState(application.state)}</strong>
                      <small>{application.application_id}</small>
                    </div>
                    <span>{application.has_been_submitted ? "Submitted" : "Not submitted"}</span>
                  </div>
                ))
              ) : (
                <p className="muted">No application records yet.</p>
              )}
            </section>

            <section className="side-card">
              <h3>Preparation pipeline</h3>
              <div className="pipeline-list">
                {Object.entries(dashboard.preparation_counts).length ? (
                  Object.entries(dashboard.preparation_counts).map(([state, count]) => (
                    <div key={state}>
                      <span>{formatState(state)}</span>
                      <strong>{count}</strong>
                    </div>
                  ))
                ) : (
                  <p className="muted">No draft packages yet.</p>
                )}
              </div>
            </section>
          </aside>
        </section>
      </main>
    </div>
  );
}
