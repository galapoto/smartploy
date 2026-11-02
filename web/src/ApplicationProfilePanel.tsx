/** SP116 applicant-led completeness and durable ATS question memory.
 * Private account data, not a provider submission status or an approval grant.
 * CV-only applicants continue all existing Manual/Assisted workflows.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, CircleHelp, LockKeyhole, ShieldCheck } from "lucide-react";
import {
  deleteApplicationQuestion, getApplicationQuestionMemory, getSession,
  saveApplicationQuestionAnswer, setApplicationProfileMode,
} from "./api";
import type {
  ApplicationProfileMode, ApplicationProfileQuestion, CandidateFact,
} from "./types";
import "./application-profile.css";

const PROFILE_FIELDS = [
  {type:"identity", label:"Legal name (for contact fields)", category:"Contact"},
  {type:"email", label:"Contact email", category:"Contact"},
  {type:"phone", label:"Contact phone", category:"Contact"},
  {type:"location", label:"City or location", category:"Contact"},
  {type:"linkedin", label:"LinkedIn URL", category:"Online presence"},
  {type:"github", label:"GitHub URL", category:"Online presence"},
  {type:"skill", label:"Skills", category:"Experience"},
  {type:"experience", label:"Work experience", category:"Experience"},
  {type:"education", label:"Education", category:"Experience"},
  {type:"certification", label:"Certifications", category:"Experience"},
  {type:"project", label:"Projects", category:"Experience"},
  {type:"language", label:"Languages", category:"Preferences"},
  {type:"domain", label:"Preferred industries", category:"Preferences"},
  {type:"preference", label:"Employment preferences", category:"Preferences"},
  {type:"availability", label:"Availability window", category:"Preferences"},
  {type:"employment_type", label:"Employment type", category:"Preferences"},
  {type:"relocation", label:"Relocation flexibility", category:"Preferences"},
  {type:"portfolio", label:"Portfolio site", category:"Online presence"},
  {type:"website", label:"Personal website", category:"Online presence"},
  {type:"work_authorization", label:"Work authorization (manual only)", category:"Sensitive"},
  {type:"notice_period", label:"Notice period (manual only)", category:"Sensitive"},
  {type:"salary_expectation", label:"Salary preference (manual only)", category:"Sensitive"},
  {type:"references", label:"References (manual only)", category:"Sensitive"},
] as const;

export function applicantProfileReadiness(facts: CandidateFact[]) {
  const approved = new Set(facts.filter(f => f.approved === true &&
    typeof f.value === "string" && f.value.trim()).map(f => f.fact_type));
  const fields = PROFILE_FIELDS.map(item => ({
    ...item, present: approved.has(item.type),
  }));
  return {
    fields, reviewed: fields.filter(f => f.present).length,
    total: fields.length,
    missing: fields.filter(f => !f.present).map(f => f.label),
  };
}

export default function ApplicationProfilePanel(props: {
  expectedUserId: string;
  facts: CandidateFact[];
  cvPresent: boolean;
  compact?: boolean;
  onOpenProfile?: () => void;
}) {
  const [mode, setMode] = useState<ApplicationProfileMode>("guided");
  const [questions, setQuestions] = useState<ApplicationProfileQuestion[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [answerDraft, setAnswerDraft] = useState<Record<string, string>>({});
  const alive = useRef(true);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const stats = useMemo(() => applicantProfileReadiness(props.facts), [props.facts]);

  async function requireOwner() {
    const session = await getSession();
    if (!session.authenticated || !props.expectedUserId ||
        session.user_id !== props.expectedUserId) {
      throw new Error("Your signed-in account changed. Reload your profile.");
    }
  }

  useEffect(() => {
    alive.current = true;
    const ticket = ++generation.current;
    setMode("guided"); setQuestions([]); setLoaded(false);
    setAnswerDraft({}); setMessage(""); setError("");
    void (async () => {
      try {
        await requireOwner();
        const result = await getApplicationQuestionMemory();
        await requireOwner();
        if (!alive.current || ticket !== generation.current) return;
        setMode(result.mode); setQuestions(result.questions);
        setAnswerDraft(Object.fromEntries(result.questions.map(q => [q.question_key, q.answer])));
        setLoaded(true);
      } catch {
        if (alive.current && ticket === generation.current) {
          setError("Could not verify saved profile preferences. CV applications remain available.");
        }
      }
    })();
    return () => {
      alive.current = false;
      ++generation.current;
    };
  }, [props.expectedUserId]);

  async function guarded(action: () => Promise<void>) {
    if (!alive.current || !loaded || inFlight.current) return;
    const ticket = generation.current;
    inFlight.current = true; setBusy(true); setError(""); setMessage("");
    try {
      await requireOwner();
      if (!alive.current || ticket !== generation.current) return;
      await action();
      await requireOwner();
    } catch (exc) {
      if (alive.current && ticket === generation.current) {
        setError(exc instanceof Error ? exc.message : "Private profile update failed.");
      }
    } finally {
      inFlight.current = false;
      if (alive.current && ticket === generation.current) setBusy(false);
    }
  }

  function changeMode(next: ApplicationProfileMode) {
    if (next === mode || busy || !loaded) return;
    if (!window.confirm(next === "cv_only"
      ? "Use only your CV for applications? This choice is saved to your own profile. " +
        "SmartPloy will no longer remember new employer questions while CV-only. " +
        "Existing saved answers remain private, but are NOT auto-filled. " +
        "You will need to enter more employer form details manually."
      : "Enable guided profile? New eligible employer questions can now be " +
        "remembered privately as unanswered prompts, and you can approve " +
        "truthful reusable answers. Nothing will be sent to an employer.")) return;
    void guarded(async () => {
      const changed = await setApplicationProfileMode(next, props.expectedUserId);
      if (!alive.current) return;
      if (changed.mode !== next || changed.employer_actions_performed !== 0) {
        throw new Error("Private profile mode was not confirmed by the server.");
      }
      setMode(changed.mode);
      setMessage(next === "cv_only"
        ? "CV-only preference saved. You can still apply; automation will have fewer verified fields."
        : "Guided profile enabled. New ordinary employer questions can be remembered for future review.");
    });
  }

  function saveAnswer(item: ApplicationProfileQuestion) {
    const answer = (answerDraft[item.question_key] || "").trim();
    if (busy || mode !== "guided" || !answer || answer.length > 1500) return;
    const approved = item.reusable_scope === "exact_question";
    if (!window.confirm(
      "SAVE THIS ANSWER IN YOUR PRIVATE PROFILE?\n\nQuestion: " + item.label +
      "\n\nI confirm my answer is true and may be suggested on later " +
      "applications with the same exact question. It will NEVER be " +
      "automatically submitted or used for legal/consent questions." +
      (approved ? "" : "\nThis job-specific answer will stay manual-only.")
    )) return;
    void guarded(async () => {
      const result = await saveApplicationQuestionAnswer(
        item.question_key, item.version, answer, approved,
        props.expectedUserId,
      );
      if (result.employer_actions_performed !== 0 ||
          result.automatic_employer_submission_authorized !== false ||
          result.question.question_key !== item.question_key ||
          result.question.version !== item.version + 1) {
        throw new Error("The saved question revision was not confirmed.");
      }
      if (!alive.current) return;
      setQuestions(existing => existing.map(q =>
        q.question_key === item.question_key ? result.question : q
      ));
      setMessage("Answer saved in your private profile. You will review it for each new application.");
    });
  }

  function forget(item: ApplicationProfileQuestion) {
    if (busy || !window.confirm(
      "Remove this question and its saved answer from your SmartPloy profile? " +
      "This will not modify any employer form."
    )) return;
    void guarded(async () => {
      const result = await deleteApplicationQuestion(item.question_key, props.expectedUserId);
      if (result.deleted !== true || result.employer_actions_performed !== 0) {
        throw new Error("Profile question removal was not confirmed.");
      }
      if (!alive.current) return;
      setQuestions(existing => existing.filter(q => q.question_key !== item.question_key));
      setAnswerDraft(old => {
        const copy = {...old}; delete copy[item.question_key]; return copy;
      });
      setMessage("The saved question was removed from your private profile.");
    });
  }

  const answered = questions.filter(q => q.approved_for_reuse).length;
  const pending = questions.filter(q => !q.approved_for_reuse).length;
  return <section className={"panel application-profile-panel" + (props.compact ? " compact" : "")}
    aria-label="Application profile completeness">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">YOUR OPTIONAL APPLICATION PROFILE</p>
        <h2>Prepare once. Review for each application.</h2>
        <p>Verified details help SmartPloy fill more of an employer's form.
          Your CV remains usable without completing a profile.</p>
      </div>
    </div>
    <div className="application-profile-progress" aria-label="Approved profile field coverage">
      <strong>{stats.reviewed} of {stats.total} profile areas reviewed</strong>
      <progress max={stats.total} value={stats.reviewed}>
        {stats.reviewed} of {stats.total}
      </progress>
      <small>Guidance only — not an employer eligibility, AI readiness or submission score.</small>
    </div>
    {props.cvPresent && stats.reviewed < stats.total ? <p className="application-profile-note"
      role="status">
      <CircleHelp size={17} aria-hidden="true" />
      With CV-only applications you can still choose Manual, Assisted or
      Automatic draft preparation. Without approved contact and career details,
      SmartPloy may not fill many employer fields or qualify for authorized
      partner submissions; you will complete more questions yourself.
    </p> : null}
    <div className="application-profile-modes" role="group" aria-label="Choose how to build your application profile">
      <button type="button" className={mode === "guided" && loaded ? "selected" : ""}
        aria-pressed={mode === "guided" && loaded}
        onClick={() => changeMode("guided")} disabled={!loaded || busy}>
        <ShieldCheck size={16} aria-hidden="true"/> Guided reusable profile
      </button>
      <button type="button" className={mode === "cv_only" && loaded ? "selected" : ""}
        aria-pressed={mode === "cv_only" && loaded}
        onClick={() => changeMode("cv_only")} disabled={!loaded || busy}>
        <LockKeyhole size={16} aria-hidden="true"/> Use CV only
      </button>
    </div>
    {mode === "cv_only" && loaded ? <p role="status" className="muted">
      CV-only mode is active. No new employer questions will be stored in
      your profile. The Manual and Assisted workflows remain available;
      complete missing employer fields yourself.
    </p> : null}
    {!props.compact ? <>
      <details className="application-profile-section">
        <summary>Profile details to complete ({stats.missing.length} missing)</summary>
        <div className="application-profile-field-grid">
          {stats.fields.map(field => <div key={field.type}
            className={field.present ? "ready" : "missing"}>
            {field.present ? <CheckCircle2 size={15} aria-hidden="true"/> :
              <CircleHelp size={15} aria-hidden="true"/>}
            <span>{field.label}</span><small>{field.category}</small>
          </div>)}
        </div>
        <p className="muted">Sensitive details such as work authorization,
          salary, consent and identity documents always require explicit
          review on the employer website, even if stored by choice.</p>
      </details>
      {mode === "guided" && questions.length ? <div className="application-profile-questions">
        <h3>Questions remembered from your applications</h3>
        <p className="muted">{answered} approved for later suggestions ·
          {pending} awaiting your review. Only safe ordinary text questions
          are retained; no CV inference or automatic employer submission.</p>
        {questions.map(item => <div key={item.question_key}
          className="application-profile-question">
          <label htmlFor={"answer-" + item.question_key}>
            <strong>{item.label}</strong>
            <small>{item.approved_for_reuse
              ? "Reviewed answer · suggest on exact matching questions"
              : item.reusable_scope === "manual_only"
                ? "Job-specific question · never reuse automatically"
                : "Missing or unapproved · complete once for future use"}</small>
          </label>
          <textarea id={"answer-" + item.question_key}
            rows={2} maxLength={1500} disabled={busy}
            value={answerDraft[item.question_key] || ""}
            onChange={event => setAnswerDraft(current =>
              ({...current, [item.question_key]:event.target.value}))}
            placeholder="Enter your truthful answer after checking the employer's question"
          />
          <div className="row-actions">
            <button type="button" className="outline-btn"
              disabled={busy || !(answerDraft[item.question_key] || "").trim() ||
                (answerDraft[item.question_key] || "").trim().length < 2}
              onClick={() => saveAnswer(item)}>
              Save reviewed answer
            </button>
            <button type="button" className="text-btn" disabled={busy}
              onClick={() => forget(item)}>Remove question</button>
          </div>
        </div>)}
      </div> : null}
      {mode === "guided" && !questions.length && loaded ?
        <p className="muted">As you encounter new eligible employer questions,
          SmartPloy remembers their prompts here. You can approve answers later.</p> : null}
    </> : null}
    {props.onOpenProfile ? <button type="button" className="outline-btn"
      onClick={props.onOpenProfile}>
      {props.compact ? "Complete my profile for better assistance" :
        "Open the profile fact editor below"}
    </button> : null}
    {error ? <p role="alert" className="studio-alert error">{error}</p> : null}
    {message ? <p role="status" className="studio-alert">{message}</p> : null}
  </section>;
}
