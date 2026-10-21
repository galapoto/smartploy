import { useState } from "react";
import type {
  JobAIProcessingConsent, JobAIProcessingConsentEvent, SavedJob
} from "./types";

interface Props {
  jobs: SavedJob[];
  consents: JobAIProcessingConsent[];
  events: JobAIProcessingConsentEvent[];
  status: "ready" | "unavailable";
  busy: boolean;
  onGrant: (jobKey: string) => Promise<void>;
  onRevoke: (consentId: string) => Promise<void>;
}

/** Settings-only explicit consent. Never invokes a model or an employer API. */
export default function AIConsentSettings({
  jobs, consents, events, status, busy, onGrant, onRevoke
}: Props) {
  const [selected, setSelected] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const permitted = jobs.filter((item) =>
    item.source_current && item.job.ai_preparation_allowed
  );
  const labels = new Map(jobs.map((item) => [
    item.canonical_key,
    item.job.role_title + " — " + item.job.company
  ]));
  const available = status === "ready";

  return <section className="panel settings-panel" aria-label="AI processing permissions">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">YOUR DATA / OBUMAI</p>
        <h2>AI processing permissions</h2>
        <p>Choose exactly which job can use your currently approved career evidence for an
          ObumAI application draft. Changing the job or approved evidence requires new consent.</p>
      </div>
    </div>
    <p className="muted">This saves permission only. Automated AI preparation is not enabled
      in production and no application will be sent to an employer.</p>
    {available ? <>
      <div className="dialog-form">
        <label htmlFor="ai-consent-job">Choose a currently approved job
          <select id="ai-consent-job" value={selected} disabled={busy}
            onChange={(event) => { setSelected(event.target.value); setAcknowledged(false); }}>
            <option value="">Select a job</option>
            {permitted.map((item) => <option key={item.canonical_key}
              value={item.canonical_key}>
              {item.job.role_title} — {item.job.company}
            </option>)}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={acknowledged} disabled={busy}
            onChange={(event) => setAcknowledged(event.target.checked)} />
          I explicitly allow ObumAI to process my approved career evidence and this
          selected job posting to prepare a draft. This does not authorize employer submission.
        </label>
        <button type="button" className="primary-btn"
          disabled={busy || !selected || !acknowledged}
          onClick={() => {
            if (!selected || !acknowledged) return;
            const jobKey = selected;
            setAcknowledged(false);
            void onGrant(jobKey);
          }}>
          Save job-specific permission
        </button>
      </div>
      {!permitted.length ? <p className="muted">
        No current jobs are approved for AI forwarding. Browse normally without an AI grant.
      </p> : null}
      <h3>Saved permissions</h3>
      {!consents.length ? <p className="muted">No permission recorded. AI processing
        remains off by default.</p> : <div className="applications-list">
        {consents.map((item) => <div className="application-list-row" key={item.consent_id}>
          <div>
            <strong>{labels.get(item.canonical_key) || "Previously reviewed job"}</strong>
            <small>{item.active ? "Saved for a specific job and evidence snapshot" :
              "Withdrawn"} · Revision {item.revision}</small>
          </div>
          {item.active ? <button type="button" className="outline-btn"
            disabled={busy} onClick={() => void onRevoke(item.consent_id)}>
            Withdraw permission
          </button> : <span className="state-pill waiting">Withdrawn</span>}
        </div>)}
      </div>}
      <h3>Consent history</h3>
      {!events.length ? <p className="muted">No recorded grant or withdrawal events.</p> :
        <div className="applications-list">{events.slice(0, 10).map((item) =>
          <div className="application-list-row" key={item.event_id}>
            <strong>{item.event_type === "granted" ? "Permission granted" : "Permission withdrawn"}</strong>
            <small>Revision {item.revision} · {item.occurred_at}</small>
          </div>)}</div>}
      <p className="muted">This history records permissions, not AI processing activity.
        Withdrawing blocks future authorization; it cannot erase requests already delivered
        to a processor.</p>
    </> : <p role="status">Permission records are unavailable.
      SmartPloy will not assume consent when the permission service is unavailable.</p>}
  </section>;
}
