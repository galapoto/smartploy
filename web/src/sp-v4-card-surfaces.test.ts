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

  it("covers the formerly mint-tinted document and application cards", () => {
    for (const selector of [
      ".flow-primary-next", ".flow-uploaded", ".flow-start-ready",
      ".flow-queue", ".flow-job-next", ".flow-choice-gate",
      ".document-coach", ".document-comparison", ".document-coach-checks li",
      ".studio-ai-card", ".studio-ai-proof", ".studio-letter-proposal",
      ".studio-info", ".studio-document-undo", ".tools-ai-readiness",
      ".studio-list-item.selected", ".studio-resume-card.selected",
      ".flow-start-method-status", ".studio-ai-risks", ".studio-review-queue",
      ".flow-job", ".search-result-card", ".flow-mode[data-flow-mode]",
      ".flow-start-grid-methods .flow-start-card[data-flow-mode]",
    ]) expect(css, selector).toContain(selector);
    expect(css).toContain("prefers-reduced-motion:reduce");
  });
});
