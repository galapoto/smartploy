import { useEffect, useLayoutEffect, useState } from "react";

export type SmartployTheme = "light" | "dark";
export const SMARTPLOY_THEME_KEY = "smartploy-ui-theme-v1";

export function savedSmartployTheme(): SmartployTheme | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(SMARTPLOY_THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch { return null; }
}

export function initialSmartployTheme(): SmartployTheme {
  const stored = savedSmartployTheme();
  if (stored) return stored;
  // New visitors see the approved black SmartPloy palette; persisted light preference stays respected.
  return "dark";
}

export function applySmartployTheme(theme: SmartployTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-smartploy-theme", theme);
  document.documentElement.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#05070b" : "#f4f7fb");
}

/** One explicit user preference for the entire app, not tied to applicant data. */
export function useSmartployTheme(): [SmartployTheme, () => void] {
  const [theme, setTheme] = useState<SmartployTheme>(initialSmartployTheme);
  useLayoutEffect(() => { applySmartployTheme(theme); }, [theme]);
  useEffect(() => {
    // Storage access can be blocked in hardened/private browser contexts.
    try { window.localStorage.setItem(SMARTPLOY_THEME_KEY, theme); } catch {}
  }, [theme]);
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== SMARTPLOY_THEME_KEY) return;
      if (event.newValue === "light" || event.newValue === "dark") {
        setTheme(event.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return [theme, () => setTheme(current => current === "dark" ? "light" : "dark")];
}
