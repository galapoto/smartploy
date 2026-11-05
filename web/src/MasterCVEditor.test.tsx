// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as api from "./api";
import MasterCVEditor from "./MasterCVEditor";
import { parseStructuredCV } from "./structured_cv";
import type { CVDocument, CVEditorDocument, CVEditorSaved, CVEditorRestored, CandidateFact } from "./types";

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
  cv?: CVDocument; userId?: string; facts?: CandidateFact[];
  onSave?: (text: string, sha: string) => Promise<CVEditorSaved>;
  onRestore?: (digest: string, sha: string) => Promise<CVEditorRestored>;
  onSaved?: (cv: CVDocument) => void;
  onUnsavedChange?: (dirty: boolean) => void;
  onWriteStarted?: () => symbol | null;
  onWriteSettled?: (token: symbol) => void;
}) {
  const onSave = vi.fn(options?.onSave ?? (async (text: string) => savedResponse(text)));
  const onRestore = vi.fn(options?.onRestore ?? (async (digest: string) => ({
    cv: {...active, sha256: digest},
    text: original,
    restored_sha256: digest,
    history: [{
      sha256: NEXT, filename: "newer.docx", media_type: active.media_type!,
      size_bytes: 1200, archived: true as const, archived_at: "2026-10-31T09:00:00Z",
    }],
    employer_actions_performed: 0 as const,
    approved_profile_facts_added: 0 as const,
  })));
  const onSaved = vi.fn(options?.onSaved ?? (() => {}));
  render(<MasterCVEditor cv={options?.cv || active}
    expectedUserId={options?.userId || USER}
    facts={options?.facts}
    onSave={onSave} onRestore={onRestore} onSaved={onSaved}
    onWriteStarted={options?.onWriteStarted}
    onWriteSettled={options?.onWriteSettled}
    onUnsavedChange={options?.onUnsavedChange}/>);
  return {onSave, onRestore, onSaved};
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

  it("keeps an imported original verbatim when switching to structured fields", async () => {
    const {onSave, onSaved} = start();
    await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.click(screen.getByRole("button", {name: "Structured editor"}));
    expect(window.confirm).toHaveBeenCalled();
    const imported = screen.getByRole("textbox", {name: "Imported source text"}) as HTMLTextAreaElement;
    expect(imported.value).toBe(original);
    expect(screen.getByLabelText("CV preview").textContent)
      .toContain("Python and SQL verified projects.");
    fireEvent.change(screen.getByRole("textbox", {name: "Full name"}), {
      target: {value: "Synthetic Candidate"},
    });
    fireEvent.change(screen.getByRole("combobox", {name: "Section type"}), {
      target: {value: "projects"},
    });
    fireEvent.click(screen.getByRole("button", {name: "Add section"}));
    fireEvent.change(screen.getByRole("textbox", {name: "Projects 1 Project name"}), {
      target: {value: "QA automation project"},
    });
    fireEvent.change(screen.getByRole("textbox", {name: "Projects 1 description"}), {
      target: {value: "Built actual regression tests."},
    });
    expect(screen.getByLabelText("CV preview").textContent)
      .toContain("Built actual regression tests.");
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      expect.stringContaining("IMPORTED SOURCE TEXT"), HASH,
    ));
    expect(parseStructuredCV(onSave.mock.calls[0][0])?.importedText).toBe(original);
    expect(onSave.mock.calls[0][0]).toContain("QA automation project");
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("declined conversion never changes imported applicant text", async () => {
    start();
    const originalBox = await screen.findByRole("textbox", {name: "Editable master CV text"});
    vi.mocked(window.confirm).mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", {name: "Structured editor"}));
    expect((originalBox as HTMLTextAreaElement).value).toBe(original);
    expect(screen.getByRole("button", {name: "Structured editor"}).getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("textbox", {name: "Imported source text"})).toBeNull();
  });

  it("never allows saving a blank structured document", async () => {
    vi.mocked(api.getCVEditor).mockResolvedValue({
      present: false, sha256: "", text: "", filename: "",
      created_by_editor: false, history: [],
      approved_profile_facts_added: 0, employer_actions_performed: 0,
    });
    const {onSave} = start({cv: {present: false}});
    await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.click(screen.getByRole("button", {name: "Structured editor"}));
    const saveButton = screen.getByRole("button", {name: "Create master CV"}) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", {name: "Full name"}), {
      target: {value: "Alex Applicant"},
    });
    expect(saveButton.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", {name: "Professional profile / summary"}), {
      target: {value: "I can verify Python, SQL and spreadsheet reporting."},
    });
    expect(saveButton.disabled).toBe(false);
    fireEvent.click(saveButton);
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      expect.stringContaining("Full name: Alex Applicant"), "",
    ));
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


