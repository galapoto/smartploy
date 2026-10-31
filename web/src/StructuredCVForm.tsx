import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import {
  emptyCVEntry, emptyCVSection, SECTION_OPTIONS,
  type CVEntry, type CVSection, type CVSectionKind, type StructuredCV,
} from "./structured_cv";

const PROFILE_FIELDS = [
  {key: "name", label: "Full name", placeholder: "Your name"},
  {key: "headline", label: "Professional headline", placeholder: "e.g. Data Analyst · SQL · Power BI"},
  {key: "email", label: "Email", placeholder: "you@example.com"},
  {key: "phone", label: "Phone number", placeholder: "+358 ..."},
  {key: "location", label: "Location", placeholder: "Helsinki, Finland"},
  {key: "links", label: "Portfolio, GitHub or LinkedIn", placeholder: "https://..."},
] as const;

export default function StructuredCVForm(props: {
  value: StructuredCV;
  onChange: (next: StructuredCV) => void;
  disabled?: boolean;
}) {
  const {value: cv, onChange, disabled = false} = props;
  const [sectionToAdd, setSectionToAdd] = useState<CVSectionKind>("experience");
  const update = (patch: Partial<StructuredCV>) => onChange({...cv, ...patch});
  const updateSections = (sections: CVSection[]) => update({sections});
  const updateSection = (index: number, updated: CVSection) =>
    updateSections(cv.sections.map((section, at) => at === index ? updated : section));
  const editEntry = (sectionIndex: number, entryIndex: number, patch: Partial<CVEntry>) => {
    const section = cv.sections[sectionIndex];
    updateSection(sectionIndex, {
      ...section,
      entries: section.entries.map((entry, at) =>
        at === entryIndex ? {...entry, ...patch} : entry),
    });
  };
  const moveSection = (index: number, change: number) => {
    const other = index + change;
    if (other < 0 || other >= cv.sections.length) return;
    const updated = [...cv.sections];
    [updated[index], updated[other]] = [updated[other], updated[index]];
    updateSections(updated);
  };
  const moveEntry = (sectionIndex: number, index: number, change: number) => {
    const current = cv.sections[sectionIndex];
    const other = index + change;
    if (other < 0 || other >= current.entries.length) return;
    const entries = [...current.entries];
    [entries[index], entries[other]] = [entries[other], entries[index]];
    updateSection(sectionIndex, {...current, entries});
  };
  const removeEntry = (sectionIndex: number, index: number) => {
    if (!window.confirm("Remove this CV entry from your unsaved draft?")) return;
    const section = cv.sections[sectionIndex];
    updateSection(sectionIndex, {
      ...section, entries: section.entries.filter((_, at) => at !== index),
    });
  };

  return <div className="structured-cv-form" aria-label="Structured CV fields">
    <div className="structured-cv-field-grid">
      {PROFILE_FIELDS.map(({key, label, placeholder}) =>
        <label key={key}>{label}
          <input type={key === "email" ? "email" : "text"}
            aria-label={label} placeholder={placeholder} disabled={disabled}
            maxLength={500} value={cv[key]} onChange={(event) =>
              update({[key]: event.target.value})}/>
        </label>,
      )}
    </div>
    <label className="structured-cv-wide-field">Professional profile / summary
      <textarea aria-label="Professional profile / summary" rows={4}
        disabled={disabled} value={cv.summary}
        onChange={(event) => update({summary: event.target.value})}
        placeholder="Describe your actual experience, strengths and target role in your own words."/>
    </label>
    <div className="structured-cv-sections-heading">
      <div>
        <strong>Career sections</strong>
        <small>Write only real experience. Add, reorder or remove entries as needed.</small>
      </div>
      <div className="structured-cv-add-section">
        <select aria-label="Section type" disabled={disabled}
          value={sectionToAdd} onChange={(event) => setSectionToAdd(event.target.value as CVSectionKind)}>
          {SECTION_OPTIONS.map(({kind, label}) =>
            <option key={kind} value={kind}>{label}</option>)}
        </select>
        <button type="button" className="outline-btn compact" disabled={disabled || cv.sections.length >= 24}
          onClick={() => updateSections([...cv.sections, emptyCVSection(sectionToAdd)])}>
          <Plus size={15}/> Add section
        </button>
      </div>
    </div>
    {cv.sections.map((section, sectionIndex) => {
      const option = SECTION_OPTIONS.find((item) => item.kind === section.kind)!;
      return <fieldset key={section.id} className="structured-cv-section">
        <legend>{option.label}</legend>
        <div className="structured-cv-order">
          <button type="button" disabled={disabled || sectionIndex === 0}
            aria-label={"Move " + option.label + " section up"}
            onClick={() => moveSection(sectionIndex, -1)}><ArrowUp size={15}/></button>
          <button type="button" disabled={disabled || sectionIndex === cv.sections.length - 1}
            aria-label={"Move " + option.label + " section down"}
            onClick={() => moveSection(sectionIndex, 1)}><ArrowDown size={15}/></button>
          <button type="button" disabled={disabled}
            aria-label={"Remove " + option.label + " section"}
            onClick={() => {
              if (window.confirm("Remove this entire " + option.label + " section from the draft?")) {
                updateSections(cv.sections.filter((_, at) => at !== sectionIndex));
              }
            }}><Trash2 size={15}/></button>
        </div>
        {section.entries.map((entry, entryIndex) =>
          <div className="structured-cv-entry" key={entry.id}>
            <div className="structured-cv-entry-header">
              <strong>{option.label} · {entryIndex + 1}</strong>
              <div className="structured-cv-order">
                <button type="button" disabled={disabled || entryIndex === 0}
                  aria-label={"Move " + option.label + " item " + (entryIndex + 1) + " up"}
                  onClick={() => moveEntry(sectionIndex, entryIndex, -1)}><ArrowUp size={15}/></button>
                <button type="button" disabled={disabled || entryIndex === section.entries.length - 1}
                  aria-label={"Move " + option.label + " item " + (entryIndex + 1) + " down"}
                  onClick={() => moveEntry(sectionIndex, entryIndex, 1)}><ArrowDown size={15}/></button>
                <button type="button" disabled={disabled}
                  aria-label={"Remove " + option.label + " item " + (entryIndex + 1)}
                  onClick={() => removeEntry(sectionIndex, entryIndex)}><Trash2 size={15}/></button>
              </div>
            </div>
            <div className="structured-cv-field-grid">
              {[
                ["title", option.titleLabel],
                ["organization", option.organizationLabel],
                ["period", "Dates or status"],
                ["location", "Location or URL"],
              ].map(([key, label]) => <label key={key}>
                {label}
                <input type="text" disabled={disabled} maxLength={700}
                  aria-label={option.label + " " + (entryIndex + 1) + " " + label}
                  value={entry[key as keyof CVEntry]}
                  onChange={(event) => editEntry(sectionIndex, entryIndex, {[key]: event.target.value})}/>
              </label>)}
            </div>
            <label className="structured-cv-wide-field">
              Description / achievements (only confirmed facts)
              <textarea rows={3} disabled={disabled} maxLength={7000}
                aria-label={option.label + " " + (entryIndex + 1) + " description"}
                value={entry.details} onChange={(event) =>
                  editEntry(sectionIndex, entryIndex, {details: event.target.value})}/>
            </label>
          </div>,
        )}
        <button type="button" className="outline-btn compact" disabled={disabled || section.entries.length >= 25}
          onClick={() => updateSection(sectionIndex, {
            ...section, entries: [...section.entries, emptyCVEntry()],
          })}><Plus size={15}/> Add {option.label.toLowerCase()} item</button>
      </fieldset>;
    })}
    {cv.importedText ? <div className="structured-cv-import">
      <p><strong>Original imported CV text preserved</strong></p>
      <p>We could not safely map all original text to fields. It remains here, unchanged, until you deliberately edit or remove it. Saving still preserves your previous file in version history.</p>
      <label className="structured-cv-wide-field">Imported source text
        <textarea aria-label="Imported source text" rows={6} disabled={disabled}
          value={cv.importedText}
          onChange={(event) => update({importedText: event.target.value})}/>
      </label>
    </div> : null}
  </div>;
}
