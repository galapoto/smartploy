// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import SearchSetup from "./SearchSetup";
import type { SearchPreferences, SearchPreferencesUpdate } from "./types";

const firstVisit: SearchPreferences = {
  completed: false, mode: "personalized", roles: [], locations: [],
  languages: [], work_modes: [], keywords: [], skills: [],
  seniority: "any", revision: 0, updated_at: "", verified_qualification_fit: false,
};

afterEach(() => cleanup());

describe("first-use choice and saved settings", () => {
  it("lets a new user browse generally without submitting a CV or criteria", async () => {
    const save = vi.fn(async (_value: SearchPreferencesUpdate) => undefined);
    render(<SearchSetup initial={firstVisit} onSave={save} />);

    expect(screen.getByRole("heading", { name: "Find work that fits your goals." })).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    expect(screen.getByText(/no profile, CV, or search preferences required/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /browse all jobs/i }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({
      mode: "general", roles: [], keywords: [], skills: [], expected_revision: 0,
    });
  });

  it("preserves the user's General choice during same-revision parent refreshes", async () => {
    const save = vi.fn(async (_value: SearchPreferencesUpdate) => undefined);
    const { rerender } = render(<SearchSetup initial={firstVisit} onSave={save} />);

    fireEvent.click(screen.getByRole("radio", { name: /general job search/i }));
    expect((screen.getByRole("radio", { name: /general job search/i }) as HTMLInputElement).checked).toBe(true);

    // The parent may reconstruct a stale server snapshot while optional
    // requests finish. A same-revision render must not discard the local mode.
    rerender(<SearchSetup initial={{
      ...firstVisit, roles: ["stale role from parent"], revision: 0,
    }} onSave={save} />);
    expect((screen.getByRole("radio", { name: /general job search/i }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /browse all jobs/i }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      mode: "general", expected_revision: 0,
    }));

    // A genuinely newer saved revision *must* rehydrate Settings correctly.
    rerender(<SearchSetup initial={{
      ...firstVisit, completed: true, revision: 1, mode: "personalized",
      roles: ["Data Analyst"],
    }} onSave={save} />);
    await waitFor(() => expect(
      (screen.getByRole("radio", { name: /personalized jobs/i }) as HTMLInputElement).checked
    ).toBe(true));
    expect((screen.getByPlaceholderText(/Data analyst, Junior software tester/) as HTMLTextAreaElement).value)
      .toBe("Data Analyst");
  });

  it("requires a target role or keyword for personalized results, not private CV evidence", async () => {
    const save = vi.fn(async (_value: SearchPreferencesUpdate) => undefined);
    render(<SearchSetup initial={firstVisit} onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: /show my matched jobs/i }));
    expect(screen.getByRole("alert").textContent).toMatch(/at least one job title or search keyword/i);
    expect(save).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText(/Data analyst, Junior software tester/), {
      target: { value: "Data analyst, Document controller" },
    });
    fireEvent.change(screen.getByPlaceholderText(/SQL, Python, nursing/), {
      target: { value: "Python, SQL" },
    });
    fireEvent.click(screen.getByRole("button", { name: /show my matched jobs/i }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({
      mode: "personalized",
      roles: ["Data analyst", "Document controller"],
      skills: ["Python", "SQL"],
      expected_revision: 0,
    });
  });

  it("keeps automatic IT drafts OFF by default, requires opt-in and revokes in general mode", async () => {
    const save = vi.fn(async (_value: SearchPreferencesUpdate) => undefined);
    render(<SearchSetup initial={firstVisit} onSave={save}/>);
    fireEvent.click(screen.getByRole("button",{name:"Use IT job starter targets"}));
    const box=screen.getByRole("checkbox",{
      name:/Automatically prepare suitable job drafts/
    }) as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    expect(box.checked).toBe(true);
    fireEvent.click(screen.getByRole("button",{name:/Show my matched jobs/}));
    await waitFor(()=>expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({
      mode:"personalized",auto_draft_enabled:true,
      roles:["Data Analyst","Junior Software Tester","Junior Business Analyst",
             "IT Support Specialist","Junior Python Developer"],
      locations:["Helsinki","Espoo","Vantaa"],seniority:"entry",
    });
    fireEvent.click(screen.getByRole("radio",{name:/general job search/i}));
    fireEvent.click(screen.getByRole("button",{name:/Browse all jobs/}));
    await waitFor(()=>expect(save).toHaveBeenCalledTimes(2));
    expect(save.mock.calls[1][0].auto_draft_enabled).toBe(false);
  });

  it("preserves previously configured targets when switching modes and allows edits", async () => {
    const save = vi.fn(async (_value: SearchPreferencesUpdate) => undefined);
    render(<SearchSetup settings onSave={save} initial={{
      ...firstVisit, completed: true, mode: "general",
      roles: ["Software tester"], keywords: ["QA"],
      revision: 4,
    }} />);
    fireEvent.click(screen.getByRole("radio", { name: /personalized jobs/i }));
    expect((screen.getByPlaceholderText(/Data analyst, Junior software tester/) as HTMLTextAreaElement).value)
      .toBe("Software tester");
    fireEvent.click(screen.getByRole("button", { name: /save search preferences/i }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({
      mode: "personalized", roles: ["Software tester"],
      keywords: ["QA"], expected_revision: 4,
    });
  });
});
