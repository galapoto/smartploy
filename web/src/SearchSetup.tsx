import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BriefcaseBusiness, Check, Compass, Globe2, MapPin, RotateCcw, SlidersHorizontal, Sparkles } from "lucide-react";
import type { SearchPreferences, SearchPreferencesUpdate } from "./types";

const WORK_MODES = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
] as const;

const LANGUAGES = [
  { value: "english", label: "English" },
  { value: "finnish", label: "Finnish" },
  { value: "swedish", label: "Swedish" }
] as const;

const SENIORITY = [
  { value: "any", label: "Any level" },
  { value: "entry", label: "Entry / junior" },
  { value: "mid", label: "Mid-level" },
  { value: "senior", label: "Senior" }
] as const;

function list(input: string): string[] {
  return [...new Set(input.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean))];
}
function toggle(current: string[], choice: string): string[] {
  return current.includes(choice) ? current.filter((entry) => entry !== choice) : [...current, choice];
}

export default function SearchSetup(props: {
  initial: SearchPreferences;
  settings?: boolean;
  onSave: (value: SearchPreferencesUpdate) => Promise<void>;
  onCancel?: () => void;
}) {
  const [mode, setMode] = useState<"personalized" | "general">(props.initial.mode);
  const [roles, setRoles] = useState(props.initial.roles.join(", "));
  const [locations, setLocations] = useState(props.initial.locations.join(", "));
  const [keywords, setKeywords] = useState(props.initial.keywords.join(", "));
  const [skills, setSkills] = useState(props.initial.skills.join(", "));
  const [languages, setLanguages] = useState(props.initial.languages);
  const [workModes, setWorkModes] = useState(props.initial.work_modes);
  const [seniority, setSeniority] = useState(props.initial.seniority);
  const [autoDrafts, setAutoDrafts] = useState(props.initial.auto_drafts_enabled === true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  // The initial form state was already hydrated by useState. A redundant
  // mount-time effect can overwrite an immediate General-mode click when
  // the parent is still finishing its asynchronous workspace loading.
  // Only an actual saved preference revision should replace local edits.
  const hydratedRevision = useRef(props.initial.revision);

  useEffect(() => {
    if (hydratedRevision.current === props.initial.revision) return;
    hydratedRevision.current = props.initial.revision;
    setMode(props.initial.mode);
    setRoles(props.initial.roles.join(", "));
    setLocations(props.initial.locations.join(", "));
    setKeywords(props.initial.keywords.join(", "));
    setSkills(props.initial.skills.join(", "));
    setLanguages(props.initial.languages);
    setWorkModes(props.initial.work_modes);
    setSeniority(props.initial.seniority);
    setAutoDrafts(props.initial.auto_drafts_enabled === true);
  }, [props.initial.revision]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const chosenRoles = list(roles);
    const chosenKeywords = list(keywords);
    if (mode === "personalized" && !chosenRoles.length && !chosenKeywords.length) {
      setError("Enter at least one job title or search keyword, or choose general search.");
      return;
    }
    setError("");
    setWorking(true);
    try {
      await props.onSave({
        mode, roles: chosenRoles, locations: list(locations),
        keywords: chosenKeywords, skills: list(skills),
        languages, work_modes: workModes, seniority,
        auto_drafts_enabled: mode === "personalized" && autoDrafts,
        expected_revision: props.initial.revision
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save your job criteria.");
    } finally { setWorking(false); }
  }

  return <section className={"search-setup" + (props.settings ? " embedded" : "")}
    aria-label="Job discovery settings">
    {!props.settings ? <div className="setup-intro">
      <span className="setup-spark"><Sparkles size={24} /></span>
      <span className="section-kicker">WELCOME TO SMARTPLOY</span>
      <h1>Find work that fits your goals.</h1>
      <p>Tell us what you want to do, or browse every available job without sharing personal criteria. You can change this at any time in Settings.</p>
    </div> : <div className="setup-intro compact-intro">
      <span className="section-kicker">YOUR SEARCH EXPERIENCE</span>
      <h2>Job search preferences</h2>
      <p>Adjust your targets whenever your plans change. General search ignores these personal criteria.</p>
    </div>}

    <form onSubmit={(event) => void save(event)} className="setup-form">
      <div className="setup-choice-grid" role="radiogroup" aria-label="Job search mode">
        <label className={"setup-choice" + (mode === "personalized" ? " chosen" : "")}>
          <input type="radio" name="job-mode" checked={mode === "personalized"}
            onChange={() => setMode("personalized")} />
          <span className="setup-choice-icon"><SlidersHorizontal size={21} /></span>
          <strong>Personalized jobs</strong>
          <small>Rank opportunities by the job titles, locations and work arrangements you choose.</small>
          {mode === "personalized" ? <Check className="setup-choice-check" size={17}/> : null}
        </label>
        <label className={"setup-choice" + (mode === "general" ? " chosen" : "")}>
          <input type="radio" name="job-mode" checked={mode === "general"}
            onChange={() => setMode("general")} />
          <span className="setup-choice-icon"><Globe2 size={21} /></span>
          <strong>General job search</strong>
          <small>Explore every current job. No profile, CV, or search preferences required.</small>
          {mode === "general" ? <Check className="setup-choice-check" size={17}/> : null}
        </label>
      </div>

      {mode === "personalized" ? <div className="setup-fields">
        <div className="setup-fields-heading"><BriefcaseBusiness size={18}/><strong>Your ideal opportunities</strong><small>Only job titles or keywords are required.</small></div>
        <button type="button" className="outline-btn compact" onClick={() => {
          setRoles("Data Analyst, Junior Data Analyst, Business Analyst, QA Engineer, Software Tester, IT Support Specialist, Junior Data Engineer");
          setLanguages(["finnish", "english"]);
          setSeniority("any");
        }}>
          <BriefcaseBusiness size={15}/> Start with IT, data and QA roles
        </button>
        <div className="setup-field-grid">
          <label className="setup-field">
            <span>Target roles <em>Recommended</em></span>
            <textarea rows={2} value={roles} onChange={(e) => setRoles(e.target.value)}
              placeholder="Data analyst, Junior software tester, Project coordinator"
              maxLength={1090} />
            <small>Separate multiple job titles with commas. We will look for related titles too.</small>
          </label>
          <label className="setup-field">
            <span>Preferred locations</span>
            <textarea rows={2} value={locations} onChange={(e) => setLocations(e.target.value)}
              placeholder="Helsinki, Espoo, Vantaa" maxLength={1090} />
            <small>Leave empty if you are open to all of Finland.</small>
          </label>
          <label className="setup-field">
            <span>Search keywords</span>
            <input value={keywords} onChange={(e) => setKeywords(e.target.value)}
              placeholder="Python, business analysis, documentation" maxLength={740} />
            <small>Helpful for roles with different job titles.</small>
          </label>
          <label className="setup-field">
            <span>Skills and tools you have <em>Optional</em></span>
            <input value={skills} onChange={(e) => setSkills(e.target.value)}
              placeholder="SQL, Python, nursing, Power BI" maxLength={990} />
            <small>Used only to compare job descriptions. Skills are not treated as verified CV facts until separately approved.</small>
          </label>
          <label className="setup-field">
            <span>Experience level</span>
            <select value={seniority} onChange={(e) => setSeniority(e.target.value)}>
              {SENIORITY.map((level) => <option key={level.value} value={level.value}>{level.label}</option>)}
            </select>
            <small>Jobs that do not specify a level are marked uncertain, not rejected.</small>
          </label>
        </div>
        <fieldset className="setup-check-options">
          <legend><MapPin size={15}/> Work arrangements</legend>
          <div>{WORK_MODES.map((choice) => <label key={choice.value}>
            <input type="checkbox" checked={workModes.includes(choice.value)}
              onChange={() => setWorkModes(toggle(workModes, choice.value))}/>{choice.label}
          </label>)}</div>
        </fieldset>
        <fieldset className="setup-check-options">
          <legend><Compass size={15}/> Job advertisement languages</legend>
          <div>{LANGUAGES.map((choice) => <label key={choice.value}>
            <input type="checkbox" checked={languages.includes(choice.value)}
              onChange={() => setLanguages(toggle(languages, choice.value))}/>{choice.label}
          </label>)}</div>
          <small>Languages are used only where the employer has provided enough information to assess them.</small>
        </fieldset>
        <label className="setup-choice">
          <input type="checkbox" checked={autoDrafts}
            onChange={(event) => setAutoDrafts(event.target.checked)}/>
          <span className="setup-choice-icon"><Sparkles size={20}/></span>
          <strong>Automatically find matching IT jobs and prepare my drafts</strong>
          <small>Opt in to private local draft preparation from verified current postings,
            up to five new drafts daily. You can turn this off at any time.
            CVs and cover letters still require your review. No AI provider
            forwarding, employer application or final submission occurs automatically.</small>
        </label>
        <p className="setup-fineprint">The results are ranked by your stated search preferences, not a guarantee that you meet every employer requirement. You can upload a CV and approve career evidence separately for stronger qualification checks.</p>
      </div> : <div className="setup-general-note">
        <Globe2 size={19}/><p>All available jobs will be shown, newest first. You can still search by keyword and filter by employer sector, but SmartPloy will not score jobs against your profile.</p>
      </div>}

      {error ? <p className="setup-error" role="alert">{error}</p> : null}
      <div className="setup-footer">
        {props.settings && props.onCancel ? <button type="button" className="outline-btn"
          disabled={working} onClick={props.onCancel}>Cancel</button> : null}
        <button className="primary-btn" type="submit" disabled={working}>
          {working ? <RotateCcw size={16} className="rotate"/> : <ArrowRight size={16}/>}
          {working ? "Saving…" : props.settings ? "Save search preferences" :
            mode === "general" ? "Browse all jobs" : "Show my matched jobs"}
        </button>
      </div>
    </form>
  </section>;
}
