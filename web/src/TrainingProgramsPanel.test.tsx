// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import * as api from "./api";
import TrainingProgramsPanel from "./TrainingProgramsPanel";
import type { TrainingProgramsResponse } from "./types";

vi.mock("./api", () => ({ getTrainingPrograms: vi.fn() }));

const programmes: TrainingProgramsResponse = {
  count: 3, opening_status: "check_provider",
  job_count_included: 0, external_actions_authorized: false,
  programs: [
    {
      id: "saranen", provider: "Saranen", title: "RekryKoulutus IT",
      kind: "recruitment_training", region: "Across Finland",
      url: "https://www.saranen.fi/aikuiskoulutus",
      focus: ["IT", "Data"], eligibility_note: "Check employment-services eligibility.",
      opening_status: "check_provider", listing_type: "directory_link",
      counts_as_live_job: false, automatic_application_authorized: false,
    },
    {
      id: "siemens", provider: "Siemens", title: "Software student programme",
      kind: "employer_trainee", region: "Finland",
      url: "https://www.siemens.com/fi-fi",
      focus: ["Software", "Engineering"], eligibility_note: "Check the country and vacancies.",
      opening_status: "check_provider", listing_type: "directory_link",
      counts_as_live_job: false, automatic_application_authorized: false,
    },
    {
      id: "nokia", provider: "Nokia", title: "Early careers",
      kind: "employer_trainee", region: "Espoo",
      url: "https://www.nokia.com/careers",
      focus: ["Data"], eligibility_note: "Check the currently open roles.",
      opening_status: "check_provider", listing_type: "directory_link",
      counts_as_live_job: false, automatic_application_authorized: false,
    },
  ],
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("training and trainee programmes directory", () => {
  it("shows official programme destinations without misleading job or application claims", async () => {
    vi.mocked(api.getTrainingPrograms).mockResolvedValue(programmes);
    render(<TrainingProgramsPanel />);
    expect(await screen.findByText("RekryKoulutus IT")).toBeTruthy();
    expect(screen.getByText("Software student programme")).toBeTruthy();
    expect(screen.getByText(/not confirmed open applications/i)).toBeTruthy();
    expect(screen.getByText(/not current vacancy counts/i)).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /open provider website/i })).toHaveLength(3);
    for (const link of screen.getAllByRole("link", { name: /open provider website/i })) {
      expect(link.getAttribute("rel")).toContain("noopener");
      expect(link.getAttribute("target")).toBe("_blank");
    }
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
  });

  it("filters actual programme providers by category and keyword without profile access", async () => {
    vi.mocked(api.getTrainingPrograms).mockResolvedValue(programmes);
    render(<TrainingProgramsPanel />);
    await screen.findByText("RekryKoulutus IT");
    fireEvent.change(screen.getByRole("combobox", { name: /training programme category/i }), {
      target: { value: "employer_trainee" },
    });
    expect(screen.queryByText("RekryKoulutus IT")).toBeNull();
    expect(screen.getByText("Software student programme")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: /find trainee programme provider/i }), {
      target: { value: "Nokia" },
    });
    expect(screen.getByText("Early careers")).toBeTruthy();
    expect(screen.queryByText("Software student programme")).toBeNull();
  });

  it("fails explicitly if source catalogue cannot be loaded", async () => {
    vi.mocked(api.getTrainingPrograms).mockRejectedValue(new Error("unavailable"));
    render(<TrainingProgramsPanel />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText(/directories are unavailable/i)).toBeTruthy();
  });
});
