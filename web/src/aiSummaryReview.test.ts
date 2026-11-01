import { describe, expect, it } from "vitest";
import { prepareAISummaryCV } from "./aiSummaryReview";

const role = "Junior Data Analyst";
const company = "Example Oy";
const original = "Alex Applicant\n\nSKILLS\nPython\n\nPROJECTS\nReporting dashboard";
const summary = "A verified Python and reporting candidate.";

describe("SP98: human-controlled job-CV AI summary preview", () => {
  it("inserts a visibly scoped summary while preserving the full original CV", () => {
    const result = prepareAISummaryCV(original, role, company, summary);
    expect(result.mode).toBe("insert");
    expect(result.text).toContain("TARGET ROLE: Junior Data Analyst — Example Oy");
    expect(result.text).toContain("PROFILE SUMMARY (review AI wording):\n" + summary);
    expect(result.text.endsWith(original)).toBe(true);
    expect(original).not.toContain("PROFILE SUMMARY");
  });

  it("can re-tailor ONLY a recognized generated summary without duplicating or erasing the CV", () => {
    const first = prepareAISummaryCV(original, role, company, summary);
    const revised = prepareAISummaryCV(first.text, role, company, "Revised approved skills summary.");
    expect(revised.mode).toBe("replace");
    expect(revised.text).toContain("Revised approved skills summary.");
    expect(revised.text).not.toContain(summary);
    expect(revised.text.endsWith(original)).toBe(true);
    expect(revised.text.match(/PROFILE SUMMARY \(review AI wording\):/g)?.length).toBe(1);
  });

  it("refuses ambiguous manual moves and other-job headings rather than deleting applicant wording", () => {
    const first = prepareAISummaryCV(original, role, company, summary).text;
    for (const altered of [
      "Moved paragraph\n\n" + first,
      first.replace("Junior Data Analyst", "Different Job"),
      first.replace("\n\n" + original, "\nUnclosed summary paragraph"),
      first.replace(summary, "First paragraph.\n\nSecond manual paragraph."),
    ]) {
      const result = prepareAISummaryCV(altered, role, company, "New summary");
      if (result.mode === "replace") {
        // Paragraph content after a manual separator must stay byte-for-byte
        // in the remaining CV rather than being erased as a guess.
        expect(result.text).toContain("Second manual paragraph.");
      } else {
        expect(result.mode).toBe("blocked");
        expect(result.text).toBe(altered);
      }
    }
  });

  it("fails closed on multiline, oversized or missing model output and CV overflow", () => {
    for (const bad of ["", "Text\nOther paragraph", "x".repeat(1401)]) {
      const result = prepareAISummaryCV(original, role, company, bad);
      expect(result.mode).toBe("blocked");
      expect(result.text).toBe(original);
    }
    expect(prepareAISummaryCV("x".repeat(29999), role, company, summary).mode)
      .toBe("blocked");
  });
});
