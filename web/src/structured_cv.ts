/** SP80 structured master-CV format.
 *
 * The rendered text is human-readable and is the same active CV used by
 * existing SmartPloy matching, DOCX/PDF exports and application workspaces.
 * Parsing is deliberately strict: a format we cannot reconstruct exactly is
 * treated as imported source text, never silently dropped or "fixed" by AI.
 */
export type CVSectionKind =
  | "experience" | "education" | "projects" | "skills"
  | "certifications" | "languages" | "additional";

export interface CVEntry {
  id: string;
  title: string;
  organization: string;
  period: string;
  location: string;
  details: string;
}
export interface CVSection {
  id: string;
  kind: CVSectionKind;
  entries: CVEntry[];
}
export interface StructuredCV {
  name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  links: string;
  summary: string;
  sections: CVSection[];
  importedText: string;
}

export const SECTION_OPTIONS: ReadonlyArray<{
  kind: CVSectionKind; label: string; titleLabel: string; organizationLabel: string;
}> = [
  { kind: "experience", label: "Work experience", titleLabel: "Role or position", organizationLabel: "Employer" },
  { kind: "education", label: "Education", titleLabel: "Qualification / degree", organizationLabel: "Institution" },
  { kind: "projects", label: "Projects", titleLabel: "Project name", organizationLabel: "Project or client context" },
  { kind: "skills", label: "Skills", titleLabel: "Skill or technology", organizationLabel: "Context / level" },
  { kind: "certifications", label: "Certifications", titleLabel: "Credential name", organizationLabel: "Issuer" },
  { kind: "languages", label: "Languages", titleLabel: "Language", organizationLabel: "Proficiency" },
  { kind: "additional", label: "Other information", titleLabel: "Item", organizationLabel: "Context" },
];

const MARKERS: Record<CVSectionKind, string> = {
  experience: "EXPERIENCE",
  education: "EDUCATION",
  projects: "PROJECTS",
  skills: "SKILLS",
  certifications: "CERTIFICATIONS",
  languages: "LANGUAGES",
  additional: "OTHER INFORMATION",
};
const BY_MARKER = new Map(Object.entries(MARKERS).map(([kind, marker]) => [
  marker, kind as CVSectionKind,
]));
const PROFILE_KEYS = [
  ["Full name:", "name"], ["Headline:", "headline"],
  ["Email:", "email"], ["Phone:", "phone"], ["Location:", "location"],
  ["Links:", "links"],
] as const;
let serial = 0;
function id(prefix: string): string { serial += 1; return prefix + "-" + serial; }

export function emptyCVEntry(): CVEntry {
  return {id: id("cv-entry"), title: "", organization: "", period: "", location: "", details: ""};
}
export function emptyCVSection(kind: CVSectionKind): CVSection {
  return {id: id("cv-section"), kind, entries: [emptyCVEntry()]};
}
export function emptyStructuredCV(): StructuredCV {
  return {
    name: "", headline: "", email: "", phone: "", location: "", links: "",
    summary: "", sections: [], importedText: "",
  };
}

function oneline(value: string): string {
  return value.replace(/[\r\n\t]+/g, " ").trim();
}
function indent(value: string): string[] {
  return value.replace(/\r\n?/g, "\n").split("\n").map((line) => "  " + line);
}
function appendBlock(lines: string[], name: string, value: string): void {
  lines.push(name);
  if (value) lines.push(...indent(value));
}
function populated(entry: CVEntry): boolean {
  return !![entry.title, entry.organization, entry.period, entry.location, entry.details]
    .some((part) => part.trim());
}

