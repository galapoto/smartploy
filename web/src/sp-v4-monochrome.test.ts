// @ts-expect-error Node-only source reading in Vitest.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Browser tests cover the actual release indicator. This source test ensures
// mobile CSS cannot silently hide the critical development-build warning.
const mobileCSS = readFileSync(new URL("./sp128-mobile-workflow.css", import.meta.url), "utf8");
const css=readFileSync(new URL("./sp-v4-monochrome.css",import.meta.url),"utf8");
const app=readFileSync(new URL("./App.tsx",import.meta.url),"utf8");
describe("SmartPloy brand focus",()=>{
  it("keeps one black-white palette with only first-party cyan and navy",()=>{
    expect(css).toContain("--sp-brand-black:#05070b");
    expect(css).toContain("--sp-brand-white:#f7faff");
    expect(css).toContain("--sp-brand-cyan:#06d9e8");
    expect(css).toContain("--sp-brand-navy:#021e3d");
    expect(css).toContain(".flow-start-card[data-flow-mode]");
    expect(css).toContain(".sp126-dashboard-aside");
  });

  it("fixes low-contrast guidance and hides inactive stages without losing handlers",()=>{
    expect(css).toContain("SP V4 FLOW-CLARITY-001");
    expect(css).toContain(".flow-boundary,.flow-decision,.flow-selection-confirmation");
    expect(css).toContain("background:#101c2a");
    expect(css).toContain("color:#f1f7ff");
    expect(css).toContain(".application-flow [hidden] {display:none!important}");
    expect(css).toContain(".flow-session-tools");
    expect(css).toContain(".studio-assisted-guide h4");
  });
  it("uses a nonrotating loading state and short brand tagline",()=>{
    expect(app).not.toContain('className="spinner"');
    expect(app).not.toContain('className={refreshing ? "rotate" : ""}');
    expect(app).toContain("Job intelligence");
    expect(app).not.toContain("Job intelligence for Finland");
    expect(css).toContain("animation:none!important");
  });
});

describe("release-status safety on mobile", () => {
  it("hides only routine version badges, not the development-build warning", () => {
    expect(mobileCSS).toContain(".release-status-aligned,.release-status-checking");
    expect(mobileCSS).not.toContain(".release-status-aligned,.release-status-development");
  });
});
