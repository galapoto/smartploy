import { ArrowRight, Bot, FileCheck2, Search, WandSparkles } from "lucide-react";
import type { ApplicationFlowMode } from "./types";

/** One decision, four honest destinations; no hidden submission consent. */
export default function StartChoices(props: {
  onMode: (mode: ApplicationFlowMode) => void;
  onBrowse: () => void;
  busyBrowse?: boolean;
}) {
  return <section className="flow-start" aria-label="Choose what to do with SmartPloy">
    <div className="flow-start-heading">
      <p className="section-kicker">START HERE</p>
      <h1>Apply for jobs in four simple steps.</h1>
      <p>Upload your CV, get matching jobs, choose one, and apply. Pick how much help you want.</p>
    </div>
    <div className="flow-start-grid">
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("manual")}>
        <FileCheck2 size={25} aria-hidden="true" />
        <strong>Apply manually</strong>
        <span>We match your CV. You fill and submit the employer application.</span>
        <small>CV → matches → employer form</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("assisted")}>
        <WandSparkles size={25} aria-hidden="true" />
        <strong>Apply with AI</strong>
        <span>Find the right jobs, prepare documents and get help with supported forms.</span>
        <small>Choose partial assistance</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("automatic")}>
        <Bot size={25} aria-hidden="true" />
        <strong>AutoApply</strong>
        <span>Select jobs for automated preparation. Unsupported submissions wait for your review.</span>
        <small>Employer submission needs supported authorization</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card" disabled={props.busyBrowse}
        onClick={props.onBrowse}>
        <Search size={25} aria-hidden="true" />
        <strong>Just find jobs</strong>
        <span>Search every current vacancy. No CV or application required.</span>
        <small>{props.busyBrowse ? "Opening jobs…" : "Browse and filter"}</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
    </div>
    <p className="flow-start-privacy">Your CV stays private. Choosing a mode never authorizes sending an application to an employer.</p>
  </section>;
}
