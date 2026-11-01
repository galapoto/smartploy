// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import StartChoices from "./StartChoices";

afterEach(cleanup);

describe("SP89: saved application entry in the CV-first journey", () => {
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


describe("SP101: CV replacement handshake on the first screen", () => {
  it("pauses mode choices and private drafts until the CV update finishes", () => {
    const onMode = vi.fn();
    const onOpenApplications = vi.fn();
    const view = render(<StartChoices cvPresent cvFilename="Earlier CV.pdf"
      onMode={onMode} onBrowse={vi.fn()} onOpenApplications={onOpenApplications}
      onUpload={vi.fn()} onCreateCV={vi.fn()}/>);
    expect(screen.getByText(/Current CV: Earlier CV.pdf/i)).toBeTruthy();
    view.rerender(<StartChoices cvPresent busyCV cvFilename="Earlier CV.pdf"
      onMode={onMode} onBrowse={vi.fn()} onOpenApplications={onOpenApplications}
      onUpload={vi.fn()} onCreateCV={vi.fn()}/>);
    expect(screen.getAllByText(/CV update in progress/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Choose what to do with SmartPloy" })
      .getAttribute("aria-busy")).toBe("true");
    for (const choice of document.querySelectorAll("button.flow-start-card[data-flow-mode]")) {
      expect((choice as HTMLButtonElement).disabled).toBe(true);
      expect(choice.getAttribute("aria-describedby")).toBe("flow-start-cv-updating");
    }
    expect((screen.getByRole("button", { name: /Continue saved drafts/i }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(onMode).not.toHaveBeenCalled();
    expect(onOpenApplications).not.toHaveBeenCalled();

    view.rerender(<StartChoices cvPresent cvFilename="New CV.pdf"
      onMode={onMode} onBrowse={vi.fn()} onOpenApplications={onOpenApplications}/>);
    expect(screen.getByText(/Current CV: New CV.pdf/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Assisted.*Apply with AI/i }));
    expect(onMode).toHaveBeenCalledTimes(1);
    expect(onMode).toHaveBeenCalledWith("assisted");
  });
});
