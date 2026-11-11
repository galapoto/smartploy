// @ts-expect-error Node-only source reading in Vitest.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./sp-v4-card-surfaces.css", import.meta.url), "utf8");
const entry = readFileSync(new URL("./main.tsx", import.meta.url), "utf8");

describe("V4 shadcn-adapted surface system", () => {
  it("loads one dependency-free surface layer last and preserves all older code", () => {
    const original = entry.indexOf('import "./sp-v4-monochrome.css";');
    const surfaces = entry.indexOf('import "./sp-v4-card-surfaces.css";');
    expect(original).toBeGreaterThanOrEqual(0);
    expect(surfaces).toBeGreaterThan(original);
    expect(entry.slice(surfaces).trim()).toBe('import "./sp-v4-card-surfaces.css";\n\nReactDOM.createRoot(document.getElementById("root")!).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>\n);');
    expect(css).not.toContain("@import");
    expect(css).not.toContain("!important");
  });

  it("pairs dark surfaces with light text and light surfaces with dark text", () => {
    expect(css).toContain("--sp-ui-card:#101821");
    expect(css).toContain("--sp-ui-ink:#f7faff");
    expect(css).toContain('--sp-ui-card:#fff');
    expect(css).toContain("--sp-ui-ink:#112334");
    expect(css).toContain(".flow-primary-next-copy strong");
    expect(css).toContain("background-image:none");
    expect(css).toContain("color:var(--sp-ui-muted)");
    expect(css).toContain("border-left:3px solid var(--sp-ui-accent)");
  });

  it("preserves disabled method cards, warning/error meaning and unambiguous selection", () => {
    expect(css).toContain(".flow-mode[data-flow-mode]:disabled");
    expect(css).toContain(".flow-start-card[data-flow-mode]:disabled");
    expect(css).toContain("opacity:.68");
    expect(css).toContain("cursor:not-allowed");
    expect(css).toContain(".studio-alert.error");
    expect(css).toContain("border-left-color:var(--sp-ui-error)");
    expect(css).toContain(".studio-ai-risks > strong");
    expect(css).toMatch(/\.studio-ai-risks > strong\s*\{\s*color:var\(--sp-ui-warning\)/);
    expect(css).not.toMatch(/\.studio-ai-risks strong\s*\)/);
    expect(css).not.toContain(".studio-alert,.studio-ai-risks,.flow-start-method-status");
    expect(css).toContain("border-left-color:var(--sp-ui-warning)");
    expect(css).toContain(".studio-list-item:hover:not(.selected)");
    expect(css).toContain(".studio-list-item.selected");
    expect(css).toContain("inset 3px 0 0 var(--sp-ui-accent)");
  });

  it("closes remaining pale status, automation, handoff and editor surfaces", () => {
    for (const selector of [
      ".flow-signal-summary", ".flow-choice-locked", ".flow-error",
      ".studio-automation", ".studio-automation-approval",
      ".studio-handoff", ".studio-handoff-blockers", ".studio-attempt-reserved",
      ".studio-receipt", ".studio-ai-preview",
      ".studio-list-heading span", ".studio-review-queue-filters button",
      ".sp126-dashboard-main .flow-start-browse-button",
      ".studio-document textarea", ".studio-packet-fallback textarea",
      ".studio-receipt-import textarea",
    ]) expect(css, selector).toContain(selector);
    expect(css).toContain("SP V4 / M1 CONTRAST-CLOSURE-002");
    expect(css).toContain("background:var(--sp-ui-card)");
    expect(css).toContain("background:var(--sp-ui-card-raised)");
    expect(css).toContain(".studio-review-queue-filters button span");
    expect(css).toContain('.studio-review-queue-filters button:not([aria-pressed="true"]):hover:not(:disabled)');
    expect(css).toContain('.studio-review-queue-filters button[aria-pressed="true"] span');
    expect(css).toContain("border-left:3px solid var(--sp-ui-warning)");
    expect(css).toContain("border-left:3px solid var(--sp-ui-error)");
    expect(css).not.toContain("!important");
    expect(css).not.toContain("@import");
  });

  it("covers the formerly mint-tinted document and application cards", () => {
    for (const selector of [
      ".flow-primary-next", ".flow-uploaded", ".flow-start-ready",
      ".flow-queue", ".flow-job-next", ".flow-choice-gate",
      ".document-coach", ".document-comparison", ".document-coach-checks li",
      ".studio-ai-card", ".studio-ai-proof", ".studio-letter-proposal",
      ".studio-info", ".studio-document-undo", ".tools-ai-readiness",
      ".studio-list-item.selected", ".studio-resume-card.selected",
      ".flow-start-method-status", ".studio-ai-risks", ".studio-review-queue",
      ".studio-list-copy strong", ".studio-resume-intro h3",
      ".studio-automation-header h3", ".studio-handoff-header h4",
      ".flow-job h3",
      ".flow-job", ".search-result-card", ".flow-mode[data-flow-mode]",
      ".flow-start-grid-methods .flow-start-card[data-flow-mode]",
    ]) expect(css, selector).toContain(selector);
    expect(css).toContain("prefers-reduced-motion:reduce");
  });
});
