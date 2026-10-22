import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, GraduationCap, MapPin, Search } from "lucide-react";
import { getTrainingPrograms } from "./api";
import { safeExternalJobUrl } from "./lib";
import type { TrainingProgram } from "./types";

const KIND_LABELS: Record<TrainingProgram["kind"], string> = {
  recruitment_training: "Recruitment training",
  academy: "Intensive academy",
  employer_trainee: "Employer trainee route",
  internship_portal: "Public internships",
};

export default function TrainingProgramsPanel() {
  const [programs, setPrograms] = useState<TrainingProgram[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | TrainingProgram["kind"]>("all");

  useEffect(() => {
    let active = true;
    void getTrainingPrograms().then((result) => {
      if (!active) return;
      setPrograms(result.programs);
      setError("");
    }).catch(() => {
      if (active) setError("Training directories are unavailable. Try again after refreshing SmartPloy.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const shown = useMemo(() => programs.filter((program) => {
    if (kind !== "all" && program.kind !== kind) return false;
    const haystack = [program.provider, program.title, program.region, ...program.focus]
      .join(" ").toLocaleLowerCase();
    return !query.trim() || haystack.includes(query.trim().toLocaleLowerCase());
  }), [programs, query, kind]);

  return <section className="panel jobs-panel" aria-label="Training and trainee opportunities">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">FINLAND CAREER PATHWAYS</p>
        <h2>Training, internships & trainee programmes</h2>
        <p>Explore official provider destinations for Saranen RekryKoulutus, academies,
          employer graduate routes and public-sector internships.</p>
      </div>
      <GraduationCap size={27} aria-hidden="true" />
    </div>
    <div className="studio-packet-fallback" role="note">
      <strong>Provider directory — not confirmed open applications</strong>
      <p>These links are places to check for programmes, not active employer vacancies.
        Dates, pay, eligibility, study requirements and available places must be checked
        on the organizer's website. They are not counted as SmartPloy jobs and
        cannot trigger automatic applications.</p>
    </div>
    <div className="job-filter-bar">
      <label className="filter-right">
        <Search size={17} aria-hidden="true" />
        <input type="search" aria-label="Find trainee programme provider" value={query}
          placeholder="Saranen, Microsoft, data, office…" onChange={(e) => setQuery(e.target.value)} />
      </label>
      <select aria-label="Training programme category" value={kind}
        onChange={(e) => setKind(e.target.value as typeof kind)}>
        <option value="all">All programme routes</option>
        <option value="recruitment_training">RekryKoulutus</option>
        <option value="academy">Academies</option>
        <option value="employer_trainee">Employer programmes</option>
        <option value="internship_portal">Internship portals</option>
      </select>
    </div>
    {loading ? <p role="status" className="muted">Loading training destinations…</p> :
      error ? <p role="alert">{error}</p> :
      <><p role="status" className="muted">
        {shown.length} provider destinations shown. These are not current vacancy counts.
      </p>
      <div className="job-list">
        {shown.map((program) => {
          const url = safeExternalJobUrl(program.url);
          return <article className="job-item search-result-card" key={program.id}>
            <span className="job-avatar" aria-hidden="true"><BookOpen size={20}/></span>
            <div className="job-details">
              <div className="job-title-line">
                <h3>{program.title}</h3>
                <span className="quiet-chip">{KIND_LABELS[program.kind]}</span>
              </div>
              <p className="job-byline"><strong>{program.provider}</strong>
                <span><MapPin size={13} />{program.region}</span>
              </p>
              <div className="job-meta">
                {program.focus.map((focus) => <span key={focus}>{focus}</span>)}
              </div>
              <p className="muted">{program.eligibility_note}</p>
              <small>Intake status: check provider. No CV, profile or application is sent.</small>
            </div>
            <div className="job-buttons">
              {url ? <a className="outline-btn compact" href={url}
                target="_blank" rel="noopener noreferrer">
                Open provider website <ArrowUpRight size={14} />
              </a> : <span role="note">Provider link unavailable</span>}
            </div>
          </article>;
        })}
        {!shown.length ? <div className="empty-state">
          <h3>No matching providers</h3>
          <p>Try a broader category or a different search phrase.</p>
        </div> : null}
      </div></>}
  </section>;
}
