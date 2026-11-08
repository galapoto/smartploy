import {
  ArrowRight, Bot, CheckCircle2, FileCheck2, FileText, Search,
  UploadCloud, WandSparkles,
} from "lucide-react";
import type { ApplicationFlowMode } from "./types";

/**
 * SP87 CV-first entrypoint: the first three application methods are NEVER
 * offered before a CV exists. Browse without a CV remains possible, but is
 * not an application mode or permission to send anything to an employer.
 */
export default function StartChoices(props: {
  onMode: (mode: ApplicationFlowMode) => void;
  onBrowse: () => void;
  onOpenApplications?: () => void;
  onUpload?: () => void;
  onCreateCV?: () => void;
  busyBrowse?: boolean;
  cvPresent?: boolean;
}) {
  const hasCV = props.cvPresent === true;
  return <section className="flow-start" aria-label="Choose what to do with SmartPloy">
    <div className="flow-start-masthead" aria-hidden="true">
      <span>SMARTPLOY / APPLICATION WORKSPACE</span><span>FINLAND · PRIVATE WORKSPACE</span>
    </div>
    <div className="flow-start-heading">
      <p className="section-kicker">YOUR APPLICATION JOURNEY</p>
      <h1>{hasCV ? "CV connected. Choose how to apply." : "Start with your CV."}</h1>
      <p>{hasCV
        ? "Your CV is ready. Choose a method to find and apply for jobs."
        : "Upload or create a CV, then choose how to apply. You can browse jobs without a CV."}</p>
    </div>
    <ol className="flow-start-progress" aria-label="Application journey steps">
      <li className={hasCV ? "done" : "current"}
        aria-current={!hasCV ? "step" : undefined}>
        1 · CV
      </li>
      <li className={hasCV ? "current" : ""}
        aria-current={hasCV ? "step" : undefined}>
        2 · Application type
      </li>
      <li>3 · Match jobs</li>
      <li>4 · Review &amp; apply</li>
    </ol>
    {!hasCV ? <>
      <div className="flow-start-how" aria-label="Step 1 — connect your CV">
        <div className="flow-start-cv-copy">
          <strong>Step 1 · Connect your CV</strong>
          <p>Upload a PDF/DOCX or create a CV here. It stays private until you approve sharing.</p>
        </div>
        <div className="row-actions">
          {props.onUpload ? <button type="button" className="primary-btn" onClick={props.onUpload}>
            <UploadCloud size={16} aria-hidden="true"/> Upload CV first
            <ArrowRight size={16} aria-hidden="true"/>
          </button> : null}
          {props.onCreateCV ? <button type="button" className="outline-btn" onClick={props.onCreateCV}>
            <FileText size={16} aria-hidden="true"/> Create CV from scratch
          </button> : null}
        </div>
      </div>
      <div className="flow-start-locked" role="status">
        <FileCheck2 size={19} aria-hidden="true"/>
        <span id="flow-start-require-cv"><strong>Upload a CV to unlock these options.</strong> You can still browse jobs.</span>
      </div>
    </> : <>
      <div className="flow-start-ready" role="status">
        <CheckCircle2 size={20} aria-hidden="true"/>
        <span><strong>CV connected.</strong> Choose how to apply. Review your facts before sending.</span>
      </div>

    </>}
    <div className="flow-start-method-heading">
      <div>
        <p className="section-kicker">STEP 2 · APPLICATION METHOD</p>
        <h2>Manual, Assisted or Automatic?</h2>
        <p>{hasCV
          ? "Select one path to continue."
          : "Connect a CV to unlock these choices."}</p>
      </div>
      <span className={"flow-start-method-status " + (hasCV ? "ready" : "waiting")}>
        {hasCV ? "Ready to choose" : "CV required first"}
      </span>
    </div>
      <div className="flow-start-grid flow-start-grid-methods" role="group"
        aria-label="Step 2 — choose application type">
        <button type="button" className="flow-start-card" data-flow-mode="manual"
          disabled={!hasCV}
          aria-describedby={!hasCV ? "flow-start-require-cv" : undefined}
          onClick={() => props.onMode("manual")}>
          <FileCheck2 size={25} aria-hidden="true"/>
          <span className="flow-start-index" aria-hidden="true">01</span>
          <strong>Apply manually</strong>
          <span>Open a matching job and complete its application yourself.</span>
          <small>MANUAL · You send the application</small>
          <span className="flow-card-cta">{hasCV ? "Choose manual" : "Connect CV to unlock"}</span>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
        <button type="button" className="flow-start-card" data-flow-mode="assisted"
          disabled={!hasCV}
          aria-describedby={!hasCV ? "flow-start-require-cv" : undefined}
          onClick={() => props.onMode("assisted")}>
          <WandSparkles size={25} aria-hidden="true"/>
          <span className="flow-start-index" aria-hidden="true">02</span>
          <strong>Assisted · Apply with AI</strong>
          <span>Prepare a CV and letter. Review before filling supported forms.</span>
          <small>ASSISTED · You review before sending</small>
          <span className="flow-card-cta">{hasCV ? "Choose assisted" : "Connect CV to unlock"}</span>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
        <button type="button" className="flow-start-card" data-flow-mode="automatic"
          disabled={!hasCV}
          aria-describedby={!hasCV ? "flow-start-require-cv" : undefined}
          onClick={() => props.onMode("automatic")}>
          <Bot size={25} aria-hidden="true"/>
          <span className="flow-start-index" aria-hidden="true">03</span>
          <strong>Automatic · AutoApply</strong>
          <span>Prepare matched jobs. Employer actions require explicit authorization.</span>
          <small>AUTOMATIC · Employer-specific authorization required</small>
          <span className="flow-card-cta">{hasCV ? "Choose automatic" : "Connect CV to unlock"}</span>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
      </div>

    {hasCV ? <>
      <div className="flow-start-cv-actions">
        {props.onUpload ? <button type="button" className="text-link" onClick={props.onUpload}>
          Replace connected CV
        </button> : null}
        {props.onCreateCV ? <button type="button" className="text-link" onClick={props.onCreateCV}>
          Review / edit master CV
        </button> : null}
      </div>
    </> : null}
    {props.onOpenApplications ? <div className="flow-start-workspaces">
      <button type="button" className="flow-start-browse-button" onClick={props.onOpenApplications}>
        <FileText size={19} aria-hidden="true"/>
        <span><strong>Continue saved drafts &amp; letters</strong><small>Open saved applications and letters</small></span>
        <ArrowRight size={17} aria-hidden="true"/>
      </button>
    </div> : null}
    <div className="flow-start-browse">
      <button type="button" className="flow-start-browse-button"
        disabled={props.busyBrowse} onClick={props.onBrowse}>
        <Search size={19} aria-hidden="true"/>
        <span><strong>Just find jobs</strong><small>Search current jobs without applying</small></span>
        <ArrowRight size={17} aria-hidden="true"/>
      </button>
    </div>
    <p className="flow-start-privacy">Selecting a mode never authorizes sending an application. Employer submissions require applicant review and explicit authorization.</p>
  </section>;
}
