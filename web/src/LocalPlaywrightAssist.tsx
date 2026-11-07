/** SP111: SmartPloy-to-local-Playwright review flow.
 * No hidden browser operation: applicant starts one local helper per job,
 * enters a one-use pairing code, sees the planned fields and approves once.
 * Same-account/session reverified before and after private bridge actions.
 */
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Monitor, ShieldCheck, XCircle } from "lucide-react";
import { getBrowserHandoffReadiness, getSession } from "./api";
import {
  callLocalPlaywrightBridge, localBridgeOriginAllowed,
  type LocalBridgeOpened, type LocalBridgeInspected,
  type LocalBridgeFilled, type LocalBridgeStopped, type LocalBridgeField,
} from "./localPlaywrightBridge";
import "./local-playwright.css";

type Phase = "not-paired" | "opened" | "inspected" | "filled" | "uncertain" | "stopped";
const CODE = /^[A-Za-z0-9_-]{20,80}$/;
const SESSION_CHANGED = "Your SmartPloy sign-in changed. The local connection is blocked; restart and review again.";

export default function LocalPlaywrightAssist(props: {
  packetText: string;
  enabled: boolean;
  expectedUserId: string;
  expectedAuthSource: string;
  expectedWorkspaceId: string;
  expectedRevision: number;
}) {
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<Phase>("not-paired");
  const [fields, setFields] = useState<LocalBridgeField[]>([]);
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const sessionToken = useRef("");
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      // A changed account or job must never expose the old token in new UI.
      // The local helper remains safe (its bearer token is no longer in UI
      // memory) and can be stopped with Ctrl+C in the applicant terminal.
      mounted.current = false;
      sessionToken.current = "";
    };
  }, []);

  async function verifyAccount() {
    const session = await getSession();
    if (session.authenticated !== true ||
        session.user_id !== props.expectedUserId ||
        session.auth_source !== props.expectedAuthSource) {
      sessionToken.current = "";
      throw new Error(SESSION_CHANGED);
    }
  }

  async function verifyCurrentDraft() {
    // Existing owner-scoped backend readiness must recheck source/job and
    // document revision immediately before each local browser action.
    // The helper's 15-minute packet is NOT enough to detect another tab edit.
    const readiness = await getBrowserHandoffReadiness(props.expectedWorkspaceId);
    if (readiness.ready !== true ||
        readiness.document_revision !== props.expectedRevision) {
      throw new Error("This job or reviewed CV/letter changed. Stop the local browser, " +
        "save and prepare a fresh application packet.");
    }
  }

  async function guarded(action: () => Promise<void>) {
    if (!props.enabled || !mounted.current || inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(""); setFeedback("");
    try {
      await verifyAccount();
      if (!mounted.current) return;
      await verifyCurrentDraft();
      await verifyAccount();
      if (!mounted.current) return;
      await action();
      await verifyAccount();
    } catch (exc) {
      if (!mounted.current) return;
      const message = exc instanceof Error ? exc.message : "The local browser action was blocked.";
      setError(message);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function startLocalBrowser() {
    if (phase !== "not-paired" || !CODE.test(code.trim()) || !props.packetText) return;
    if (!window.confirm(
      "Send the currently reviewed SmartPloy packet (approved contact details " +
      "and cover letter) ONLY to the helper on this computer at 127.0.0.1? " +
      "The helper opens the exact employer posting in visible Chromium. " +
      "The employer website may receive data during form filling, but this step " +
      "does not fill fields, upload a CV or submit an application."
    )) return;
    void guarded(async () => {
      let packet: unknown;
      try { packet = JSON.parse(props.packetText); }
      catch { throw new Error("The reviewed application packet is invalid. Copy a fresh one."); }
      if (!packet || typeof packet !== "object" ||
          (packet as { workspace_id?: unknown }).workspace_id !== props.expectedWorkspaceId ||
          (packet as { revision?: unknown }).revision !== props.expectedRevision) {
        throw new Error("The reviewed packet does not match this exact current job. Copy a fresh one.");
      }
      const response = await callLocalPlaywrightBridge<LocalBridgeOpened>(
        "prepare", { pairing_code: code.trim(), packet }, { expectedStage: "opened" },
      );
      // Do not leave an old applicant's browser session reusable after an
      // in-flight OIDC switch; best-effort cleanup is LOCAL only.
      try { await verifyAccount(); } catch (exc) {
        try {
          await callLocalPlaywrightBridge<LocalBridgeStopped>(
            "stop", {}, { token: response.token, expectedStage: "stopped" }
          );
        } catch { /* helper can always be shut down from terminal */ }
        throw exc;
      }
      if (!mounted.current) return;
      sessionToken.current = response.token; // memory only: no storage/log/URL
      setCode("");
      setPhase("opened");
      setFeedback("Local Chromium opened for " + response.company +
        " — " + response.role_title + ". Complete employer login and navigate to " +
        "the exact application form in the visible browser, then inspect here.");
    });
  }

  function inspectLocalBrowser() {
    if (phase !== "opened" || !sessionToken.current) return;
    void guarded(async () => {
      const response = await callLocalPlaywrightBridge<LocalBridgeInspected>(
        "inspect", {}, { token: sessionToken.current, expectedStage: "inspected" },
      );
      if (!mounted.current) return;
      setFields(response.approved_fields);
      setPlanId(response.plan_id);
      setPhase("inspected");
      setFeedback(response.approved_fields.length
        ? "Inspect these exact field names. Nothing has been filled or submitted."
        : "No unique, safe empty fields were found. Complete this form manually.");
    });
  }

  function fillLocalBrowser() {
    if (phase !== "inspected" || !sessionToken.current ||
        !planId || !fields.length || !props.enabled || inFlight.current) return;
    if (!window.confirm(
      "Fill these " + fields.length + " reviewed, ordinary fields ONCE in the " +
      "visible employer form? The employer page may transmit each value " +
      "immediately. SmartPloy will not upload any file or click Submit. " +
      "A changed form or uncertain outcome stops without retry."
    )) return;
    // Even after a network timeout the local helper may have filled some
    // values. Disable local retry before issuing the request.
    setPhase("uncertain");
    void guarded(async () => {
      const response = await callLocalPlaywrightBridge<LocalBridgeFilled>(
        "fill", { plan_id: planId, confirmation: "FILL REVIEWED FIELDS" },
        { token: sessionToken.current, expectedStage: "filled" },
      );
      if (!mounted.current) return;
      setPhase("filled");
      setFeedback("Filled " + response.filled + " of " + response.planned +
        " reviewed fields. " + (response.stopped_on_change
          ? "The form changed; finish remaining fields manually. "
          : "") +
        "Review every value, attach documents and submit personally on the employer website.");
    });
  }

  function stopLocalBrowser() {
    if (!sessionToken.current || inFlight.current) return;
    const token = sessionToken.current;
    sessionToken.current = "";
    setBusy(true); setError("");
    void callLocalPlaywrightBridge<LocalBridgeStopped>(
      "stop", {}, { token, expectedStage: "stopped" },
    ).then(() => {
      if (mounted.current) setFeedback("Local Playwright browser closed. Restart the helper for another job.");
    }).catch(() => {
      if (mounted.current) setError(
        "Could not confirm local browser closure. Press Ctrl+C in the helper terminal."
      );
    }).finally(() => {
      if (!mounted.current) return;
      setPhase("stopped"); setFields([]); setPlanId(""); setBusy(false);
    });
  }

  const trustedPage = localBridgeOriginAllowed(window.location.origin);

  return <section className="local-playwright-panel" aria-label="Paired local Playwright browser">
    <div className="local-playwright-heading">
      <Monitor size={20} aria-hidden="true" />
      <div>
        <strong>Connect my local Playwright browser</strong>
        <p>Fill reviewed fields from SmartPloy without pasting your private packet into a terminal.</p>
      </div>
    </div>
    <p className="local-playwright-notice">
      <ShieldCheck size={15} aria-hidden="true" />
      Private local connection only · 127.0.0.1 · no employer submission or automatic CV upload
    </p>
    <p className="muted">
      Install the reviewed Playwright ZIP once, then start <code>python bridge.py</code> on
      your own desktop. The terminal prints a one-use code. Keep the visible Chromium
      browser open while completing the employer's application. The Chrome extension
      remains an alternative when local-network access is blocked.
    </p>
    {!trustedPage ? <p role="alert">This origin cannot connect to your local Playwright helper.
      Use the Chrome companion instead.</p> : null}
    {phase === "not-paired" ? <div className="local-playwright-actions">
      <label htmlFor="smartploy-local-playwright-code">Temporary local pairing code
        <input id="smartploy-local-playwright-code" type="password"
          autoComplete="off" spellCheck={false} value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Code printed by python bridge.py" maxLength={80} />
      </label>
      <button type="button" className="navy-btn"
        disabled={!props.enabled || busy || !trustedPage || !CODE.test(code.trim())}
        onClick={startLocalBrowser}>
        {busy ? "Connecting to local browser…" : "Open reviewed employer form"}
      </button>
    </div> : null}
    {phase === "opened" ? <div className="local-playwright-actions">
      <button type="button" className="navy-btn" disabled={!props.enabled || busy}
        onClick={inspectLocalBrowser}>
        {busy ? "Inspecting…" : "Inspect current employer form"}
      </button>
      <small>Navigate/login in the visible local browser first. The page must match this exact job.</small>
    </div> : null}
    {phase === "inspected" ? <div className="local-playwright-actions">
      <strong>Reviewed safe fields ({fields.length})</strong>
      <ul className="local-playwright-fields">
        {fields.map((item, index) =>
          <li key={item.key + ":" + index}>{item.label} <small>{item.key}</small></li>)}
      </ul>
      <button type="button" className="navy-btn"
        disabled={!props.enabled || busy || !fields.length}
        onClick={fillLocalBrowser}>
        Fill reviewed fields once (never submit)
      </button>
    </div> : null}
    {phase === "uncertain" ? <p role="alert">
      The fill attempt may have changed the employer form. Inspect the visible
      browser manually; do not retry an uncertain application.
    </p> : null}
    {phase === "filled" ? <p role="status" className="local-playwright-result">
      <CheckCircle2 size={17} aria-hidden="true" />
      Field-fill action completed. Your application is NOT submitted.
    </p> : null}
    {phase === "stopped" ? <p role="status">
      Session stopped. Restart <code>python bridge.py</code> for the next job.
    </p> : null}
    {feedback ? <p role="status" className="local-playwright-result">{feedback}</p> : null}
    {error ? <p role="alert" className="local-playwright-error">
      <XCircle size={16} aria-hidden="true" /> {error}
    </p> : null}
    {sessionToken.current && phase !== "stopped" ? <button type="button"
      className="outline-btn compact" disabled={busy} onClick={stopLocalBrowser}>
      Stop local browser session
    </button> : null}
    {!props.enabled ? <p role="alert">
      Your reviewed application is no longer current or editing is in progress.
      Save and copy a fresh packet before using local browser assistance.
    </p> : null}
  </section>;
}
