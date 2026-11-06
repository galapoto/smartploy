// @ts-expect-error Intentional Node-only source reading in Vitest; browser tsc omits Node ambient types.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./sp125-workspace-theme.css", import.meta.url), "utf8");
const art = readFileSync(new URL("../public/smartploy-career-workflow-banner.svg", import.meta.url), "utf8");

function luminance(hex: string): number {
  const v = [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255)
    .map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  return v[0] * .2126 + v[1] * .7152 + v[2] * .0722;
}
function contrast(a: string, b: string): number {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x,y) + .05) / (Math.min(x,y) + .05);
}

describe("SP125 real dark screenshot regression", () => {
  it("uses a near-black canvas and readable elevated action surfaces", () => {
    expect(css).toContain("--sp125-bg: #080f1b");
    expect(css).toContain("--sp125-card: #142235");
    expect(css).toContain("--sp125-raised: #1b2d44");
    expect(css).toContain(".flow-start-browse-button");
    expect(css).toContain(".release-status");
    expect(contrast("#f2f7ff", "#142235")).toBeGreaterThanOrEqual(7);
    expect(contrast("#b9cee2", "#1b2d44")).toBeGreaterThanOrEqual(7);
    expect(contrast("#d7f8e6", "#173f36")).toBeGreaterThanOrEqual(7);
  });

  it("removes the old flow width caps and handles zoom-width mobile", () => {
    expect(css).toContain(".flow-first-use .flow-start");
    expect(css).toContain("max-width: none");
    expect(css).toContain("repeat(auto-fit,minmax(min(100%,242px),1fr))");
    expect(css).toContain("@media(max-width:720px)");
    expect(css).toContain("@media(prefers-reduced-motion:reduce)");
  });

  it("ships an original job application visual, not a landscape or fake job record", () => {
    expect(art).toContain('viewBox="0 0 1600 320"');
    expect(art).toContain("Opportunities for you");
    expect(art).toContain("CV and job opportunities");
    expect(art).not.toContain("<script");
    expect(art).not.toContain("http://www.w3.org/1999/xhtml");
  });
});
