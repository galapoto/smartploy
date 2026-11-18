// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SignIn from "./SignIn";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("SmartPloy branded ZITADEL entry", () => {
  it("does not fake an unconfigured Google provider", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ google: false }),
    }));
    render(<SignIn />);
    expect(screen.getByRole("heading", { name: /Apply with confidence/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Continue securely/ }).getAttribute("href"))
      .toBe("/auth/login");
    expect(screen.getByRole("button", { name: "Sign in with Google (unavailable)" }))
      .toHaveProperty("disabled", true);
    await screen.findByText(/Google sign-in will be available/);
    expect(screen.getByRole("button", { name: "Sign in with Google (unavailable)" })
      .querySelector("img")?.getAttribute("src")).toBe("/google-signin-light.png");
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
    expect(screen.getByRole("link", { name: /Create account securely/ }).getAttribute("href"))
      .toBe("/auth/login?intent=signup");
    expect(screen.getByRole("button", { name: "Sign up with Google (unavailable)" })
      .querySelector("img")?.getAttribute("src")).toBe("/google-signup-light.png");
  });
  it("uses the provider-gated ZITADEL path for Google sign in and sign up", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ google: true }),
    }));
    render(<SignIn />);
    await waitFor(() => expect(screen.getByRole("link", {
      name: "Sign in with Google",
    })).toBeTruthy());
    expect(screen.getByRole("link", { name: "Sign in with Google" })
      .getAttribute("href")).toBe("/auth/login?provider=google");
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
    expect(screen.getByRole("link", { name: "Sign up with Google" })
      .getAttribute("href")).toBe("/auth/login?intent=signup&provider=google");
    expect(screen.queryByText(/Google sign-in will be available/)).toBeNull();
  });
});
