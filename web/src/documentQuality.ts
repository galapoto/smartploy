/**
 * SP96: immediate, deterministic document hygiene hints. This module never
 * calls an AI service, stores personal data or verifies applicant claims.
 * Its findings are advisory and must never gate saves or employer rights.
 */
export type DocumentQualityKind = "master_cv" | "job_cv" | "cover_letter";

export interface DocumentQualityInput {
  kind: DocumentQualityKind;
  text: string;
  roleTitle?: string;
  company?: string;
}

export interface DocumentQualityCheck {
  id: string;
  label: string;
  guidance: string;
  passed: boolean;
}

export interface DocumentQualityResult {
  title: string;
  checks: DocumentQualityCheck[];
  passed: number;
  total: number;
  summary: string;
}

const PLACEHOLDER = /(?:\b(?:lorem ipsum|tbd|todo|insert your|replace this|your name|your company)\b|\[(?:your\s+)?(?:name|company|job title|role|date|experience|contact|email|phone|skill|example)\])/i;
const CONTACT = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\b(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\//i;
const CAREER = /\b(?:experience|employment|work history|career history|työkokemus|kokemus|projects?|projektit?|harjoittelu|työura)\b/i;
const SKILLS = /\b(?:skills?|osaaminen|taidot|teknologiat|technologies|technical|tools|työkalut)\b/i;
const QUALIFICATIONS = /\b(?:education|degrees?|koulutus|opinnot|tutkinto|training|certification|sertifikaatti)\b/i;
const RESULTS = /\b\d+(?:[.,]\d+)?\s?(?:%|€|hours?|months?|weeks?|users?|clients?|projects?|cases?|tickets?|customers?|requests?)\b/i;
const LETTER_OPENING = /\b(?:dear|hello|hi|hyvä|hei|arvoisa|haen|olen kiinnostunut|i am applying)\b/i;
const LETTER_ENDING = /\b(?:kind regards|best regards|sincerely|yours faithfully|yours sincerely|thank you|ystävällisin terveisin|terveisin|kunnioittavasti)\b/i;

function matchesExactJob(text: string, value?: string): boolean {
  if (!value || value.trim().length < 4) return true;
  return text.toLocaleLowerCase().includes(value.trim().toLocaleLowerCase());
}

function check(id: string, label: string, guidance: string, passed: boolean): DocumentQualityCheck {
  return { id, label, guidance, passed };
}

export function reviewDocument(input: DocumentQualityInput): DocumentQualityResult {
  const content = input.text || "";
  const meaningful = content.trim();
  const wordCount = meaningful.split(/\s+/).filter(Boolean).length;
  let checks: DocumentQualityCheck[];
  let title: string;

  if (input.kind === "cover_letter") {
    title = "Cover letter";
    const paragraphs = meaningful.split(/\n\s*\n/).map((row) => row.trim()).filter(Boolean);
    checks = [
      check("letter-content", "Substantive letter",
        "Aim for at least 65 words of job-specific prose; edit the generated draft rather than sending a template.",
        wordCount >= 65),
      check("letter-opening", "Purposeful opening",
        "Use a greeting or a clear statement of the role you are applying for.",
        LETTER_OPENING.test(content)),
      check("letter-job", "Correct position",
        "Verify the exact role title in the employer posting and mention it naturally.",
        matchesExactJob(content, input.roleTitle)),
      check("letter-company", "Correct employer",
        "Name the actual employer, not a generic or different company.",
        matchesExactJob(content, input.company)),
      check("letter-structure", "Readable paragraphs",
        "Separate your motivation, relevant factual examples and conclusion into paragraphs.",
        paragraphs.length >= 3),
      check("letter-ending", "Professional ending",
        "Add an appropriate English or Finnish closing.",
        LETTER_ENDING.test(content)),
      check("letter-placeholders", "No unfinished placeholders",
        "Replace [Name], TBD and other template prompts before considering the letter complete.",
        !PLACEHOLDER.test(content)),
    ];
  } else {
    title = input.kind === "master_cv" ? "Master CV" : "Job-specific CV";
    checks = [
      check("cv-content", "Enough content to review",
        "Include your real professional summary, experience or projects, and relevant qualifications.",
        meaningful.length >= 160 && wordCount >= 25),
      check("cv-contact", "Contact route",
        "Before exporting, review an email address or LinkedIn profile you want to share with employers.",
        CONTACT.test(content)),
      check("cv-evidence", "Work or project evidence",
        "Describe work, placements, internships or projects you actually completed.",
        CAREER.test(content)),
      check("cv-skills", "Skills and tools",
        "Include a clearly labeled skills section with technologies or methods you can demonstrate.",
        SKILLS.test(content)),
      check("cv-education", "Education or training",
        "List real qualifications and relevant completed training with accurate dates.",
        QUALIFICATIONS.test(content)),
      check("cv-impact", "Specific results",
        "When you can substantiate them, add measurable achievements rather than broad claims.",
        RESULTS.test(content)),
      check("cv-placeholders", "No unfinished placeholders",
        "Remove unfinished template prompts. Do not fill gaps with invented qualifications.",
        !PLACEHOLDER.test(content)),
    ];
  }

  const passed = checks.filter((item) => item.passed).length;
  const remaining = checks.length - passed;
  return {
    title, checks, passed, total: checks.length,
    summary: remaining === 0
      ? "All writing checks met. Still verify every claim, role and employer detail yourself."
      : remaining + " writing check" + (remaining === 1 ? "" : "s") +
        " worth reviewing. Suggestions are guidance, not verified facts or a hiring score.",
  };
}
