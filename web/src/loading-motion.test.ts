// @ts-expect-error Intentional Node-only source reading in Vitest; browser tsc omits Node ambient types.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const shell = readFileSync(new URL("./sp127-mobile-shell.css", import.meta.url), "utf8");

describe("V4 motion acceptance: no endless rotations while loading", () => {
  it("shows an accessible, static progress indicator while the account loads", () => {
    // SP127's immediate, non-private startup shell replaces the old
    // blocking full-page progress screen with a static status line.
    expect(app).toContain('className="sp-boot-progress" role="progressbar"');
    expect(app).toContain('role={props.loading ? "status" : "alert"}');
    expect(shell).toContain(".sp-boot-progress");
    expect(app).not.toContain('className="loading-progress-track"');
    expect(app).not.toContain('className="spinner"');
    expect(styles).not.toContain("@keyframes spin");
    expect(styles).not.toContain("animation: spin");
  });
  it("keeps refresh feedback but does not rotate the refresh icon", () => {
    expect(app).toContain('aria-label={refreshing ? "Refreshing workspace" : "Refresh workspace"}');
    expect(app).not.toContain('className={refreshing ? "rotate" : ""}');
    expect(styles).not.toContain(".rotate {");
  });
});
