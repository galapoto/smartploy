// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import StartChoices from "./StartChoices";

afterEach(cleanup);

describe("SP89: saved application entry in the CV-first journey", () => {
  it("keeps concise mobile labels and explicit applicant/ATS boundaries", () => {
    render(<StartChoices cvPresent onMode={vi.fn()} onBrowse={vi.fn()} />);
    expect(screen.getByText("Open a matching job and complete its application yourself.")).toBeTruthy();
    expect(screen.getByText("Prepare a CV and letter. Review before filling supported forms.")).toBeTruthy();
    expect(screen.getByText("Prepare matched jobs. Employer actions require explicit authorization.")).toBeTruthy();
    expect(screen.getByText(/Selecting a mode never authorizes sending an application/)).toBeTruthy();
    expect(screen.getByText(/Employer submissions require applicant review and explicit authorization/)).toBeTruthy();
    expect(screen.getAllByRole("button").filter((b) => b.getAttribute("data-flow-mode"))).toHaveLength(3);
  });


  it("opens saved applications from the first-use CV screen without picking a mode", () => {
    const onOpenApplications = vi.fn();
    const onMode = vi.fn();
    render(<StartChoices cvPresent={false} onMode={onMode}
      onBrowse={vi.fn()} onOpenApplications={onOpenApplications} />);
    fireEvent.click(screen.getByRole("button", { name: /Continue saved drafts & letters/i }));
    expect(onOpenApplications).toHaveBeenCalledOnce();
    expect(onMode).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: /^Apply manually/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps the application shortcut visible for a connected CV", () => {
    const onOpenApplications = vi.fn();
    render(<StartChoices cvPresent onMode={vi.fn()}
      onBrowse={vi.fn()} onOpenApplications={onOpenApplications} />);
    fireEvent.click(screen.getByRole("button", { name: /Continue saved drafts & letters/i }));
    expect(onOpenApplications).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /^Apply manually/i })).toBeTruthy();
  });

  it("does not advertise an unwired shortcut", () => {
    render(<StartChoices cvPresent={false} onMode={vi.fn()} onBrowse={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Continue saved drafts & letters/i })).toBeNull();
  });
});

describe("V4 clarity: one visible task, real actions, and accessible disclosure hierarchy",()=>{
  it("uses a clear step heading and keeps all three original application choices operational",()=>{
    const onMode=vi.fn();
    render(<StartChoices cvPresent onMode={onMode}
      onBrowse={vi.fn()} onOpenApplications={vi.fn()} />);
    expect(screen.getByRole("heading",{name:"CV connected. Choose how to apply.",level:2})).toBeTruthy();
    expect(screen.getByRole("heading",{name:"How would you like to apply?",level:3})).toBeTruthy();
    const assisted=screen.getByRole("button",{name:/Assisted · Apply with AI/i});
    expect(assisted.getAttribute("data-featured")).toBe("guided");
    fireEvent.click(assisted);
    expect(onMode).toHaveBeenCalledOnce();
    expect(onMode).toHaveBeenCalledWith("assisted");
    expect(screen.getByRole("button",{name:/Just find jobs/i})).toBeTruthy();
    expect(screen.getByText(/Employer submissions require applicant review and explicit authorization/)).toBeTruthy();
  });
  it("never turns a missing CV into enabled application or employer submission",()=>{
    const onMode=vi.fn();
    render(<StartChoices cvPresent={false} onMode={onMode}
      onBrowse={vi.fn()} onUpload={vi.fn()} onCreateCV={vi.fn()}/>);
    expect(screen.getByRole("heading",{name:"Start with your CV.",level:2})).toBeTruthy();
    for(const mode of ["manual","assisted","automatic"]){
      const el=document.querySelector<HTMLButtonElement>(
        '.flow-start-card[data-flow-mode="'+mode+'"]');
      expect(el?.disabled).toBe(true);
      if(el)fireEvent.click(el);
    }
    expect(onMode).not.toHaveBeenCalled();
  });
});
