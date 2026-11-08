import { ArrowRightLeft, FileCheck2 } from "lucide-react";

export interface DocumentComparisonProps {
  title: string;
  current: string;
  proposed: string;
  source: "approved_evidence" | "private_ai" | "master_cv";
}

/** Preview-only: never persists a proposal or implicitly replaces the editor. */
export default function DocumentComparison(props: DocumentComparisonProps) {
  const count = (value: string) => value.trim().split(/\s+/).filter(Boolean).length;
  return <section className="document-comparison" aria-label={props.title}>
    <div className="document-comparison-heading">
      <ArrowRightLeft size={17} aria-hidden="true"/>
      <div><strong>{props.title}</strong>
        <small>{props.source === "master_cv"
          ? "Current owner-private master CV · independently review every claim"
          : props.source === "private_ai"
            ? "Private model suggestion · unverified; review every claim"
            : "Approved-evidence template · review and personalize"}</small>
      </div>
    </div>
    <div className="document-comparison-columns">
      <div>
        <span><FileCheck2 size={14} aria-hidden="true"/> Current document · {count(props.current)} words</span>
        <pre>{props.current || "(No content yet)"}</pre>
      </div>
      <div>
        <span><FileCheck2 size={14} aria-hidden="true"/> {props.source === "master_cv" ? "Current master CV" : "Proposed text"} · {count(props.proposed)} words</span>
        <pre>{props.proposed}</pre>
      </div>
    </div>
    <p className="document-comparison-boundary">
      Preview only. Your original wording remains unchanged until you explicitly
      select {props.source === "master_cv" ? "Use current master CV in this job draft" : "Use proposed text"}.
      Accepting a comparison does not save a document or contact any employer.
    </p>
  </section>;
}
