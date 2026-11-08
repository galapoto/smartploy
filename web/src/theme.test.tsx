// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { applySmartployTheme, initialSmartployTheme, savedSmartployTheme,
  SMARTPLOY_THEME_KEY, useSmartployTheme } from "./theme";

function ThemeProbe() {
  const [theme, toggle] = useSmartployTheme();
  return <button type="button" onClick={toggle}>
    Current {theme}; switch mode
  </button>;
}

beforeEach(() => {
  window.localStorage.removeItem(SMARTPLOY_THEME_KEY);
  document.documentElement.removeAttribute("data-smartploy-theme");
  document.documentElement.style.colorScheme = "";
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
});
afterEach(() => {
  cleanup();
  window.localStorage.removeItem(SMARTPLOY_THEME_KEY);
  document.documentElement.removeAttribute("data-smartploy-theme");
  document.documentElement.style.colorScheme = "";
  vi.unstubAllGlobals();
});

describe("SP99 persistent light/dark preference", () => {
  it("uses the approved black default with no stored preference", () => {
    expect(initialSmartployTheme()).toBe("dark");
    expect(savedSmartployTheme()).toBeNull();
  });

  it("preserves an explicitly chosen light theme but otherwise defaults to dark", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    expect(initialSmartployTheme()).toBe("dark");
    window.localStorage.setItem(SMARTPLOY_THEME_KEY, "light");
    expect(initialSmartployTheme()).toBe("light");
    window.localStorage.setItem(SMARTPLOY_THEME_KEY, "INVALID");
    expect(initialSmartployTheme()).toBe("dark");
  });

  it("actually switches root styles, remembers the choice and restores it in a new mount", () => {
    const view = render(<ThemeProbe />);
    expect(screen.getByRole("button", { name: "Current dark; switch mode" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Current dark; switch mode" }));
    expect(document.documentElement.dataset.smartployTheme).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(window.localStorage.getItem(SMARTPLOY_THEME_KEY)).toBe("light");
    view.unmount();
    render(<ThemeProbe />);
    expect(screen.getByRole("button", { name: "Current light; switch mode" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Current light; switch mode" }));
    expect(document.documentElement.dataset.smartployTheme).toBe("dark");
    expect(window.localStorage.getItem(SMARTPLOY_THEME_KEY)).toBe("dark");
  });

  it("updates a browser theme-color and handles a preference change from another tab", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
    applySmartployTheme("dark");
    expect(meta.content).toBe("#05070b");
    applySmartployTheme("light");
    expect(meta.content).toBe("#f4f7fb");
    render(<ThemeProbe />);
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", {
        key: SMARTPLOY_THEME_KEY, newValue: "dark",
      }));
    });
    expect(screen.getByRole("button", { name: "Current dark; switch mode" })).toBeTruthy();
    meta.remove();
  });
});
