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
    <div className="flow-start-heading">
      <p className="section-kicker">YOUR APPLICATION JOURNEY</p>
      <h1>{hasCV ? "CV connected. Choose how to apply." : "Start with your CV."}</h1>
      <p>{hasCV
        ? "Your CV is ready. Pick Manual, Assisted or Automatic to see the right job-matching and application steps."
        : "Upload your existing CV or create a new one. Then choose Manual, Assisted or Automatic. No application will be sent by connecting a CV."}</p>
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
          <p>Start with a PDF/DOCX file or build a CV in SmartPloy. Your information stays private until you explicitly approve an employer action.</p>
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
        <span><strong>Step 2 unlocks after your CV is saved.</strong> Manual, Assisted and Automatic choices appear here next. You can still browse jobs without a CV.</span>
      </div>
    </> : <>
      <div className="flow-start-ready" role="status">
        <CheckCircle2 size={20} aria-hidden="true"/>
        <span><strong>CV connected.</strong> Step 1 is complete. Choose Manual, Assisted or Automatic. Review extracted facts before submitting an application.</span>
      </div>
      <div className="flow-start-grid flow-start-grid-methods" role="group"
        aria-label="Step 2 — choose application type">
        <button type="button" className="flow-start-card"
          onClick={() => props.onMode("manual")}>
          <FileCheck2 size={25} aria-hidden="true"/>
          <strong>Apply manually</strong>
          <span>Find CV-matched jobs, open the original employer form and submit it yourself.</span>
          <small>MANUAL · You send the application</small>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
        <button type="button" className="flow-start-card"
          onClick={() => props.onMode("assisted")}>
          <WandSparkles size={25} aria-hidden="true"/>
          <strong>Assisted · Apply with AI</strong>
          <span>Prepare a job-specific CV and complete cover letter. Review and fill supported employer forms with the browser companion.</span>
          <small>ASSISTED · You review before sending</small>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
        <button type="button" className="flow-start-card"
          onClick={() => props.onMode("automatic")}>
          <Bot size={25} aria-hidden="true"/>
          <strong>Automatic · AutoApply</strong>
          <span>Prepare multiple matched jobs, then approve exact reviewed submissions where the employer has authorized a Lever/Ashby integration.</span>
          <small>AUTOMATIC · Employer-specific authorization required</small>
          <ArrowRight size={17} aria-hidden="true"/>
        </button>
      </div>
      <div className="flow-start-cv-actions">
        {props.onUpload ? <button type="button" className="text-link" onClick={props.onUpload}>
          Replace connected CV
        </button> : null}
        {props.onCreateCV ? <button type="button" className="text-link" onClick={props.onCreateCV}>
          Review / edit master CV
        </button> : null}
      </div>
    </>}
    {props.onOpenApplications ? <div className="flow-start-workspaces">
      <button type="button" className="flow-start-browse-button" onClick={props.onOpenApplications}>
        <FileText size={19} aria-hidden="true"/>
        <span><strong>My applications &amp; cover letters</strong><small>Open saved applications, review full letters and return to drafts</small></span>
        <ArrowRight size={17} aria-hidden="true"/>
      </button>
    </div> : null}
    <div className="flow-start-browse">
      <button type="button" className="flow-start-browse-button"
        disabled={props.busyBrowse} onClick={props.onBrowse}>
        <Search size={19} aria-hidden="true"/>
        <span><strong>Just find jobs</strong><small>Browse Finland-wide openings without creating an application</small></span>
        <ArrowRight size={17} aria-hidden="true"/>
      </button>
    </div>
    <p className="flow-start-privacy">Selecting a mode never authorizes sending an application. SmartPloy requires applicant review and independently authorized employer rights for real automated submission.</p>
  </section>;
}
