// @vitest-environment jsdom
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import AutoShortlistPanel from "./AutoShortlistPanel";

vi.mock("./api",()=>({
  getSession:vi.fn(),getLocalShortlistSettings:vi.fn(),
  saveLocalShortlistSettings:vi.fn(),runLocalShortlistNow:vi.fn()
}));

const baseline:api.LocalShortlistSettings={
  enabled:false,minimum_score:75,max_per_cycle:3,
  revision:0,last_run_at:"",last_status:"not_run",
  last_created:0,last_inspected:0,
  review_required:true,automatic_employer_submission:false,
  external_ai_processing:false,background_worker_enabled:false
};
beforeEach(()=>{
  vi.resetAllMocks();
  vi.mocked(api.getSession).mockResolvedValue({
    authenticated:true,user_id:"usr-one",profile_id:"profile-one",
    email:"same@example.invalid",auth_source:"oidc"
  });
  vi.mocked(api.getLocalShortlistSettings).mockResolvedValue({...baseline});
  vi.mocked(api.saveLocalShortlistSettings).mockResolvedValue({
    ...baseline,enabled:true,revision:1
  });
  vi.mocked(api.runLocalShortlistNow).mockResolvedValue({
    status:"ready",created:2,inspected:4,
    employer_submissions:0,external_ai_processing:false,
    external_actions_authorized:false,review_required:true
  });
});
afterEach(()=>cleanup());

describe("real opt-in automatic IT job shortlist panel",()=>{
  it("does not enable automation without explicit signed-in consent",async()=>{
    render(<AutoShortlistPanel expectedUserId="usr-one" personalized/>);
    const button=await screen.findByRole("button",{name:"Enable automatic IT-job drafts"});
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(api.saveLocalShortlistSettings).not.toHaveBeenCalled();
    expect(screen.getByText(/No employer applications are sent/i)).toBeTruthy();
    expect(api.runLocalShortlistNow).not.toHaveBeenCalled();
  });

  it("enabling drafts runs immediately with same-owner checks, never sends employer forms",async()=>{
    const prepared=vi.fn();
    render(<AutoShortlistPanel expectedUserId="usr-one" personalized onPrepared={prepared}/>);
    const button=await screen.findByRole("button",{name:"Enable automatic IT-job drafts"});
    const consent=screen.getByRole("checkbox",{
      name:/I authorize automatic LOCAL drafts/
    });
    fireEvent.click(consent);
    fireEvent.click(button);
    await waitFor(()=>expect(api.saveLocalShortlistSettings).toHaveBeenCalledWith({
      enabled:true,minimum_score:75,max_per_cycle:3,
      expected_revision:0,acknowledge_local_drafts_only:true
    },"usr-one"));
    await waitFor(()=>expect(api.runLocalShortlistNow).toHaveBeenCalledWith("usr-one"));
    expect(await screen.findByText(/2 new application drafts prepared for your review/)).toBeTruthy();
    expect(prepared).toHaveBeenCalledTimes(1);
    expect(api.runLocalShortlistNow).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/No employer applications are sent/)).toBeTruthy();
  });

  it("general search cannot opt into personalized background matching",async()=>{
    render(<AutoShortlistPanel expectedUserId="usr-one" personalized={false}/>);
    const button=await screen.findByRole("button",{name:"Enable automatic IT-job drafts"});
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Switch to personalized job search/)).toBeTruthy();
    expect(api.saveLocalShortlistSettings).not.toHaveBeenCalled();
  });

  it("same-email account switch fails closed BEFORE any consent mutation",async()=>{
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated:true,user_id:"usr-another",profile_id:"profile-another",
      email:"same@example.invalid",auth_source:"oidc"
    });
    render(<AutoShortlistPanel expectedUserId="usr-one" personalized/>);
    expect(await screen.findByText(/signed-in account changed/)).toBeTruthy();
    expect(api.saveLocalShortlistSettings).not.toHaveBeenCalled();
    expect(api.runLocalShortlistNow).not.toHaveBeenCalled();
  });

  it("turning off existing account stops future draft creation",async()=>{
    vi.mocked(api.getLocalShortlistSettings).mockResolvedValue({
      ...baseline,enabled:true,revision:4,background_worker_enabled:true
    });
    vi.mocked(api.saveLocalShortlistSettings).mockResolvedValue({
      ...baseline,enabled:false,revision:5
    });
    render(<AutoShortlistPanel expectedUserId="usr-one" personalized/>);
    const disable=await screen.findByRole("button",{name:"Disable automatic drafts"});
    fireEvent.click(disable);
    await waitFor(()=>expect(api.saveLocalShortlistSettings).toHaveBeenCalledWith({
      enabled:false,minimum_score:75,max_per_cycle:3,
      expected_revision:4,acknowledge_local_drafts_only:false
    },"usr-one"));
    expect(api.runLocalShortlistNow).not.toHaveBeenCalled();
  });
});
