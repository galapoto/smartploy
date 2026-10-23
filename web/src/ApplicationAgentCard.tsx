import { useCallback, useEffect, useState } from "react";
import { BellRing, CheckCircle2, Clock3, PauseCircle, PlayCircle, RefreshCw, ShieldCheck, StopCircle } from "lucide-react";
import {
  changeApplicationAgent, createApplicationAgent,
  getApplicationAgent, getApplicationAgentForWorkspace,
  recordApplicationAgentMilestone, recordApplicationAgentFollowup
} from "./api";
import type { ApplicationAgent, ApplicationAgentEvent, ApplicationAgentMilestone } from "./types";

/** In-app-only agent lifecycle; parent checks account identity before/after every request. */
export default function ApplicationAgentCard(props: {
  workspaceId: string;
  expectedUserId: string;
  verifyAccount: () => Promise<void>;
}) {
  const [agent, setAgent] = useState<ApplicationAgent | null>(null);
  const [events, setEvents] = useState<ApplicationAgentEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState("");
  const [milestone, setMilestone] = useState<ApplicationAgentMilestone>("recruiter_replied");
  const [outcomeConfirmed, setOutcomeConfirmed] = useState(false);
  const [reload, setReload] = useState(0);

  const refresh = useCallback(() => setReload((previous) => previous + 1), []);

  useEffect(() => {
    let active = true;
    setAgent(null);
    setEvents([]);
    setError("");
    setOutcomeConfirmed(false);
    setLoading(true);
    void (async () => {
      try {
        await props.verifyAccount();
        const lookup = await getApplicationAgentForWorkspace(props.workspaceId);
        await props.verifyAccount();
        if (!active) return;
        const selected = lookup.agent;
        if (selected) {
          const detailed = await getApplicationAgent(
            selected.agent_id, Math.max(0, selected.revision - 5)
          );
          await props.verifyAccount();
          if (!active) return;
          setAgent(detailed.agent);
          setEvents(detailed.events);
        } else {
          setAgent(null);
          setEvents([]);
        }
        setUnavailable(false);
      } catch {
        // The parent blocks the editor if account identity changed. Do not
        // retain the former account's agent timeline or treat 503 as no agent.
        if (active) {
          setAgent(null);
          setEvents([]);
          setUnavailable(true);
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [props.workspaceId, props.verifyAccount, reload]);

  async function create() {
    if (busy || loading || unavailable || agent) return;
    setBusy(true);
    setError("");
    try {
      await props.verifyAccount();
      await createApplicationAgent(props.workspaceId, props.expectedUserId);
      await props.verifyAccount();
      refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to start the agent.");
    } finally {
      setBusy(false);
    }
  }

  async function act(action: "pause" | "resume" | "close") {
    if (!agent || busy || loading || unavailable) return;
    if (action === "close" && !window.confirm(
      "Close this application agent permanently? It will never wake again. " +
      "This does not withdraw any application from the employer."
    )) return;
    const current = agent;
    setBusy(true);
    setError("");
    try {
      await props.verifyAccount();
      await changeApplicationAgent(
        current.agent_id, action, current.revision, props.expectedUserId
      );
      await props.verifyAccount();
      refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to change the agent.");
    } finally {
      setBusy(false);
    }
  }

  async function reportMilestone() {
    if (!agent || busy || loading || unavailable || !outcomeConfirmed ||
        agent.state === "closed" || agent.workspace_status === "draft") return;
    if (["hired", "rejected"].includes(milestone) && !window.confirm(
      "End this application agent based on your personal report of " + milestone +
      "? It will never wake again. This does not verify the employer outcome."
    )) return;
    const active = agent;
    setBusy(true); setError("");
    try {
      await props.verifyAccount();
      await recordApplicationAgentMilestone(
        active.agent_id, milestone, active.revision, props.expectedUserId
      );
      await props.verifyAccount();
      setOutcomeConfirmed(false);
      refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not record the reported update.");
    } finally {
      setBusy(false);
    }
  }

  async function reportFollowupSent() {
    if (!agent || busy || loading || unavailable || !agent.followup_suggestion ||
        agent.state !== "active") return;
    if (!window.confirm(
      "Confirm that YOU already sent this follow-up outside SmartPloy. " +
      "SmartPloy cannot verify its delivery and will not send anything."
    )) return;
    const active = agent;
    setBusy(true); setError("");
    try {
      await props.verifyAccount();
      await recordApplicationAgentFollowup(
        active.agent_id, active.revision, props.expectedUserId
      );
      await props.verifyAccount();
      refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not record your reported follow-up.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="studio-ai-card" aria-label="Your job application agent">
    <div className="studio-ai-heading">
      <span className="studio-ai-icon"><BellRing size={19} /></span>
      <div><strong>Application agent · follow-up tracking</strong>
        <p>One private agent for this job. It tracks your next steps and keeps an in-app
          activity history. No emails, calls or employer applications are sent by this agent.</p>
      </div>
    </div>
    {loading ? <p role="status"><Clock3 size={15} /> Checking application agent…</p> : null}
    {unavailable && !loading ? <p role="status">
      Agent tracking requires the durable-agent database migration and worker activation.
      Your application editor still works normally.
    </p> : null}
    {!agent && !loading && !unavailable ? (
      <button type="button" className="outline-btn"
        disabled={busy} onClick={() => void create()}>
        <PlayCircle size={16} /> {busy ? "Starting…" : "Start tracking this application"}
      </button>
    ) : null}
    {agent && !loading ? <div>
      <p role="status"><ShieldCheck size={15} /> Status: <strong>{agent.state}</strong>
        {agent.last_woke_at ? " · Last reminder " + new Date(agent.last_woke_at).toLocaleString() : ""}
      </p>
      {agent.state !== "closed" ? <div className="studio-actions">
        {agent.state === "active" ? (
          <button type="button" className="outline-btn compact"
            disabled={busy} onClick={() => void act("pause")}>
            <PauseCircle size={15} /> Pause
          </button>
        ) : (
          <button type="button" className="outline-btn compact"
            disabled={busy} onClick={() => void act("resume")}>
            <PlayCircle size={15} /> Resume
          </button>
        )}
        <button type="button" className="outline-btn compact"
          disabled={busy} onClick={() => void act("close")}>
          <StopCircle size={15} /> End case
        </button>
      </div> : <p><CheckCircle2 size={15} /> Case ended. Existing documents remain available.</p>}
      <div className="studio-info">
        <ShieldCheck size={16}/>
        <div>
          <strong>{agent.workspace_status === "provider_acknowledged"
            ? "Application submission acknowledged by provider"
            : agent.workspace_status === "self_reported_applied"
              ? "Application reported sent by you"
              : "Application is still a draft"}</strong>
          <p>{agent.milestone !== "none"
            ? "Latest milestone: " + agent.milestone.replaceAll("_", " ") +
              " (your report only, not independently verified)."
            : "No recruiter outcome recorded."}
            {agent.next_due_at ? " · Next in-app review " +
              new Date(agent.next_due_at).toLocaleString() : ""}
          </p>
        </div>
      </div>
      {agent.state === "active" &&
      agent.workspace_status !== agent.observed_workspace_status ? (
        <p role="status">Your application status has changed. The case worker
          will reconcile it before suggesting another follow-up.
          No employer action will be taken automatically.</p>
      ) : null}
      {agent.workspace_status === "draft" && agent.state !== "closed" ? (
        <p>First submit or personally report submitting this application using
          the Application Studio controls. Recruiter outcomes and follow-ups
          cannot be recorded against an unsent draft.</p>
      ) : null}
      {agent.workspace_status !== "draft" && agent.state !== "closed" ? (
        <div className="studio-ai-card" aria-label="Record applicant-confirmed recruiter update">
          <strong>What happened with this application?</strong>
          <p>This is your personal report. SmartPloy does not verify recruiter messages.</p>
          <label htmlFor="agent-milestone">Recruiter update</label>
          <select id="agent-milestone" value={milestone}
            onChange={(event) => {
              setMilestone(event.target.value as ApplicationAgentMilestone);
              setOutcomeConfirmed(false);
            }} disabled={busy}>
            <option value="recruiter_replied">Recruiter replied</option>
            <option value="interview">Interview invited or scheduled</option>
            <option value="offer">Offer received</option>
            <option value="rejected">Application rejected — end agent</option>
            <option value="hired">Job accepted / employed — end agent</option>
          </select>
          <label>
            <input type="checkbox" checked={outcomeConfirmed} disabled={busy}
              onChange={(event) => setOutcomeConfirmed(event.target.checked)}/>
            I personally confirm this update
          </label>
          <button type="button" className="outline-btn compact"
            disabled={busy || !outcomeConfirmed}
            onClick={() => void reportMilestone()}>
            <CheckCircle2 size={15}/> Record applicant-reported update
          </button>
        </div>
      ) : null}
      {agent.followup_suggestion ? (
        <div className="studio-ai-card" aria-label="Review follow-up draft">
          <strong>Suggested polite follow-up · {agent.followups_sent}/2 reported sent</strong>
          <p>Review and edit this template in your own email app. No recipient is selected;
            nothing is sent, and SmartPloy cannot verify delivery.</p>
          <textarea aria-label="Follow-up message you may copy" readOnly rows={6}
            value={agent.followup_suggestion}/>
          <button type="button" className="outline-btn compact" disabled={busy}
            onClick={() => void reportFollowupSent()}>
            <CheckCircle2 size={15}/> I already sent a follow-up myself
          </button>
        </div>
      ) : null}
      {events.length > 0 ? (
        <div aria-label="Agent activity">
          <strong>Recent activity</strong>
          <ul>{events.slice(-5).reverse().map((event) =>
            <li key={event.sequence}>
              <Clock3 size={13} /> {event.message}
              <small> · {new Date(event.occurred_at).toLocaleString()}</small>
            </li>
          )}</ul>
        </div>
      ) : null}
      <button type="button" className="outline-btn compact" disabled={busy}
        onClick={refresh}><RefreshCw size={14} /> Refresh activity</button>
    </div> : null}
    {error ? <p role="alert">{error}</p> : null}
    <p className="studio-ai-privacy">Private candidate reports and in-app reminders only.
      model calls and external actions are disabled. SmartPloy never emails recruiters from this card.</p>
  </section>;
}
