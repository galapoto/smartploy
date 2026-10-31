// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import StartChoices from "./StartChoices";

afterEach(cleanup);

describe("SP91 SmartPloy Career Atlas entrypoint", () => {
  it("distinguishes Manual, Assisted and Automatic without changing their permissions", () => {
    const onMode = vi.fn();
    render(<StartChoices cvPresent onMode={onMode} onBrowse={vi.fn()} />);
    expect(screen.getByText("SMARTPLOY / APPLICATION WORKSPACE")).toBeTruthy();
    const modes = ["manual", "assisted", "automatic"];
    for (const mode of modes) {
      const button = document.querySelector(`button.flow-start-card[data-flow-mode="${mode}"]`);
      expect(button).toBeTruthy();
      expect((button as HTMLButtonElement).type).toBe("button");
    }
    expect(document.querySelectorAll(".flow-start-grid-methods .flow-start-card")).toHaveLength(3);
    expect(screen.getByText(/Selecting a mode never authorizes sending an application/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Assisted/ }));
    expect(onMode).toHaveBeenCalledWith("assisted");
    expect(onMode).toHaveBeenCalledTimes(1);
  });

  it("keeps all three application methods unavailable until a CV exists", () => {
    const onMode = vi.fn(), onBrowse = vi.fn(), onUpload = vi.fn();
    render(<StartChoices cvPresent={false} onMode={onMode}
      onBrowse={onBrowse} onUpload={onUpload} />);
    expect(document.querySelectorAll(".flow-start-grid-methods .flow-start-card")).toHaveLength(3);
    for (const mode of ["manual", "assisted", "automatic"]) {
      const card = document.querySelector(`button.flow-start-card[data-flow-mode="${mode}"]`);
      expect(card).toBeTruthy();
      expect((card as HTMLButtonElement).disabled).toBe(true);
    }
    expect(screen.getByText(/The three application paths are shown below/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Upload CV first/ }));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onMode).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Just find jobs/ }));
    expect(onBrowse).toHaveBeenCalledTimes(1);
    expect(onMode).not.toHaveBeenCalled();
  });
});
