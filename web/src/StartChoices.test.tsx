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
    expect(screen.getByText(/Choosing a method never sends anything/)).toBeTruthy();
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
