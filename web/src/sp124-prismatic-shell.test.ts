import { describe, expect, it } from "vitest";
import css from "./sp124-prismatic-shell.css?raw";

/** Static policy tests complement real Chromium computed-style tests. */
function hexLuminance(hex: string): number {
  const rgb = [1, 3, 5].map(offset =>
    parseInt(hex.slice(offset, offset + 2), 16) / 255
  ).map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}
function ratio(foreground: string, background: string): number {
  const a = hexLuminance(foreground), b = hexLuminance(background);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}

describe("SP124 Prismatic release: accessible workspace and reversible sidebar", () => {
  it("uses the SmartPloy Prismatic font pairing and original CV-first shell", () => {
    expect(css).toContain("Plus Jakarta Sans");
    expect(css).toContain("Onest");
    expect(css).toContain(".studio-layout");
    expect(css).toContain(".application-flow");
    expect(css).toContain("data-sidebar-size=\"compact\"");
    expect(css).toContain(".sp124-sidebar-toggle");
  });

  it("has readable sampled dark cards and muted text pairs", () => {
    expect(ratio("#f4f8ff", "#192b40")).toBeGreaterThanOrEqual(7);
    expect(ratio("#c2d5e8", "#192b40")).toBeGreaterThanOrEqual(7);
    expect(ratio("#f4f8ff", "#21364e")).toBeGreaterThanOrEqual(7);
    expect(ratio("#172d55", "#ffffff")).toBeGreaterThanOrEqual(7);
    expect(css).toContain(".studio-review-queue");
    expect(css).toContain(".document-coach-checks li");
    expect(css).toContain(".studio-next-action.state-attention");
    expect(css).toContain("html[data-smartploy-theme=\"dark\"]");
    expect(css).toContain("--sp124-surface:#192b40");
  });

  it("expands content and treats browser zoom as reduced CSS viewport width", () => {
    expect(css).toContain("max-width:none");
    expect(css).toContain("container-type:inline-size");
    expect(css).toContain("@container (max-width:880px)");
    expect(css).toContain("@media(max-width:1000px)");
    expect(css).toContain("width:min(300px,85vw)");
    expect(css).toContain("@media(prefers-reduced-motion:reduce)");
  });

  it("keeps visible keyboard focus and does not use universal CSS !important overrides", () => {
    expect(css).toContain("outline:3px solid var(--sp124-focus)");
    expect(css).not.toContain("!important");
  });
});
