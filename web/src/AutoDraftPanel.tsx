import { useEffect, useRef, useState } from "react";
import { CheckCircle2, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import {
  getAutoDraftSettings,getSession,saveAutoDraftSettings,scanAutoDrafts
} from "./api";
import type { AutoDraftSettings,AutoDraftScan } from "./api";

/** Candidate-owned on/off switch. Preparing a draft is NEVER submitting it. */
export default function AutoDraftPanel(props: {
  expectedUserId:string;
  authSource:string;
  personalized:boolean;
  onReview:()=>void;
}) {
  const [settings,setSettings]=useState<AutoDraftSettings|null>(null);
  const [minimumScore,setMinimumScore]=useState(75);
  const [maxDrafts,setMaxDrafts]=useState(5);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [result,setResult]=useState<AutoDraftScan|null>(null);
  const pending=useRef(false);
  const owner=props.expectedUserId;
  const supported=!!owner && props.authSource==="oidc";

  useEffect(()=>{
    let alive=true;
    setSettings(null);setError("");setResult(null);
    if (!supported) return ()=>{alive=false;};
    void (async()=>{
      try {
        const before=await getSession();
        if (before.user_id!==owner || !before.authenticated) return;
        const state=await getAutoDraftSettings();
        const after=await getSession();
        if (!alive || after.user_id!==owner || !after.authenticated) return;
        setSettings(state);
        setMinimumScore(state.minimum_score);
        setMaxDrafts(state.max_per_cycle);
      } catch {
        if (alive) setError("Automatic draft controls are unavailable. Refresh or sign in again.");
      }
    })();
    return ()=>{alive=false;};
  },[owner,supported]);

  async function sameOwner() {
    const user=await getSession();
    if (!user.authenticated || user.user_id!==owner) {
      throw new Error("Your signed-in account changed. Refresh before continuing.");
    }
  }

  async function toggle(enable:boolean) {
    if (!settings || pending.current || !supported) return;
    pending.current=true;setBusy(true);setError("");setResult(null);
    try {
      await sameOwner();
      const saved=await saveAutoDraftSettings({
        enabled:enable,minimum_score:minimumScore,
        max_per_cycle:maxDrafts,revision:settings.revision,
      },owner);
      await sameOwner();
      setSettings(saved);
      if (enable) {
        // Immediate first pass. Background worker continues even if this
        // browser closes, but ONLY while this owner keeps it enabled.
        const scanned=await scanAutoDrafts(owner);
        await sameOwner();
        setResult(scanned);
      }
    } catch (exc) {
      setError(exc instanceof Error?exc.message:"Could not change automatic draft preferences.");
    } finally {pending.current=false;setBusy(false);}
  }

  async function scan() {
    if (!settings?.enabled || pending.current || !supported) return;
    pending.current=true;setBusy(true);setError("");setResult(null);
    try {
      await sameOwner();
      const scanned=await scanAutoDrafts(owner);
      await sameOwner();
      setResult(scanned);
    } catch (exc) {
      setError(exc instanceof Error?exc.message:"Matching scan unavailable.");
    } finally {pending.current=false;setBusy(false);}
  }

  return <section className="panel" aria-label="Automatic IT application drafts">
    <div className="panel-heading"><div>
      <p className="section-kicker"><Sparkles size={14}/> JOB DISCOVERY AUTOPILOT</p>
      <h2>Find IT jobs and prepare drafts automatically</h2>
      <p>SmartPloy checks the available job feeds and prepares applications for
        high-alignment matches, even when you close the browser.</p>
    </div></div>
    <p className="muted"><ShieldCheck size={15}/> Drafts use only your approved CV/profile.
      You review and authorize each employer submission separately.
      <strong> Enabling this does not send applications or contact employers.</strong>
    </p>
    {!supported ? <p role="status">First-party SmartPloy sign-in is required before
      you can enable your private automatic search.</p> :
    !props.personalized ? <p role="status">Set your target IT job titles or
      keywords in personalized search first. General search never auto-profiles you.</p> :
    settings ? <>
      <div className="setup-field-grid">
        <label className="setup-field"><span>Minimum search alignment</span>
          <select aria-label="Minimum automatic match" value={minimumScore}
            disabled={busy || settings.enabled}
            onChange={event=>setMinimumScore(Number(event.target.value))}>
            {[60,70,75,80,90,95].map(score=><option key={score} value={score}>{score}%</option>)}
          </select>
        </label>
        <label className="setup-field"><span>Maximum new drafts each cycle</span>
          <select aria-label="Drafts per cycle" value={maxDrafts}
            disabled={busy || settings.enabled}
            onChange={event=>setMaxDrafts(Number(event.target.value))}>
            {[1,3,5,10].map(count=><option key={count} value={count}>{count}</option>)}
          </select>
        </label>
      </div>
      <div className="job-buttons">
        <button className={settings.enabled?"outline-btn":"navy-btn"} type="button"
          disabled={busy} onClick={()=>void toggle(!settings.enabled)}>
          {busy?"Updating…":settings.enabled?"Pause automatic drafting":"Enable and find IT matches now"}
        </button>
        {settings.enabled ? <button className="secondary-btn" type="button"
          disabled={busy} onClick={()=>void scan()}>
          <RefreshCw size={15}/> Scan new matches now
        </button> : null}
      </div>
      {settings.enabled ? <p role="status"><CheckCircle2 size={15}/>
        Automatic drafting is enabled for this signed-in account.
        Job matches require your CV/approved facts; saved drafts wait in My applications.</p>
      : <p className="muted">Automatic drafting is off. Your existing drafts are retained.</p>}
      {result ? <div role="status">
        <strong>{result.created_count} new matching application draft(s)</strong>
        {result.status==="profile_evidence_required"
          ? <p>Upload a CV or approve career facts before drafts can be created.</p> :
          result.status==="ready"
          ? <p>{result.inspected_recommendations||0} recommendations checked.
              No employer was contacted, and no application was submitted.</p> :
          <p>Scan status: {result.status.replaceAll("_"," ")}.</p>}
        {result.created_count>0 ? <button className="secondary-btn" type="button"
          onClick={props.onReview}>Review prepared applications</button> : null}
      </div> : null}
    </> : <p>Loading your private automatic draft settings…</p>}
    {error ? <p role="alert">{error}</p> : null}
  </section>;
}
