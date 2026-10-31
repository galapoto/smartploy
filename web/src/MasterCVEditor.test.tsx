// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as api from "./api";
import MasterCVEditor from "./MasterCVEditor";
import type { CVDocument, CVEditorDocument, CVEditorSaved } from "./types";

vi.mock("./api", () => ({
  getCVEditor: vi.fn(),
  getSession: vi.fn(),
}));

const USER = "usr-synthetic-a";
const HASH = "a".repeat(64);
const NEXT = "b".repeat(64);
const original = "Synthetic Candidate\nEXPERIENCE\nPython and SQL verified projects.";
const active: CVDocument = {
  present: true, filename: "original.docx", sha256: HASH,
  media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size_bytes: 1024, text_extracted: true,
};
const response: CVEditorDocument = {
  present: true, sha256: HASH, text: original,
  filename: "original.docx", created_by_editor: false,
  employer_actions_performed: 0, approved_profile_facts_added: 0,
  history: [],
};

const savedResponse = (text: string): CVEditorSaved => ({
  cv: {...active, sha256: NEXT, filename: "smartploy-master-cv.docx", created_by_editor: true},
  history: [{
    sha256: HASH, filename: "original.docx", media_type: active.media_type!,
    size_bytes: 1024, archived: true, archived_at: "2026-10-31T06:00:00Z",
  }],
  employer_actions_performed: 0,
  approved_profile_facts_added: 0,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getSession).mockResolvedValue({
    authenticated: true, user_id: USER,
  });
  vi.mocked(api.getCVEditor).mockResolvedValue({...response});
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function start(options?: {
  cv?: CVDocument; userId?: string;
  onSave?: (text: string, sha: string) => Promise<CVEditorSaved>;
  onSaved?: (cv: CVDocument) => void;
}) {
  const onSave = vi.fn(options?.onSave ?? (async (text: string) => savedResponse(text)));
  const onSaved = vi.fn(options?.onSaved ?? (() => {}));
  render(<MasterCVEditor cv={options?.cv || active}
    expectedUserId={options?.userId || USER} onSave={onSave} onSaved={onSaved}/>);
  return {onSave, onSaved};
}

describe("SP79 owner-private CV creator/editor", () => {
  it("loads full original CV; updates, previews, saves and reveals history", async () => {
    const {onSave, onSaved} = start();
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    expect((editor as HTMLTextAreaElement).value).toBe(original);
    const updated = original + "\n\nEDUCATION\nBachelor degree.";
    fireEvent.change(editor, {target: {value: updated}});
    expect(screen.getByLabelText("CV preview").textContent).toContain("Bachelor degree.");
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(updated, HASH));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(onSaved.mock.calls[0][0].sha256).toBe(NEXT);
    expect(screen.getByText(/Saved. Your active master CV/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Previous CV versions/));
    const older = screen.getByRole("link", {name: "Download previous version"});
    expect(older.getAttribute("href")).toContain(HASH);
    expect(screen.getByRole("link", {name: "PDF"}).getAttribute("href"))
      .toBe("/api/v1/profile/cv/editor/download/pdf");
    expect(screen.getByRole("link", {name: "DOCX"}).getAttribute("href"))
      .toBe("/api/v1/profile/cv/editor/download/docx");
  });

  it("creates a useful blank CV with section headings, never auto-approves", async () => {
    vi.mocked(api.getCVEditor).mockResolvedValue({
      present: false, sha256: "", text: "", filename: "",
      created_by_editor: false, history: [],
      approved_profile_facts_added: 0, employer_actions_performed: 0,
    });
    const {onSave} = start({cv: {present: false}});
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    expect((editor as HTMLTextAreaElement).value).toBe("");
    expect((screen.getByRole("button", {name: "Create master CV"}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Choose CV section to insert"), {target: {value: "SKILLS"}});
    fireEvent.change(editor, {target: {value: "Synthetic Candidate\n\nSKILLS\nPython and SQL."}});
    fireEvent.click(screen.getByRole("button", {name: "Create master CV"}));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      "Synthetic Candidate\n\nSKILLS\nPython and SQL.", ""
    ));
    expect(window.confirm).toHaveBeenCalled();
  });

  it("never discards unsaved text if applicant declines reload", async () => {
    start();
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + " personal update"}});
    vi.mocked(window.confirm).mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", {name: /Reload/}));
    expect((editor as HTMLTextAreaElement).value).toContain("personal update");
    expect(api.getCVEditor).toHaveBeenCalledTimes(1);
  });

  it("blocks an unmatched signed-in user and never renders prior account text", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      authenticated: true, user_id: "usr-synthetic-b",
    });
    const {onSave} = start();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText(original)).toBeNull();
    expect(screen.queryByRole("textbox", {name: "Editable master CV text"})).toBeNull();
    expect(api.getCVEditor).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("does not overwrite local text after rejected stale revision", async () => {
    const {onSaved} = start({
      onSave: async () => { throw new Error("CV changed in another tab"); },
    });
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + " manually edited"}});
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((editor as HTMLTextAreaElement).value).toContain("manually edited");
    expect(onSaved).not.toHaveBeenCalled();
  });
});
