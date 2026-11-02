// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://smartploy.komplyint.fi/"}
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  deleteApplicationQuestion, getApplicationQuestionMemory, getSession,
  saveApplicationQuestionAnswer, setApplicationProfileMode, suggestProfileFactsFromCV,
} from "./api";
import ApplicationProfilePanel, {applicantProfileReadiness} from "./ApplicationProfilePanel";
import type { ApplicationProfileQuestion, CandidateFact } from "./types";

vi.mock("./api", () => ({
  deleteApplicationQuestion: vi.fn(), getApplicationQuestionMemory: vi.fn(),
  getSession: vi.fn(), saveApplicationQuestionAnswer: vi.fn(),
  setApplicationProfileMode: vi.fn(),
  suggestProfileFactsFromCV: vi.fn(),
}));

const key = "c".repeat(64);
const saved: ApplicationProfileQuestion = {
  question_key:key, label:"Describe a project you led",
  answer:"", approved_for_reuse:false, reusable_scope:"exact_question",
  version:1, first_seen_at:"2026-11-02T15:00:00Z",
  updated_at:"2026-11-02T15:00:00Z",
};
const facts: CandidateFact[] = [
  {fact_id:"f1", fact_type:"identity", value:"Synthetic Applicant",
   approved:true, source:"user-confirmed",confidence:1,created_at:""},
  {fact_id:"f2", fact_type:"skill", value:"Python",
   approved:true, source:"user-confirmed",confidence:1,created_at:""},
  {fact_id:"f3", fact_type:"email", value:"unapproved@example.invalid",
   approved:false, source:"user-entered",confidence:1,created_at:""},
];

const instance = () => render(<ApplicationProfilePanel expectedUserId="user-A"
  facts={facts} cvPresent={true} />);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getSession).mockResolvedValue({
    authenticated:true, user_id:"user-A", profile_id:"profile-A",
    auth_source:"oidc", email:"same@example.invalid",
  });
  vi.mocked(getApplicationQuestionMemory).mockResolvedValue({
    questions:[saved],count:1,mode:"guided",cv_only_allowed:true,
    approved_answers_auto_submitted:false,employer_actions_performed:0,
  });
  vi.mocked(setApplicationProfileMode).mockImplementation(async mode => ({
    mode,cv_only_allowed:true,employer_actions_performed:0,
  }));
  vi.mocked(saveApplicationQuestionAnswer).mockResolvedValue({
    question:{...saved,answer:"Led a real data-quality project",
      version:2,approved_for_reuse:true},
    employer_actions_performed:0,
    automatic_employer_submission_authorized:false,
  });
  vi.mocked(suggestProfileFactsFromCV).mockResolvedValue({
    created:3,already_known:1,suggestions_are_approved:false,
    external_ai_forwarding:false,employer_actions_performed:0,
  });
  vi.mocked(deleteApplicationQuestion).mockResolvedValue({
    deleted:true,employer_actions_performed:0,
  });
  vi.stubGlobal("confirm",vi.fn(() => true));
});
afterEach(() => { cleanup();vi.unstubAllGlobals(); });

describe("SP116 guided complete profile / optional CV-only", () => {
  it("counts only reviewed facts and never conflates them with a CV", () => {
    const result = applicantProfileReadiness(facts);
    expect(result.reviewed).toBe(2);
    expect(result.total).toBeGreaterThan(15);
    expect(result.missing).toContain("Contact email");
    expect(result.missing).toContain("Salary preference (manual only)");
  });
  it("keeps CV-only path available with an honest reduced-assistance warning",async () => {
    instance();
    expect(await screen.findByRole("button", {name:/Use CV only/})).toBeTruthy();
    expect(screen.getByText(/Without approved contact and career details/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {name:/Use CV only/}));
    await waitFor(() => expect(setApplicationProfileMode).toHaveBeenCalledWith("cv_only","user-A"));
    expect(await screen.findByText(/CV-only mode is active/)).toBeTruthy();
    expect(screen.getByText(/No new employer questions will be stored/)).toBeTruthy();
    expect(getApplicationQuestionMemory).toHaveBeenCalledTimes(1);
  });
  it("remembers an eligible answer only after affirmative applicant confirmation",async () => {
    instance();
    const answer = await screen.findByLabelText("Describe a project you led");
    fireEvent.change(answer,{target:{value:"Led a real data-quality project"}});
    fireEvent.click(screen.getByRole("button",{name:"Save reviewed answer"}));
    await waitFor(() => expect(saveApplicationQuestionAnswer).toHaveBeenCalledWith(
      key,1,"Led a real data-quality project",true,"user-A",
    ));
    expect(window.confirm).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Answer saved in your private profile/)).toBeTruthy();
    expect(screen.getByText(/suggest on exact matching questions/)).toBeTruthy();
  });
  it("SP116 saved CV facts remain unapproved until applicant reviews", async () => {
    const onFactsSuggested = vi.fn();
    render(<ApplicationProfilePanel expectedUserId="user-A"
      facts={facts} cvPresent={true} cvVerified
      onFactsSuggested={onFactsSuggested} />);
    const button = await screen.findByRole("button", {
      name: "Find reviewable facts in my CV",
    });
    fireEvent.click(button);
    await waitFor(() => expect(suggestProfileFactsFromCV).toHaveBeenCalledWith("user-A"));
    expect(onFactsSuggested).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/unapproved contact\/skill suggestion/)).toBeTruthy();
    expect(window.confirm).toHaveBeenCalledTimes(1);
  });

  it("lets each applicant remove remembered questions", async () => {
    instance();
    await screen.findByRole("button", {name:"Remove question"});
    fireEvent.click(screen.getByRole("button", {name:"Remove question"}));
    await waitFor(() => expect(deleteApplicationQuestion).toHaveBeenCalledWith(key,"user-A"));
    expect(screen.queryByText("Describe a project you led")).toBeNull();
  });
  it("cannot publish previous account's preferences after OIDC switch",async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated:true,user_id:"user-B",profile_id:"profile-B",
      auth_source:"oidc",email:"same@example.invalid",
    });
    instance();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(setApplicationProfileMode).not.toHaveBeenCalled();
    expect(saveApplicationQuestionAnswer).not.toHaveBeenCalled();
    expect(deleteApplicationQuestion).not.toHaveBeenCalled();
  });
  it("never changes profile preference when explicit CV-only confirmation is declined",async () => {
    vi.stubGlobal("confirm",vi.fn(() => false));
    instance();
    const button = await screen.findByRole("button",{name:/Use CV only/});
    fireEvent.click(button);
    expect(setApplicationProfileMode).not.toHaveBeenCalled();
  });
});
