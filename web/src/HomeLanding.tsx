import { useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, FileText, Search, UploadCloud } from "lucide-react";
import type { ApplicationFlowMode } from "./types";
import StartChoices from "./StartChoices";

/**
 * V4 Quiet Home: one immediate task, then choose a real application method.
 * This only changes presentation. All mode, upload, browse and application
 * handlers are delegated to the original signed-in App controller.
 *
 * Key this component by server-issued account identity + current CV digest
 * to discard step state if the signed-in user or saved CV changes.
 */
export default function HomeLanding(props: {
  cvPresent: boolean;
  busyBrowse?: boolean;
  busyCV?: boolean;
  onMode: (mode: ApplicationFlowMode) => void;
  onUpload: () => void;
  onCreateCV: () => void;
  onBrowse: () => void;
  onOpenApplications: () => void;
}) {
  const [choosingMethod, setChoosingMethod] = useState(false);
  const ready = props.cvPresent;

  return <div className="sp-solo-home">
    <header className="sp-solo-hero">
      <h1>Apply with confidence</h1>
    </header>
    <section className="sp-solo-task" aria-label="Your next step">
      {choosingMethod && ready ? <>
        <button type="button" className="sp-solo-back"
          onClick={() => setChoosingMethod(false)}>
          <ArrowLeft size={17} aria-hidden="true" /> Back
        </button>
        <div className="sp-solo-methods" id="sp-solo-methods">
          <h2>How would you like to apply?</h2>
          <StartChoices cvPresent
            onMode={props.onMode}
            onBrowse={props.onBrowse}
            busyBrowse={props.busyBrowse}
            onOpenApplications={props.onOpenApplications}
            onUpload={props.onUpload}
            onCreateCV={props.onCreateCV}/>
        </div>
      </> : <>
        {ready ? <p className="sp-solo-status">
          <CheckCircle2 size={18} aria-hidden="true" /> CV saved
        </p> : null}
        <h2>{ready ? "Ready to apply?" : "Start with your CV."}</h2>
        <p className="sp-solo-description">{ready
          ? "Choose how much help you want with your next application."
          : "Upload a PDF or DOCX once. You can review and update it any time."}</p>
        <button type="button" className="sp-solo-primary"
          onClick={ready ? () => setChoosingMethod(true) : props.onUpload}
          disabled={!ready && props.busyCV}
          >
          {ready ? "Choose how to apply" : props.busyCV ? "Uploading CV…" : "Upload your CV"}
          {ready ? <ArrowRight size={19} aria-hidden="true"/> :
            <UploadCloud size={19} aria-hidden="true"/>}
        </button>
        <div className="sp-solo-links" aria-label="Other ways to continue">
          {!ready ? <button type="button" onClick={props.onCreateCV}>
            <FileText size={17} aria-hidden="true" /> Create a CV
          </button> : <button type="button" onClick={props.onCreateCV}>
            <FileText size={17} aria-hidden="true" /> Review your CV
          </button>}
          <button type="button" disabled={props.busyBrowse} onClick={props.onBrowse}>
            <Search size={17} aria-hidden="true" /> Find jobs
          </button>
          <button type="button" onClick={props.onOpenApplications}>
            My applications
          </button>
        </div>
        <p className="sp-solo-privacy">Nothing is sent to an employer without your approval.</p>
      </>}
    </section>
  </div>;
}