describe("SP82 applicant-controlled exact CV version restore", () => {
  const archived = [{
    sha256: HASH, filename: "original.docx", media_type: active.media_type!,
    size_bytes: 1024, archived: true as const, archived_at: "2026-10-31T06:00:00Z",
  }];

  it("restores a selected archived CV only after confirmation with current SHA", async () => {
    const revised = "Newer synthetic CV with verified Power BI and project evidence.";
    vi.mocked(api.getCVEditor).mockResolvedValue({
      ...response, sha256: NEXT, text: revised, filename: "newer.docx", history: archived,
    });
    const {onSave, onRestore, onSaved} = start({
      cv: {...active, sha256: NEXT, filename: "newer.docx"},
    });
    expect((await screen.findByRole("textbox", {name: "Editable master CV text"}) as HTMLTextAreaElement).value)
      .toBe(revised);
    fireEvent.click(screen.getByText(/Previous CV versions/));
    fireEvent.click(screen.getByRole("button", {name: "Restore version aaaaaaaa"}));
    await waitFor(() => expect(onRestore).toHaveBeenCalledWith(HASH, NEXT));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({sha256: HASH}),
    ));
    expect((screen.getByRole("textbox", {name: "Editable master CV text"}) as HTMLTextAreaElement).value)
      .toBe(original);
    expect(screen.getByLabelText("CV preview").textContent).toContain("Python and SQL");
    expect(screen.getByText(/Previous CV restored as your active document/)).toBeTruthy();
    expect(screen.getByRole("button", {name: "Restore version bbbbbbbb"})).toBeTruthy();
    expect(window.confirm).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("never restores on a declined confirmation, preserving unsaved changes", async () => {
    vi.mocked(api.getCVEditor).mockResolvedValue({
      ...response, sha256: NEXT, history: archived,
    });
    const {onRestore} = start({cv: {...active, sha256: NEXT}});
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + " unsaved extra"}});
    vi.mocked(window.confirm).mockReturnValue(false);
    fireEvent.click(screen.getByText(/Previous CV versions/));
    fireEvent.click(screen.getByRole("button", {name: "Restore version aaaaaaaa"}));
    expect(onRestore).not.toHaveBeenCalled();
    expect((editor as HTMLTextAreaElement).value).toContain("unsaved extra");
  });

  it("does not show a false restored version on a rejected revision conflict", async () => {
    vi.mocked(api.getCVEditor).mockResolvedValue({
      ...response, sha256: NEXT, history: archived,
    });
    const {onSaved} = start({
      cv: {...active, sha256: NEXT},
      onRestore: async () => { throw new Error("CV changed in another tab"); },
    });
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.click(screen.getByText(/Previous CV versions/));
    fireEvent.click(screen.getByRole("button", {name: "Restore version aaaaaaaa"}));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((editor as HTMLTextAreaElement).value).toBe(original);
    expect(onSaved).not.toHaveBeenCalled();
  });
});


