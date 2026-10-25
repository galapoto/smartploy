import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, BellRing, Clock3, RefreshCw, ShieldCheck } from "lucide-react";
import { getApplicationAgentInbox } from "./api";
import type { ApplicationAgentAttention, ApplicationAgentInboxItem } from "./types";

/** Private, action-oriented view of the original durable Agent Zero ledger.
 * This view NEVER creates cases, sends messages, or wakes background workers.
 */
const PAGE_SIZE = 25;

const ATTENTION: Record<ApplicationAgentAttention, string> = {
  status_changed: "Submission status changed · check this agent",
  due_review: "Review due · private reminder only",
  draft_review: "Draft ready · not submitted",
  awaiting_response: "Awaiting response · follow-up not yet due",
  paused: "Agent paused",
  closed: "Case closed",
};

function scheduleText(item: ApplicationAgentInboxItem): string {
  const recorded = item.next_due_at ? new Date(item.next_due_at) : null;
  const next = recorded && Number.isFinite(recorded.getTime())
    ? recorded.toLocaleString() : "";
  if (item.state === "closed") return "No further agent reminders";
  if (item.state === "paused") return "Reminders paused by the candidate";
  return next ? "Next private review: " + next : "Next review date unavailable";
}

export default function ApplicationAgentInbox(props: {
  verifyAccount: () => Promise<void>;
  onOpen: (workspaceId: string) => void | Promise<void>;
}) {
  const [items, setItems] = useState<ApplicationAgentInboxItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);

  const load = useCallback(async (offset: number, replace: boolean) => {
    const ticket = ++generation.current;
    setBusy(true);
    setError("");
    try {
      // The server also binds every inbox query to the signed-in OIDC owner.
      // The second check avoids rendering old account data if cookies change
      // while a private GET is in flight.
      await props.verifyAccount();
      const result = await getApplicationAgentInbox(PAGE_SIZE, offset);
      await props.verifyAccount();
      if (ticket !== generation.current) return;
      setItems((previous) => {
        if (replace) return result.items;
        const seen = new Set(previous.map((item) => item.agent_id));
        return [...previous, ...result.items.filter((item) => !seen.has(item.agent_id))];
      });
      setHasMore(result.has_more);
      setNextOffset(result.next_offset);
    } catch (exc) {
      if (ticket !== generation.current) return;
      try { await props.verifyAccount(); } catch { return; }
      if (ticket === generation.current) {
        setError(exc instanceof Error ? exc.message : "Unable to read application agents.");
      }
    } finally {
      if (ticket === generation.current) setBusy(false);
    }
  }, [props.verifyAccount]);

  useEffect(() => {
    void load(0, true);
    return () => { ++generation.current; };
  }, [load]);

  return <section className="agent-inbox" aria-label="Application agent inbox">
    <div className="agent-inbox-heading">
      <div>
        <span className="section-kicker">PRIVATE APPLICATION QUEUE</span>
        <h3><BellRing size={18}/> Your agent inbox</h3>
        <p>Review due cases and applications needing attention. This is not an employer
          inbox or proof that background workers have run.</p>
      </div>
      <button type="button" className="outline-btn compact"
        onClick={() => void load(0, true)} disabled={busy}
        aria-label="Refresh agent inbox">
        <RefreshCw size={15}/> Refresh
      </button>
    </div>
    {error ? <p role="alert" className="studio-alert error">{error}</p> : null}
    {busy && items.length === 0 ? <p role="status"><Clock3 size={14}/>
      Loading private agent priorities…</p> : null}
    {!busy && !error && items.length === 0 ? <p className="muted">
      No tracked application agents yet. Select a job in AutoApply mode or start
      tracking a saved application to build your private queue.
    </p> : null}
    {items.length ? <div className="agent-inbox-list">
      {items.map((item) => <div className="agent-inbox-row" key={item.agent_id}>
        <div className="agent-inbox-copy">
          <strong>{item.role_title} · {item.company}</strong>
          <span className={"agent-inbox-priority priority-" + item.attention_state}>
            {ATTENTION[item.attention_state]}
          </span>
          <small><Clock3 size={12}/> {scheduleText(item)}</small>
          {item.workspace_status === "self_reported_applied" ? <small>
            Application status: personally reported sent, not employer-verified
          </small> : null}
          {item.workspace_status === "provider_acknowledged" ? <small>
            Application status: provider acknowledged submission, not a hiring decision
          </small> : null}
        </div>
        <button type="button" className="outline-btn compact"
          onClick={() => void props.onOpen(item.workspace_id)}
          aria-label={"Open " + item.role_title + " at " + item.company + " application"}>
          Open application <ArrowRight size={15}/>
        </button>
      </div>)}
    </div> : null}
    {hasMore && nextOffset !== null ? <button type="button"
      className="outline-btn compact agent-inbox-more" disabled={busy}
      onClick={() => void load(nextOffset, false)}>
      {busy ? "Loading…" : "Load more application agents"} <ArrowRight size={15}/>
    </button> : null}
    <p className="studio-ai-privacy"><ShieldCheck size={14}/>
      Private case data only. A due review is not a sent email or an employer response.
      Background worker activation has not been verified by this view.</p>
  </section>;
}
