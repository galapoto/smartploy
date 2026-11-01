// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import DocumentCoach from "./DocumentCoach";
import { reviewDocument } from "./documentQuality";

afterEach(cleanup);

const cv = [
  "Test Applicant",
  "applicant@example.invalid",
  "",
  "PROFILE",
  "Data professional with experience in software quality assurance and analytics.",
  "",
  "EXPERIENCE AND PROJECTS",
  "Delivered three reviewed reporting projects for a training portfolio.",
  "Automated quality checks across 12 projects with clear audit notes.",
  "",
  "SKILLS",
  "Python, SQL, Power BI",
  "",
  "EDUCATION",
  "Bachelor degree and relevant training",
].join("\n");

const letter = [
  "Dear Hiring Manager,",
  "",
  "I am applying for the Junior Data Analyst role at Example Oy. " +
  "I have practical training in analytics and I would like to contribute to data reporting. " +
  "The role's emphasis on reliable business information is important to me.",
  "",
  "My portfolio includes a training project that involved verified SQL queries " +
  "and careful review of analytical results. I am particularly interested in " +
  "documenting work clearly, learning from feedback and collaborating with a team.",
  "",
  "Thank you for considering my application. " +
  "I would welcome an opportunity to discuss my experience.",
  "",
  "Kind regards,",
  "Test Applicant",
].join("\n");

describe("SP96 private live document quality checks", () => {
  it("reviews a master CV with factual section prompts and never claims fact verification", () => {
    const result = reviewDocument({kind: "master_cv", text: cv});
    expect(result.passed).toBe(result.total);
    expect(result.checks.every((item) => item.passed)).toBe(true);
    expect(result.summary).toMatch(/verify every claim/i);
  });

  it("spots unfinished placeholders without replacing or inventing applicant facts", () => {
    const source = "PROFILE\n[Name]\nTODO\n" + cv;
    const result = reviewDocument({kind: "job_cv", text: source});
    const placeholders = result.checks.find((row) => row.id === "cv-placeholders");
    expect(placeholders?.passed).toBe(false);
    expect(result.checks.some((row) => row.id === "cv-evidence" && row.passed)).toBe(true);
    expect(source).toContain("[Name]");
  });

  it("checks the exact job and employer independently of the letter's length", () => {
    const result = reviewDocument({
      kind: "cover_letter", text: letter,
      roleTitle: "Junior Data Analyst", company: "Example Oy",
    });
    expect(result.passed).toBe(result.total);
    const wrong = reviewDocument({
      kind: "cover_letter", text: letter,
      roleTitle: "Senior Driver", company: "Different Employer",
    });
    expect(wrong.checks.find((row) => row.id === "letter-job")?.passed).toBe(false);
    expect(wrong.checks.find((row) => row.id === "letter-company")?.passed).toBe(false);
  });

  it("renders live human-review guidance without sending user text anywhere", () => {
    const view = render(<DocumentCoach kind="cover_letter"
      text="Dear Sir or Madam,\n[Company]\nTBD" roleTitle="Data Engineer" company="Example Oy" />);
    expect(screen.getByRole("complementary", {
      name: "Cover letter live writing review",
    })).toBeTruthy();
    expect(screen.getByText("Correct employer")).toBeTruthy();
    expect(screen.getByText(/runs in your browser without sending document text/i)).toBeTruthy();
    view.rerender(<DocumentCoach kind="cover_letter" text={letter}
      roleTitle="Junior Data Analyst" company="Example Oy" />);
    expect(screen.getByText("7 / 7 checks")).toBeTruthy();
  });
});
