/**
 * SP98: a pure, browser-only and reversible job-CV AI-summary preview.
 *
 * Keep the applicant's complete CV intact. Only a precisely recognized,
 * top-of-document summary block from the existing SP96/SP97 editor is
 * replaceable. Never guess the bounds of a manually moved or damaged block.
 */
export type AISummaryPreview = {
  mode: "insert" | "replace" | "blocked";
  text: string;
  reason: string;
};

const MARKER = "PROFILE SUMMARY (review AI wording):\n";
const MAX_CV = 30_000;
const MAX_SUMMARY = 1_400;

export function prepareAISummaryCV(
  original: string, title: string, company: string, suggestion: string,
): AISummaryPreview {
  const text = original || "";
  const role = title.replace(/\s+/g, " ").trim();
  const employer = company.replace(/\s+/g, " ").trim();
  const summary = suggestion.trim();
  const blocked = (reason: string): AISummaryPreview =>
    ({ mode: "blocked", text, reason });

  if (!role || !employer || !summary || summary.length > MAX_SUMMARY ||
      /[\r\n]/.test(summary)) {
    return blocked("The suggested summary is incomplete or has unsafe formatting. Edit it manually.");
  }
  if (text.length > MAX_CV) return blocked("The CV exceeds the supported editor limit.");
  const header = "TARGET ROLE: " + role + " — " + employer + "\n\n" + MARKER;
  if (text.startsWith(header)) {
    // Exactly one summary paragraph followed by the remainder of the CV.
    const sectionEnd = text.indexOf("\n\n", header.length);
    const originalSummary = sectionEnd < 0 ? "" : text.slice(header.length, sectionEnd);
    const remainder = sectionEnd < 0 ? "" : text.slice(sectionEnd + 2);
    if (!originalSummary.trim() || originalSummary.length > MAX_SUMMARY ||
        originalSummary.includes("\n") || !remainder.trim() ||
        remainder.includes(MARKER) || remainder.startsWith("TARGET ROLE: ")) {
      return blocked(
        "The existing AI summary cannot be safely isolated. Review and edit it manually; no CV text was removed.",
      );
    }
    const proposed = header + summary + "\n\n" + remainder;
    if (proposed.length > MAX_CV) return blocked("The proposed CV exceeds 30,000 characters.");
    return {
      mode: "replace", text: proposed,
      reason: "Only the recognizable AI summary paragraph changes; your remaining CV stays intact.",
    };
  }
  if (text.includes(MARKER) || text.trimStart().startsWith("TARGET ROLE: ")) {
    return blocked(
      "An existing role header or AI summary has custom placement. Edit it manually rather than duplicating or deleting personal wording.",
    );
  }
  const proposed = header + summary + "\n\n" + text;
  if (proposed.length > MAX_CV) return blocked("The proposed CV exceeds 30,000 characters.");
  return {
    mode: "insert", text: proposed,
    reason: "The new role heading and AI summary are added above your unchanged CV.",
  };
}
