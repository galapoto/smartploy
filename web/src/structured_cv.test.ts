import { describe, expect, it } from "vitest";
import {
  cvHasApplicantContent, emptyCVSection, emptyStructuredCV,
  parseStructuredCV, renderStructuredCV, structuredFromSource,
} from "./structured_cv";

describe("SP80 structured CV text fidelity and safe conversion", () => {
  it("round-trips repeated experiences, dates, tools, multiline results and section order", () => {
    const model = emptyStructuredCV();
    model.name = "Synthetic Applicant";
    model.headline = "Junior Data Analyst";
    model.email = "synthetic@example.invalid";
    model.phone = "+358 40 123 4567";
    model.location = "Helsinki, Finland";
    model.links = "https://portfolio.example.invalid";
    model.summary = "Python, SQL and reporting.\nSeeking junior data roles.";
    const work = emptyCVSection("experience");
    work.entries[0] = {
      ...work.entries[0], title: "Analyst", organization: "Employer Oy",
      period: "2024–2025", location: "Finland",
      details: "Designed test cases.\n\nWrote SQL and dashboards.",
    };
    work.entries.push({
      ...work.entries[0], id: "second-role", title: "Trainee",
      organization: "Second company", period: "2022",
      location: "Tampere", details: "Documented test results.",
    });
    const education = emptyCVSection("education");
    education.entries[0] = {
      ...education.entries[0], title: "Bachelor's degree", organization: "University",
      period: "2019", details: "Completed coursework",
    };
    model.sections = [work, education];
    const text = renderStructuredCV(model);
    expect(text).toContain("EXPERIENCE");
    expect(text).toContain("EDUCATION");
    expect(text.indexOf("EXPERIENCE")).toBeLessThan(text.indexOf("EDUCATION"));
    expect(text).toContain("Designed test cases.\n  \n  Wrote SQL");
    const parsed = parseStructuredCV(text);
    expect(parsed).not.toBeNull();
    expect(parsed?.name).toBe("Synthetic Applicant");
    expect(parsed?.sections.map(s => s.kind)).toEqual(["experience", "education"]);
    expect(parsed?.sections[0].entries.map(x => x.title)).toEqual(["Analyst", "Trainee"]);
    expect(parsed?.sections[0].entries[0].details)
      .toBe("Designed test cases.\n\nWrote SQL and dashboards.");
    expect(renderStructuredCV(parsed!)).toBe(text);
    expect(cvHasApplicantContent(parsed!)).toBe(true);
  });

  it("never tries to reinterpret a free-form original CV as editable claims", () => {
    const original = [
      "Alex Applicant", "Old experience", "EXPERIENCE",
      "Title: Example", "Do not claim a qualification I do not have",
    ].join("\n");
    expect(parseStructuredCV(original)).toBeNull();
    const conversion = structuredFromSource(original);
    expect(conversion.origin).toBe("imported");
    expect(conversion.model.importedText).toBe(original);
    expect(conversion.model.sections).toEqual([]);
    expect(conversion.model.summary).toBe("");
    expect(cvHasApplicantContent(conversion.model)).toBe(false);
    conversion.model.name = "Alex Applicant";
    const preview = renderStructuredCV(conversion.model);
    expect(preview).toContain("IMPORTED SOURCE TEXT");
    expect(preview).toContain("Do not claim a qualification I do not have");
    const parsed = parseStructuredCV(preview);
    expect(parsed?.importedText).toBe(original);
    expect(renderStructuredCV(parsed!)).toBe(preview);
  });

  it("recognizes an already structured CV without duplicating or losing source text", () => {
    const doc = emptyStructuredCV();
    doc.name = "Alex Applicant";
    doc.summary = "SQL evidence, not automatically approved.";
    const originalText = renderStructuredCV(doc);
    const result = structuredFromSource(originalText);
    expect(result.origin).toBe("structured");
    expect(result.model.name).toBe(doc.name);
    expect(result.model.importedText).toBe("");
    expect(renderStructuredCV(result.model)).toBe(originalText);
  });

  it("does not fabricate identity or make empty new CV eligible for save", () => {
    expect(structuredFromSource("").origin).toBe("blank");
    const empty = emptyStructuredCV();
    expect(cvHasApplicantContent(empty)).toBe(false);
    empty.summary = "A real personal summary.";
    expect(cvHasApplicantContent(empty)).toBe(false);
    empty.name = "Synthetic Applicant";
    expect(cvHasApplicantContent(empty)).toBe(true);
  });

  it("rejects malformed structured texts rather than silently dropping lines", () => {
    const doc = emptyStructuredCV();
    doc.name = "Synthetic Applicant";
    doc.summary = "Supported data, not employer verified.";
    const canonical = renderStructuredCV(doc);
    expect(parseStructuredCV(canonical + "\nSECRET EXTRAS")).toBeNull();
    expect(structuredFromSource(canonical + "\nSECRET EXTRAS").origin).toBe("imported");
    expect(parseStructuredCV(canonical.replace("PROFILE", "UNSUPPORTED PROFILE"))).toBeNull();
    expect(parseStructuredCV(canonical.replace("Email: ", "Mail: "))).toBeNull();
  });

  it("omits empty item placeholders from exported text but keeps user-entered facts", () => {
    const doc = emptyStructuredCV();
    doc.name = "Alex Applicant";
    const work = emptyCVSection("projects");
    work.entries.push({
      ...work.entries[0], id: "real-item",
      title: "Personal project", details: "Used Python for QA evidence.",
    });
    doc.sections.push(work);
    const output = renderStructuredCV(doc);
    expect(output.match(/Title: /g)?.length).toBe(1);
    expect(output).toContain("Personal project");
    expect(output).toContain("Used Python");
    expect(parseStructuredCV(output)?.sections[0].entries).toHaveLength(1);
  });
});
