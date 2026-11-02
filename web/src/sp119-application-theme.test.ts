import { describe, expect, it } from "vitest";
import css from "./sp119-application-theme.css?raw";
// The production SVG is fetched and validated in real Chromium browser acceptance.

function relativeLuminance(hex: string): number {
  const rgb = [1, 3, 5].map((index) => {
    const channel = Number.parseInt(hex.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4);
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

function contrastRatio(a: string, b: string): number {
  const top = Math.max(relativeLuminance(a), relativeLuminance(b));
  const bottom = Math.min(relativeLuminance(a), relativeLuminance(b));
  return (top + 0.05) / (bottom + 0.05);
}

describe("SP119 application banner and dark-mode readability contract", () => {
  it("loads the local application hero, keyboard focus and responsive styles", () => {
    expect(css).toContain(".sp119-application-cover");
    expect(css).toContain(".sp119-cover-art");
    expect(css).toContain(".sp119-cover-title");
    expect(css).toContain(".sp119-cover-description");
    expect(css).toContain(".sp119-cover-action:focus-visible");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("@media (max-width: 650px)");
    expect(css).toContain('html[data-smartploy-theme="dark"]');
  });

  it("provides at least WCAG AAA contrast for normal dark-mode foreground labels", () => {
    const foregroundBackgroundPairs = [
      ["#f2f8ff", "#192a40"], // main headings
      ["#bfdee9", "#192a40"], // previously unreadable masthead
      ["#a6dfe5", "#21354c"], // Finland/private workspace secondary label
      ["#cadcec", "#1a2d43"], // mode card descriptions
      ["#c6d7ec", "#192a40"], // guidance and privacy
      ["#f1cf97", "#2b394c"], // CV required
      ["#7fe4f2", "#192a40"], // application section kicker
    ] as const;
    for (const [foreground, background] of foregroundBackgroundPairs) {
      expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(7);
    }
    expect(css).toContain('.flow-start-progress li.current');
    expect(css).toContain('.flow-start-grid-methods .flow-start-card:disabled');
  });
});
