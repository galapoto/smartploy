// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";

import * as api from "./api";
import AutoDraftPanel from "./AutoDraftPanel";

vi.mock("./api",()=>({
  getSession:vi.fn(), getAutoDraftSettings:vi.fn(),
  saveAutoDraftSettings:vi.fn(), scanAutoDrafts:vi.fn(),
}));

const disabled={
  enabled:false,minimum_score:75,max_per_cycle:5,revision:0,
  draft_only:true as const,
  automatic_employer_submission_authorized:false as const,
  external_ai_processing_authorized:false as const,
};
beforeEach(()=>{
  vi.resetAllMocks();
  vi.mocked(api.getSession).mockResolvedValue({
    authenticated:true,user_id:"usr-synthetic",profile_id:"profile-synthetic",
    auth_source:"oidc",
  });
  vi.mocked(api.getAutoDraftSettings).mockResolvedValue(disabled);
  vi.mocked(api.saveAutoDraftSettings).mockResolvedValue({
    ...disabled, enabled:true, revision:1,
  });
  vi.mocked(api.scanAutoDrafts).mockResolvedValue({
    status:"ready",created_count:1,existing_count:0,skipped_count:0,
    created:[{workspace_id:"kit-synthetic",canonical_key:"data-job",
      preference_score:95,reasons:["Job title matches Data Analyst"]}],
    external_actions_performed:false,external_ai_calls:0,
    employer_applications_submitted:0,
    requires_individual_review_before_application:true,
  });
});
afterEach(()=>cleanup());

function view(personalized=true,authSource="oidc") {
  const onReview=vi.fn();
  render(<AutoDraftPanel expectedUserId="usr-synthetic" authSource={authSource}
    personalized={personalized} onReview={onReview}/>);
  return onReview;
}

describe("automatic IT matching before any employer submission",()=>{
  it("opts in per owner, scans at once and offers review without sending",async()=>{
    const onReview=view();
    const button=await screen.findByRole("button",{name:"Enable and find IT matches now"});
    fireEvent.click(button);
    await waitFor(()=>expect(api.saveAutoDraftSettings).toHaveBeenCalledWith({
      enabled:true,minimum_score:75,max_per_cycle:5,revision:0,
    },"usr-synthetic"));
    await waitFor(()=>expect(api.scanAutoDrafts).toHaveBeenCalledWith("usr-synthetic"));
    expect(await screen.findByText(/1 new matching application draft/)).toBeTruthy();
    expect(screen.getByText(/No employer was contacted/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:"Review prepared applications"}));
    expect(onReview).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button",{name:/submit to employer/i})).toBeNull();
  });

  it("pauses a prior optin and does not start a new scan",async()=>{
    vi.mocked(api.getAutoDraftSettings).mockResolvedValue({...disabled,enabled:true,revision:2});
    vi.mocked(api.saveAutoDraftSettings).mockResolvedValue({
      ...disabled,enabled:false,revision:3,
    });
    view();
    fireEvent.click(await screen.findByRole("button",{name:"Pause automatic drafting"}));
    await waitFor(()=>expect(api.saveAutoDraftSettings).toHaveBeenCalledWith({
      enabled:false,minimum_score:75,max_per_cycle:5,revision:2,
    },"usr-synthetic"));
    expect(api.scanAutoDrafts).not.toHaveBeenCalled();
  });

  it("never enables private automatic matching for general mode or Access-only sessions",async()=>{
    view(false);
    expect(await screen.findByText(/Set your target IT job titles/)).toBeTruthy();
    cleanup();
    view(true,"cloudflare_access");
    expect(screen.getByText(/First-party SmartPloy sign-in is required/)).toBeTruthy();
    expect(api.saveAutoDraftSettings).not.toHaveBeenCalled();
  });

  it("fails closed when the verified account switches before opting in",async()=>{
    vi.mocked(api.getSession).mockResolvedValueOnce({
      authenticated:true,user_id:"usr-synthetic",auth_source:"oidc",
    }).mockResolvedValueOnce({
      authenticated:true,user_id:"usr-synthetic",auth_source:"oidc",
    }).mockResolvedValue({
      authenticated:true,user_id:"usr-other",auth_source:"oidc",
    });
    view();
    fireEvent.click(await screen.findByRole("button",{name:"Enable and find IT matches now"}));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/account changed/i);
    expect(api.saveAutoDraftSettings).not.toHaveBeenCalled();
  });
});
