import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, RefreshCw, ShieldCheck } from "lucide-react";
import { getEmployerAttemptStatus } from "./api";
import type { ApplicationWorkspace } from "./types";

const BATCH_SIZE = 10;

type AttemptCheck = "reserved" | "not_reserved" | "unavailable";

/**
 * Read-only batch triage of EXISTING owner-bound draft workspaces. This does
 * not grant employer permissions and never schedules a submit, retry or job.
 * The server's OIDC-protected /employer-attempt route owns claim truth.
 */
export default function ApplicationAttemptAudit(props: {
  workspaces: readonly ApplicationWorkspace[];
  verifyAccount: () => Promise<void>;
  onOpen: (workspaceId: string) => void;
}) {
  const drafts = useMemo(
    () => props.workspaces.filter((item) => item.status === "draft"), [props.workspaces],
  );
  const signature = JSON.stringify(drafts.map((item) => [
    item.workspace_id, item.revision, item.updated_at, item.canonical_key,
  ]));
  const signatureRef = useRef(signature);
  signatureRef.current = signature;
  const generation = useRef(0);
  const inFlight = useRef(false);
  const [checks, setChecks] = useState<Record<string, AttemptCheck>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // An edited/replaced draft or switched account must not inherit old
  // "no reserved attempt" data. Parent Studio also remounts per OIDC user.
  useEffect(() => {
    ++generation.current;
    inFlight.current = false;
    setChecks({});
    setBusy(false);
    setMessage("");
    return () => { ++generation.current; inFlight.current = false; };
  }, [signature]);

  const unchecked = drafts.filter((item) => !checks[item.workspace_id]);
  const unavailable = drafts.filter((item) => checks[item.workspace_id] === "unavailable");
  const reserved = drafts.filter((item) => checks[item.workspace_id] === "reserved");
  const checked = drafts.length - unchecked.length;
  const isValid = (ticket: number, scope: string) =>
    generation.current === ticket && signatureRef.current === scope;

  async function checkPreviousAttempts() {
    if (inFlight.current || !drafts.length) return;
    const pending = unchecked.length ? unchecked : unavailable.length ? unavailable : drafts;
    const targets = pending.slice(0, BATCH_SIZE);
    const ticket = ++generation.current;
    const scope = signature;
    inFlight.current = true;
    setBusy(true);
    setMessage("");
    try {
      for (const item of targets) {
        if (!isValid(ticket, scope)) return;
        try {
          // Existing Studio guard verifies OIDC user ID and auth source.
          // The server independently rechecks OIDC owner, same origin and
          // durable employer-claim ledger before each read.
          await props.verifyAccount();
          if (!isValid(ticket, scope)) return;
          const attempt = await getEmployerAttemptStatus(item.workspace_id);
          await props.verifyAccount();
          if (!isValid(ticket, scope)) return;
          const result: AttemptCheck = attempt.previous_attempt_reserved === true
            ? "reserved"
            : attempt.previous_attempt_reserved === false &&
              attempt.state === "not_reserved" ? "not_reserved" : "unavailable";
          setChecks((current) => isValid(ticket, scope)
            ? { ...current, [item.workspace_id]: result } : current);
        } catch {
          if (!isValid(ticket, scope)) return;
          // A network or 403 failure can hide a cookie/account switch.
          // Do not render any former owner's case data without rechecking.
          try { await props.verifyAccount(); } catch { return; }
          if (!isValid(ticket, scope)) return;
          setChecks((current) => isValid(ticket, scope)
            ? { ...current, [item.workspace_id]: "unavailable" } : current);
          setMessage("Some attempt checks could not be verified. Do not retry an employer submission.");
        }
      }
    } finally {
      if (isValid(ticket, scope)) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  if (!drafts.length) return null;

  const buttonLabel = unchecked.length
    ? "Check next " + Math.min(BATCH_SIZE, unchecked.length) + " draft attempt" +
      (Math.min(BATCH_SIZE, unchecked.length) === 1 ? "" : "s")
    : unavailable.length
      ? "Recheck " + Math.min(BATCH_SIZE, unavailable.length) + " unavailable status" +
        (Math.min(BATCH_SIZE, unavailable.length) === 1 ? "" : "es")
      : "Recheck previous attempts";

  return <section className="studio-attempt-audit" aria-label="Previous employer attempt checks">
    <div className="studio-attempt-heading">
      <div>
        <span className="section-kicker">BEFORE ANY EMPLOYER HANDOFF</span>
        <h3><ShieldCheck size={18} aria-hidden="true"/> Check previous attempts</h3>
        <p>Verify whether saved drafts already have a reserved employer attempt.
          A draft is not proof that an employer has or has not received it.</p>
      </div>
      <button className="outline-btn compact" type="button"
        disabled={busy} onClick={() => void checkPreviousAttempts()}>
        {busy ? <RefreshCw size={15} className="rotate" aria-hidden="true"/> :
          <ShieldCheck size={15} aria-hidden="true"/>}
        {busy ? "Checking private attempts…" : buttonLabel}
      </button>
    </div>
    <p className="studio-attempt-summary" role="status">
      {checked} of {drafts.length} loaded private drafts checked
      {" · "}{reserved.length} need previous-attempt reconciliation
      {" · "}{unavailable.length} could not be verified.
      No employer contact or retry is performed.
    </p>
    {message ? <p className="studio-attempt-warning" role="alert">
      <AlertTriangle size={15} aria-hidden="true"/>{message}</p> : null}
    {reserved.length ? <div className="studio-attempt-reserved" role="alert">
      <strong><AlertTriangle size={16} aria-hidden="true"/>
        {reserved.length} previously reserved employer attempt{reserved.length === 1 ? "" : "s"}
      </strong>
      <p>Do not submit these jobs again. Open their existing cases and reconcile the outcome.</p>
      <div className="row-actions">
        {reserved.slice(0, 3).map((item) => <button className="outline-btn compact" type="button"
          key={item.workspace_id} onClick={() => props.onOpen(item.workspace_id)}>
          Review {item.role_title} at {item.company} <ArrowRight size={14}/>
        </button>)}
      </div>
    </div> : null}
    {checked ? <details className="studio-attempt-details">
      <summary>View per-application attempt checks</summary>
      <ul>
        {drafts.filter((item) => checks[item.workspace_id]).map((item) => (
          <li key={item.workspace_id}>
            <span><strong>{item.role_title}</strong> · {item.company}</span>
            <small>{checks[item.workspace_id] === "reserved"
              ? "Previous attempt reserved — review, never retry" :
              checks[item.workspace_id] === "not_reserved"
                ? "No previous attempt recorded at check time — not send permission"
                : "Attempt status unavailable — do not retry"}</small>
            <button className="outline-btn compact" type="button"
              onClick={() => props.onOpen(item.workspace_id)}>Open case</button>
          </li>
        ))}
      </ul>
    </details> : null}
  </section>;
}