/** Serialize a CV to document-ready plain text with reversible field boundaries. */
export function renderStructuredCV(cv: StructuredCV): string {
  const lines: string[] = PROFILE_KEYS.map(([key, field]) => key + " " + oneline(cv[field]));
  lines.push("");
  appendBlock(lines, "PROFILE", cv.summary);
  for (const section of cv.sections) {
    const entries = section.entries.filter(populated);
    if (!entries.length) continue;
    lines.push("", MARKERS[section.kind]);
    for (const [index, entry] of entries.entries()) {
      if (index) lines.push("");
      lines.push(
        "Title: " + oneline(entry.title),
        "Organization: " + oneline(entry.organization),
        "Period: " + oneline(entry.period),
        "Location: " + oneline(entry.location),
        "Details:",
      );
      if (entry.details) lines.push(...indent(entry.details));
    }
  }
  if (cv.importedText) {
    lines.push("");
    appendBlock(lines, "IMPORTED SOURCE TEXT", cv.importedText);
  }
  return lines.join("\n").trimEnd();
}

function block(lines: string[], at: number): {value: string; next: number} {
  const content: string[] = [];
  while (at < lines.length && lines[at].startsWith("  ")) {
    content.push(lines[at].slice(2));
    at += 1;
  }
  return {value: content.join("\n"), next: at};
}

export function parseStructuredCV(text: string): StructuredCV | null {
  if (typeof text !== "string") return null;
  const normalized = text.replace(/\r\n?/g, "\n").trimEnd();
  const lines = normalized.split("\n");
  if (lines.length < 8) return null;
  const cv = emptyStructuredCV();
  for (let i = 0; i < PROFILE_KEYS.length; i += 1) {
    const [key, field] = PROFILE_KEYS[i];
    if (!lines[i].startsWith(key + " ")) return null;
    cv[field] = lines[i].slice(key.length + 1);
  }
  if (lines[6] !== "" || lines[7] !== "PROFILE") return null;
  let at = 8;
  const summary = block(lines, at);
  cv.summary = summary.value;
  at = summary.next;
  const usedImported = {value: false};
  while (at < lines.length) {
    if (lines[at] !== "") return null;
    at += 1;
    const label = lines[at];
    if (!label) return null;
    at += 1;
    if (label === "IMPORTED SOURCE TEXT") {
      if (usedImported.value || at > lines.length) return null;
      usedImported.value = true;
      const source = block(lines, at);
      cv.importedText = source.value;
      at = source.next;
      if (at !== lines.length) return null;
      continue;
    }
    const kind = BY_MARKER.get(label);
    if (!kind) return null;
    const entries: CVEntry[] = [];
    // An entry always begins with Title; the blank line separates entries
    // from following sections in the only supported reversible grammar.
    while (at < lines.length && lines[at].startsWith("Title: ")) {
      const title = lines[at++].slice(7);
      const fields = ["Organization: ", "Period: ", "Location: ", "Details:"];
      if (at + 4 > lines.length || fields.some((item, i) =>
        i === 3 ? lines[at + i] !== item : !lines[at + i].startsWith(item)
      )) return null;
      const organization = lines[at++].slice(fields[0].length);
      const period = lines[at++].slice(fields[1].length);
      const location = lines[at++].slice(fields[2].length);
      at += 1; // Details:
      const details = block(lines, at);
      at = details.next;
      entries.push({
        id: id("cv-entry"), title, organization, period, location,
        details: details.value,
      });
      if (at < lines.length && lines[at] === "" &&
          lines[at + 1]?.startsWith("Title: ")) at += 1;
      else break;
    }
    if (!entries.length) return null;
    cv.sections.push({id: id("cv-section"), kind, entries});
  }
  // Reject any malformed, unknown or incomplete conversion. No input loss.
  return renderStructuredCV(cv) === normalized ? cv : null;
}

export function structuredFromSource(text: string): {
  model: StructuredCV; origin: "structured" | "imported" | "blank";
} {
  if (!text.trim()) return {model: emptyStructuredCV(), origin: "blank"};
  const found = parseStructuredCV(text);
  if (found) return {model: found, origin: "structured"};
  const model = emptyStructuredCV();
  model.importedText = text; // exact applicant text is carried into the new document.
  return {model, origin: "imported"};
}

export function cvHasApplicantContent(cv: StructuredCV): boolean {
  return !!cv.name.trim() && !!(
    cv.summary.trim() || cv.importedText.trim() ||
    cv.sections.some((section) => section.entries.some(populated))
  );
}
