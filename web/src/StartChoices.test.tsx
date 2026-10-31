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
    fireEvent.click(screen.getByRole("button", { name: /My applications & cover letters/i }));
    expect(onOpenApplications).toHaveBeenCalledOnce();
    expect(onMode).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /^Apply manually/i })).toBeNull();
  });

  it("keeps the application shortcut visible for a connected CV", () => {
    const onOpenApplications = vi.fn();
    render(<StartChoices cvPresent onMode={vi.fn()}
      onBrowse={vi.fn()} onOpenApplications={onOpenApplications} />);
    fireEvent.click(screen.getByRole("button", { name: /My applications & cover letters/i }));
    expect(onOpenApplications).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /^Apply manually/i })).toBeTruthy();
  });

  it("does not advertise an unwired shortcut", () => {
    render(<StartChoices cvPresent={false} onMode={vi.fn()} onBrowse={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /My applications & cover letters/i })).toBeNull();
  });
});