describe("SP103 master CV editor write lifecycle", () => {
  it("keeps the parent CV write barrier until owner verification and handoff finish", async () => {
    const token = Symbol("cv-save");
    const order: string[] = [];
    let finish!: (value: CVEditorSaved) => void;
    const onSaved = vi.fn(() => order.push("saved"));
    const onWriteSettled = vi.fn((_token: symbol) => { order.push("settled"); });
    const {onSave} = start({
      onWriteStarted: () => { order.push("started"); return token; },
      onWriteSettled,
      onSaved,
      onSave: () => new Promise(resolve => { finish = resolve; }),
    });
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + "\nNew applicant project."}});
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(order).toEqual(["started"]);
    await act(async () => { finish(savedResponse(original)); });
    await waitFor(() => expect(onWriteSettled).toHaveBeenCalledWith(token));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["started", "saved", "settled"]);
  });

  it("releases parent write lock after a rejected save without publishing a CV", async () => {
    const token = Symbol("rejected-cv");
    const onWriteSettled = vi.fn();
    const {onSaved} = start({
      onWriteStarted: () => token, onWriteSettled,
      onSave: async () => { throw new Error("CV revision conflict"); },
    });
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + "\nAn applicant edit."}});
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(onWriteSettled).toHaveBeenCalledWith(token);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("does not mutate a CV if the owner-level write barrier is occupied", async () => {
    const {onSave} = start({ onWriteStarted: () => null });
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.change(editor, {target: {value: original + "\nOne more true fact."}});
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    expect(await screen.findByText(/Another CV update is already in progress/)).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });
});


describe("SP104 master CV unsaved reporting", () => {
  it("reports dirty edits and clears the marker after a verified save", async () => {
    const onUnsavedChange = vi.fn();
    const {onSaved} = start({onUnsavedChange});
    const editor = await screen.findByRole("textbox", {name: "Editable master CV text"});
    expect(onUnsavedChange).toHaveBeenLastCalledWith(false);
    fireEvent.change(editor, {target: {value: original + "\nApplicant verified project."}});
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onUnsavedChange).toHaveBeenLastCalledWith(false));
  });
});


describe("SP133 approved-profile CV generator", () => {
  const fact = (fact_type: string, value: string, approved = true): CandidateFact => ({
    fact_id: fact_type + ":" + value, fact_type, value, approved,
    source: "synthetic-test", confidence: 1,
    created_at: "2026-11-05T00:00:00Z",
  });

  it("offers an unsaved, editable master CV from approved facts and preserves the imported source", async () => {
    const {onSave} = start({facts: [
      fact("identity", "Approved Applicant"),
      fact("skill", "Python"),
      fact("experience", "Analyst at Example Oy, 2024"),
      fact("skill", "Unapproved cybersecurity certificate", false),
    ]});
    await screen.findByRole("textbox", {name: "Editable master CV text"});
    const button = screen.getByRole("button", {name: "Build CV from approved profile"});
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(await screen.findByRole("textbox", {name: "Full name"})).toBeTruthy();
    expect((screen.getByRole("textbox", {name: "Full name"}) as HTMLInputElement).value)
      .toBe("Approved Applicant");
    const source = screen.getByRole("textbox", {name: "Imported source text"}) as HTMLTextAreaElement;
    expect(source.value).toBe(original);
    expect(screen.getByLabelText("CV preview").textContent).toContain("Analyst at Example Oy, 2024");
    expect(screen.getByLabelText("CV preview").textContent).not.toContain("Unapproved cybersecurity");
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText(/UNSAVED structured CV draft/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", {name: "Save updated CV"}));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const submittedText = onSave.mock.calls[0][0];
    expect(submittedText).toContain("Approved Applicant");
    expect(submittedText).toContain("Python");
    expect(submittedText).toContain("IMPORTED SOURCE TEXT");
    expect(submittedText).not.toContain("Unapproved cybersecurity");
    expect(parseStructuredCV(submittedText)?.importedText).toBe(original);
  });

  it("does not invent an applicant name or allow saving only skill facts", async () => {
    const {onSave} = start({facts: [fact("skill", "SQL")]});
    await screen.findByRole("textbox", {name: "Editable master CV text"});
    fireEvent.click(screen.getByRole("button", {name: "Build CV from approved profile"}));
    expect(await screen.findByRole("textbox", {name: "Full name"})).toBeTruthy();
    expect((screen.getByRole("textbox", {name: "Full name"}) as HTMLInputElement).value)
      .toBe("");
    expect((screen.getByRole("button", {name: "Save updated CV"}) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("CV-only users without approved facts retain the manual editor and no generator write", async () => {
    const {onSave} = start({facts: []});
    await screen.findByRole("textbox", {name: "Editable master CV text"});
    const generate = screen.getByRole("button", {name: "Build CV from approved profile"});
    expect((generate as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(generate);
    expect(onSave).not.toHaveBeenCalled();
  });
});
