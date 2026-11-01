// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import DocumentComparison from "./DocumentComparison";

afterEach(cleanup);

describe("SP97 private document proposal comparison", () => {
  it("shows the exact current and proposed letter as read-only, without any save or submit action", () => {
    const { rerender } = render(<DocumentComparison
      title="Compare original and proposed cover letters"
      current={"My own unsaved sentence.\n\nWith a second paragraph."}
      proposed={"Dear Hiring Team,\n\nEvidence-backed letter draft.\n\nKind regards,"}
      source="approved_evidence"
    />);
    const section = screen.getByRole("region", {
      name: "Compare original and proposed cover letters",
    });
    expect(section.textContent).toContain("My own unsaved sentence.");
    expect(section.textContent).toContain("Evidence-backed letter draft.");
    expect(section.textContent).toContain("Your original wording remains unchanged");
    expect(screen.queryByRole("button", { name: /Submit|Save/ })).toBeNull();
    rerender(<DocumentComparison title="Compare original and proposed cover letters"
      current="New manual wording" proposed="A different AI suggestion"
      source="private_ai" />);
    expect(section.textContent).toContain("New manual wording");
    expect(section.textContent).toContain("A different AI suggestion");
    expect(section.textContent).toContain("unverified");
  });
});


describe("SP105 applicant-owned master CV provenance comparison", () => {
  it("shows master CV provenance without treating the comparison as an employer action", () => {
    render(<DocumentComparison title="Job-specific CV versus current master CV"
      current="Job-specific CV text" proposed="Current full master CV text" source="master_cv"/>);
    const section = screen.getByRole("region", { name: "Job-specific CV versus current master CV" });
    expect(section.textContent).toContain("Current owner-private master CV");
    expect(section.textContent).toContain("Current master CV text");
    expect(section.textContent).toContain("does not save a document");
    expect(screen.queryByRole("button", { name: /send|submit/i })).toBeNull();
  });
});
