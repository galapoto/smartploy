import { useCallback, useEffect, useState } from "react";
import { CheckCheck, Flag, RefreshCw, ShieldCheck } from "lucide-react";
import {
  getSession, getSocialModeratorCapabilities, getSocialModerationQueue,
  markSocialReportReviewed, type SocialModeratorReport
} from "./api";

/** This panel loads content only after a server-verified operator capability.
 * No member-specific reports appear in the DOM for normal signed-in users.
 * Review acknowledges triage; it is NOT an automatic ban/sanction.
 */
export default function SocialSafetyInbox({ expectedUserId }: { expectedUserId: string }) {
  const [allowed, setAllowed] = useState(false);
  const [reports, setReports] = useState<SocialModeratorReport[]>([]);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const verifyOwner = useCallback(async () => {
    const session = await getSession();
    if (!session.authenticated || !expectedUserId ||
        session.user_id !== expectedUserId) {
      setAllowed(false);
      setReports([]);
      throw new Error("Your SmartPloy account changed. Reload before reviewing reports.");
    }
  }, [expectedUserId]);

  const load = useCallback(async () => {
    setChecking(true);
    try {
      const cap = await getSocialModeratorCapabilities();
      await verifyOwner();
      if (!cap.operator) {
        setAllowed(false); setReports([]);
        return;
      }
      const result = await getSocialModerationQueue();
      await verifyOwner();
      setAllowed(true);
      setReports(result.reports);
      setError("");
    } catch (exc) {
      setAllowed(false); setReports([]);
      // The main member experience must not show a spurious moderation error.
      if (exc instanceof Error && /account changed/i.test(exc.message)) {
        setError(exc.message);
      }
    } finally {
      setChecking(false);
    }
  }, [verifyOwner]);

  useEffect(() => {
    let active = true;
    void (async () => {
      if (active) await load();
    })();
    return () => { active = false; };
  }, [load]);

  const markReviewed = async (item: SocialModeratorReport) => {
    if (busy || item.state !== "open") return;
    setBusy(true); setNotice(""); setError("");
    try {
      await verifyOwner();
      await markSocialReportReviewed(item.report_id, expectedUserId);
      await verifyOwner();
      const next = await getSocialModerationQueue();
      await verifyOwner();
      setReports(next.reports);
      setNotice("Marked reviewed. No automatic account restriction was applied.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not mark this report reviewed");
    } finally {
      setBusy(false);
    }
  };

  if (checking || !allowed) return null;
  return <section className="sp128-moderation sp127-card" aria-label="Social safety moderation">
    <header className="sp127-card-heading">
      <div><p className="section-kicker">RESTRICTED OPERATOR WORKSPACE</p>
        <h3><Flag size={18} aria-hidden="true"/> Message safety reports</h3>
        <p className="sp127-muted">Only explicitly authorized SmartPloy operators can
          inspect reported message previews. Reviewing does not automatically
          suspend or restrict a member.</p></div>
      <button type="button" className="sp127-refresh" disabled={busy}
        onClick={() => void load()}><RefreshCw size={15}/> Refresh</button>
    </header>
    {error ? <p role="alert" className="sp127-error">{error}</p> : null}
    {notice ? <p role="status" className="sp127-feedback">{notice}</p> : null}
    {reports.length === 0 ? <p className="sp127-muted">No reports to review.</p> :
      <div className="sp128-report-list">
        {reports.map(item => <article key={item.report_id} className="sp128-report-entry">
          <div className="sp128-report-top">
            <strong>@{item.reported_handle}</strong>
            <span className={"sp128-review-state " + item.state}>
              {item.state === "open" ? "Needs review" : "Reviewed"}</span>
          </div>
          <p className="sp127-muted">Reported by @{item.reporter_handle} ·
            {item.reason.replaceAll("_", " ")} · {new Date(item.created_at).toLocaleString()}</p>
          <blockquote className="sp128-preview">{item.message_preview}</blockquote>
          {item.note ? <p className="sp128-review-note">Reporter note: {item.note}</p> : null}
          {item.state === "open" ? <button type="button" className="outline-btn"
            disabled={busy} onClick={() => void markReviewed(item)}>
            <CheckCheck size={16} aria-hidden="true"/> Mark reviewed</button> :
            <p className="sp127-muted"><ShieldCheck size={14} aria-hidden="true"/>
              Reviewed {item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : ""}</p>}
        </article>)}
      </div>}
  </section>;
}
