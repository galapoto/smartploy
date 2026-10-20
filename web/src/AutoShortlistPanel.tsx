import { useEffect, useRef, useState } from "react";
import {
  getLocalShortlistSettings, saveLocalShortlistSettings,
  runLocalShortlistNow, getSession
} from "./api";
import type { LocalShortlistSettings, LocalShortlistRun } from "./api";

interface Props {
  expectedUserId: string;
  personalized: boolean;
  onPrepared?: () => void;
}

/** Account-bound, opt-in LOCAL drafts: never employer/ObumAI permissions. */
export default function AutoShortlistPanel({
  expectedUserId, personalized, onPrepared
}: Props) {
  const [settings, setSettings] = useState<LocalShortlistSettings | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [score, setScore] = useState(75);
  const [batch, setBatch] = useState(3);
  const mounted = useRef(false);
  const acting = useRef(false);

  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    setSettings(null); setStatus(""); setError(""); setConsent(false);
    void (async () => {
      try {
        const session = await getSession();
        if (!session.authenticated || session.user_id !== expectedUserId) {
          throw new Error("Your signed-in account changed. Reload before enabling drafts.");
        }
        const item = await getLocalShortlistSettings();
        const again = await getSession();
        if (!again.authenticated || again.user_id !== expectedUserId) {
          throw new Error("Account changed during private shortlist loading.");
        }
        if (!cancelled) {
          setSettings(item); setScore(item.minimum_score); setBatch(item.max_per_cycle);
        }
      } catch (exc) {
        if (!cancelled) setError(
          exc instanceof Error ? exc.message : "Local-draft settings unavailable."
        );
      }
    })();
    return () => { cancelled = true; mounted.current = false; };
  }, [expectedUserId]);

  async function verifyOwner() {
    const session = await getSession();
    if (!session.authenticated || !expectedUserId || session.user_id !== expectedUserId) {
      setSettings(null);
      throw new Error("Your SmartPloy account changed. Reload before creating applications.");
    }
  }

  async function runNow() {
    if (!settings?.enabled || busy || acting.current || !personalized) return;
    acting.current = true; setBusy(true); setError(""); setStatus("");
    try {
      await verifyOwner();
      const run = await runLocalShortlistNow(expectedUserId);
      await verifyOwner();
      if (mounted.current) {
        setStatus(report(run));
        const fresh = await getLocalShortlistSettings();
        await verifyOwner();
        if (mounted.current) {
          setSettings(fresh);
          if (run.created > 0) onPrepared?.();
        }
      }
    } catch (exc) {
      if (mounted.current) setError(
        exc instanceof Error ? exc.message : "Local drafts could not be created."
      );
    } finally { acting.current = false; if (mounted.current) setBusy(false); }
  }

  async function setEnabled(enabled: boolean) {
    if (!settings || busy || acting.current ||
        (enabled && (!personalized || (!settings.enabled && !consent)))) return;
    acting.current = true; setBusy(true); setError(""); setStatus("");
    try {
      await verifyOwner();
      const saved = await saveLocalShortlistSettings({
        enabled, minimum_score:score, max_per_cycle:batch,
        expected_revision:settings.revision,
        acknowledge_local_drafts_only: enabled && consent
      },expectedUserId);
      await verifyOwner();
      if (mounted.current) {
        setSettings(saved); setConsent(false);
        setStatus(enabled
          ? "Automatic local drafts enabled; no employer submission permission."
          : "Automatic draft creation disabled. Existing drafts remain private.");
      }
      // The applicant's explicit first enable immediately prepares their
      // first set of local drafts. No employer or model receives any data.
      if (enabled && !settings.enabled) {
        const run = await runLocalShortlistNow(expectedUserId);
        await verifyOwner();
        const fresh = await getLocalShortlistSettings();
        await verifyOwner();
        if (mounted.current) {
          setSettings(fresh);
          setStatus(report(run));
          if (run.created > 0) onPrepared?.();
        }
      }
    } catch (exc) {
      if (mounted.current) setError(
        exc instanceof Error ? exc.message : "Could not save automatic draft settings."
      );
    } finally { acting.current=false; if (mounted.current) setBusy(false); }
  }

  function report(result: LocalShortlistRun): string {
    if (result.status === "needs_profile") {
      return "Upload your CV or approve career facts first. No draft was created.";
    }
    if (result.status === "needs_preferences") {
      return "Choose personalized job roles and criteria first. No draft was created.";
    }
    return result.created
      ? result.created + " new application drafts prepared for your review. None submitted."
      : "No new qualifying IT-job drafts. Existing drafts are preserved and no job was submitted.";
  }

  return <section className="panel settings-panel" aria-label="Automatic IT-job drafts">
    <div className="panel-heading"><div>
      <p className="section-kicker">JOB DISCOVERY / AUTOMATION</p>
      <h2>Automatically find and prepare IT applications</h2>
      <p>SmartPloy already collects current vacancies. Reuse your saved job
        preferences and approved CV to create review-ready drafts for strong matches.</p>
    </div></div>
    <p className="muted">Off until you enable it. No employer applications are sent,
      no accounts are created on employer sites, and no personal data goes to ObumAI.
      A match score reflects your preferences, not verified qualifications.</p>
    {!settings ? <p role="status">{error || "Loading private automation settings…"}</p> : <>
      <p role="status">{settings.enabled
        ? "Local auto-preparation enabled for this account"
        : "Local auto-preparation disabled"}. {settings.background_worker_enabled
          ? "Background worker configured."
          : "Background scheduling not enabled on this deployment. Run now is available."}</p>
      <div className="dialog-form">
        <label htmlFor="shortlist-score">Minimum preference alignment
          <select id="shortlist-score" value={score} disabled={busy}
            onChange={event => setScore(Number(event.target.value))}>
            {[70,75,80,85,90,95].map(value =>
              <option key={value} value={value}>{value}%</option>)}
          </select>
        </label>
        <label htmlFor="shortlist-batch">New drafts per cycle
          <select id="shortlist-batch" value={batch} disabled={busy}
            onChange={event => setBatch(Number(event.target.value))}>
            {[1,3,5,10].map(value =>
              <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        {!settings.enabled ? <label>
          <input type="checkbox" checked={consent} disabled={busy || !personalized}
            onChange={event => setConsent(event.target.checked)} />
          I authorize automatic LOCAL drafts based on my saved job criteria
          and approved CV. I will review them before any employer submission.
        </label> : null}
      </div>
      {!personalized ? <p role="status">Switch to personalized job search
        and choose IT roles in Settings to enable matching.</p> : null}
      {settings.enabled ?
        <div className="button-row">
          <button className="primary-btn" type="button"
            disabled={busy || !personalized || score !== settings.minimum_score ||
              batch !== settings.max_per_cycle}
            onClick={() => void runNow()}>
            {busy ? "Preparing…" : "Find matching jobs and prepare drafts now"}
          </button>
          <button className="outline-btn" type="button" disabled={busy}
            onClick={() => void setEnabled(false)}>Disable automatic drafts</button>
          {(score !== settings.minimum_score || batch !== settings.max_per_cycle) ?
            <button className="outline-btn" disabled={busy} type="button"
              onClick={() => void setEnabled(true)}>Save new limits</button> : null}
        </div> :
        <button className="primary-btn" type="button"
          disabled={busy || !personalized || !consent}
          onClick={() => void setEnabled(true)}>
          {busy ? "Saving…" : "Enable automatic IT-job drafts"}
        </button>}
      <p className="muted">Last cycle: {settings.last_run_at || "Not run"}.
        {settings.last_run_at ? " Created " + settings.last_created +
          " drafts after inspecting " + settings.last_inspected + " matches." : ""}
        All new drafts are private and require your review.</p>
    </>}
    {settings && error ? <p role="alert">{error}</p> : null}
    {status ? <p role="status">{status}</p> : null}
  </section>;
}
