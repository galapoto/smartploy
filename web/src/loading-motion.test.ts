// @ts-expect-error Intentional Node-only source reading in Vitest; browser tsc omits Node ambient types.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

describe("V4 motion acceptance: no endless rotations while loading", () => {
  it("shows an accessible, static progress indicator while the account loads", () => {
    expect(app).toContain('className="loading-progress-track"');
    expect(app).toContain('role="status" aria-busy="true"');
    expect(styles).toContain(".loading-progress-track");
    expect(styles).toContain(".loading-progress-fill");
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
