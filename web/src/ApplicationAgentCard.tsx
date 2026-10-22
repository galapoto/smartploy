import { useCallback, useEffect, useState } from "react";
import { BellRing, CheckCircle2, Clock3, PauseCircle, PlayCircle, RefreshCw, ShieldCheck, StopCircle } from "lucide-react";
import {
  changeApplicationAgent, createApplicationAgent,
  getApplicationAgent, getApplicationAgents
} from "./api";
import type { ApplicationAgent, ApplicationAgentEvent } from "./types";

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
  const [reload, setReload] = useState(0);

  const refresh = useCallback(() => setReload((previous) => previous + 1), []);

  useEffect(() => {
    let active = true;
    setAgent(null);
    setEvents([]);
    setError("");
    setLoading(true);
    void (async () => {
      try {
        await props.verifyAccount();
        const list = await getApplicationAgents();
        await props.verifyAccount();
        if (!active) return;
        const selected = list.agents.find((item) => item.workspace_id === props.workspaceId) || null;
        if (selected) {
          const detailed = await getApplicationAgent(selected.agent_id);
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

  return <section className="studio-ai-card" aria-label="Your job application agent">
    <div className="studio-ai-heading">
      <span className="studio-ai-icon"><BellRing size={19} /></span>
      <div><strong>Application agent · Agent Zero</strong>
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
    <p className="studio-ai-privacy">Agent Zero stores only case progress and safe
      reminders. Its model calls and external actions are disabled.</p>
  </section>;
}
