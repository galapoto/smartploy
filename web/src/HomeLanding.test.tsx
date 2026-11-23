// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import HomeLanding from "./HomeLanding";

afterEach(cleanup);
function setup(cvPresent:boolean) {
  const actions={
    onMode:vi.fn(), onBrowse:vi.fn(), onUpload:vi.fn(),
    onCreateCV:vi.fn(), onOpenApplications:vi.fn()
  };
  render(<HomeLanding cvPresent={cvPresent} {...actions}/>);
  return actions;
}
describe("V4 distill: one real primary action, no fake employer send",()=>{
  it("shows exactly the CV action first, with no employer mode before a CV",()=>{
    const a=setup(false);
    expect(screen.getByRole("heading",{name:"Apply with confidence",level:1})).toBeTruthy();
    expect(screen.getByRole("heading",{name:"Start with your CV.",level:2})).toBeTruthy();
    expect(document.querySelectorAll(".flow-start-card")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:/Upload your CV/i}));
    expect(a.onUpload).toHaveBeenCalledOnce();
    expect(a.onMode).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button",{name:/Find jobs/i}));
    expect(a.onBrowse).toHaveBeenCalledOnce();
    expect(a.onOpenApplications).not.toHaveBeenCalled();
    expect(screen.getByText(/Nothing is sent to an employer without your approval/)).toBeTruthy();
  });
  it("makes application-mode choices visible only after the user elects to apply",()=>{
    const a=setup(true);
    expect(screen.getByRole("button",{name:/Choose how to apply/i})).toBeTruthy();
    expect(document.querySelectorAll(".flow-start-card")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:/Choose how to apply/i}));
    expect(document.querySelectorAll(".flow-start-card")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button",{name:/Assisted · Apply with AI/i}));
    expect(a.onMode).toHaveBeenCalledOnce();
    expect(a.onMode).toHaveBeenCalledWith("assisted");
    fireEvent.click(screen.getByRole("button",{name:/Back/i}));
    expect(document.querySelectorAll(".flow-start-card")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:/My applications/i}));
    expect(a.onOpenApplications).toHaveBeenCalledOnce();
  });
});
