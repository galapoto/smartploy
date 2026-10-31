import { ArrowRight, Bot, CheckCircle2, FileCheck2, Search, WandSparkles } from "lucide-react";
import type { ApplicationFlowMode } from "./types";

/** One decision, four honest destinations; no hidden submission consent. */
export default function StartChoices(props: {
  onMode: (mode: ApplicationFlowMode) => void;
  onBrowse: () => void;
  onUpload?: () => void;
  onCreateCV?: () => void;
  busyBrowse?: boolean;
  cvPresent?: boolean;
}) {
  return <section className="flow-start" aria-label="Choose what to do with SmartPloy">
    <div className="flow-start-heading">
      <p className="section-kicker">START HERE</p>
      <h1>Apply for jobs in four simple steps.</h1>
      <p>Connect your CV once, choose your level of help, review matching jobs and follow each application through to its outcome.</p>
    </div>
    {props.cvPresent ? <div className="flow-start-ready" role="status">
      <CheckCircle2 size={20} aria-hidden="true"/>
      <span><strong>CV connected.</strong> Choose Manual, Assisted or Automatic below. You do not need to upload again.</span>
    </div> : <div className="flow-start-how">
      <p>You can upload a CV, create one from scratch, or browse jobs before preparing an application.</p>
      <div className="row-actions">
        {props.onUpload ? <button type="button" className="primary-btn" onClick={props.onUpload}>
          Upload CV first <ArrowRight size={16} aria-hidden="true"/>
        </button> : null}
        {props.onCreateCV ? <button type="button" className="outline-btn" onClick={props.onCreateCV}>
          Create CV from scratch <ArrowRight size={16} aria-hidden="true"/>
        </button> : null}
      </div>
    </div>}
    <div className="flow-start-grid">
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("manual")}>
        <FileCheck2 size={25} aria-hidden="true" />
        <strong>Apply manually</strong>
        <span>We find matching jobs. You complete the employer form and press Submit.</span>
        <small>MANUAL · You send the application</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("assisted")}>
        <WandSparkles size={25} aria-hidden="true" />
        <strong>Assisted · Apply with AI</strong>
        <span>SmartPloy helps prepare your CV, letter and supported forms. You review before sending.</span>
        <small>ASSISTED · You approve and send</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card"
        onClick={() => props.onMode("automatic")}>
        <Bot size={25} aria-hidden="true" />
        <strong>Automatic · AutoApply</strong>
        <span>Select jobs for private drafts and tracking agents. Employer sending requires separate authorization.</span>
        <small>AUTOMATIC · Not an automatic employer send</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
      <button type="button" className="flow-start-card" disabled={props.busyBrowse}
        onClick={props.onBrowse}>
        <Search size={25} aria-hidden="true" />
        <strong>Just find jobs</strong>
        <span>Browse available jobs and filter them. No CV or application required.</span>
        <small>{props.busyBrowse ? "Opening jobs…" : "Browse and filter"}</small>
        <ArrowRight size={17} aria-hidden="true" />
      </button>
    </div>
    <p className="flow-start-privacy">Your CV stays private. Choosing a mode never authorizes sending an application to an employer.</p>
  </section>;
}
