import { CheckCircle2, CircleHelp, Sparkles } from "lucide-react";
import { reviewDocument, type DocumentQualityInput } from "./documentQuality";

/**
 * Continuous in-browser editorial guidance for master and job-specific drafts.
 * This deliberately does not claim model inference or check the truth of facts.
 */
export default function DocumentCoach(props: DocumentQualityInput) {
  const result = reviewDocument(props);
  return <aside className="document-coach"
      aria-label={result.title + " live writing review"}>
    <div className="document-coach-heading">
      <span className="document-coach-mark"><Sparkles size={18} aria-hidden="true"/></span>
      <div className="document-coach-title">
        <strong>Live writing review</strong>
        <span>{result.title} · updates as you type</span>
      </div>
      <span className="document-coach-progress" aria-label={
        result.passed + " of " + result.total + " writing checks met"
      }>{result.passed} / {result.total} checks</span>
    </div>
    <p className="document-coach-summary">{result.summary}</p>
    <ul className="document-coach-checks">
      {result.checks.map((item) => <li key={item.id}
          className={item.passed ? "is-met" : "needs-review"}>
        {item.passed
          ? <CheckCircle2 size={17} aria-hidden="true"/>
          : <CircleHelp size={17} aria-hidden="true"/>}
        <div><strong>{item.label}</strong>
          {!item.passed ? <small>{item.guidance}</small> : null}
        </div>
      </li>)}
    </ul>
    <p className="document-coach-disclosure">
      This instant checklist runs in your browser without sending document text
      to an AI service. It cannot verify claims or predict hiring decisions.
      The separate private-model assistant proposes wording only when you approve a request.
    </p>
  </aside>;
}
