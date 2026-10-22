import test from "node:test";
import assert from "node:assert/strict";
import { verifyReviewOnSmartPloy } from "../page-review.mjs";

const binding = Object.freeze({
  workspace_id: "kit-" + "a".repeat(30),
  expected_revision: 2,
  expected_document_sha256: "b".repeat(64),
  expected_cv_pdf_sha256: "c".repeat(64),
  expected_fields_sha256: "d".repeat(64),
  expected_application_url_sha256: "e".repeat(64),
  expected_cv_pdf_size: 12000,
});
const approved = {
  review_verified: true, review_state: "pending",
  expires_at: "2026-10-22T22:00:00Z",
  browser_grant_issued: false,
  automatic_employer_submit_authorized: false,
  external_actions_performed: false,
};
const session = {
  authenticated: true, auth_source: "oidc", user_id: "usr-" + "f".repeat(32),
};

async function executeAt(origin, {
  signedIn = true, authSource = "oidc", nested = false,
  simulateRedirect = false,
} = {}) {
  const prior = {
    fetch: globalThis.fetch,
    location: globalThis.location,
    window: globalThis.window,
  };
  const requests = [];
  const frame = {};
  globalThis.location = {
    origin, protocol: origin.startsWith("https:") ? "https:" : "http:",
  };
  globalThis.window = nested
    ? { top: {}, self: frame }
    : { top: frame, self: frame };
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (simulateRedirect) throw new TypeError("Blocked cross-origin redirect");
    if (url === "/api/v1/session") {
      return {
        ok: signedIn,
        async json() { return { ...session, auth_source: authSource }; },
      };
    }
    if (url.includes("/verify-reviewed-packet")) {
      return { ok: true, async json() { return approved; } };
    }
    throw new Error("Unexpected destination " + url);
  };
  try {
    return { outcome: await verifyReviewOnSmartPloy(binding), requests };
  } finally {
    if (prior.fetch === undefined) delete globalThis.fetch;
    else globalThis.fetch = prior.fetch;
    if (prior.location === undefined) delete globalThis.location;
    else globalThis.location = prior.location;
    if (prior.window === undefined) delete globalThis.window;
    else globalThis.window = prior.window;
  }
}

test("Komplyint OIDC origin verifies an exact packet with same-origin cookies only", async () => {
  const { outcome, requests } = await executeAt("https://smartploy.komplyint.fi");
  assert.equal(outcome.review_verified, true);
  assert.equal(outcome.browser_grant_issued, false);
  assert.equal(outcome.automatic_employer_submit_authorized, false);
  assert.equal(outcome.external_actions_performed, false);
  assert.deepEqual(
    requests.map(item => item.url),
    ["/api/v1/session", "/api/v1/application-workspaces/" +
      binding.workspace_id + "/verify-reviewed-packet"],
  );
  for (const { options } of requests) {
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.equal(options.headers.Authorization, undefined);
  }
  const body = JSON.parse(requests[1].options.body);
  assert.deepEqual(body, binding);
  assert.equal(requests[1].options.headers["X-Smartploy-Expected-User-Id"], session.user_id);
  assert.equal(JSON.stringify(outcome).includes(session.user_id), false);
});

test("legacy first-party origin accepts OIDC only, not Cloudflare session", async () => {
  const valid = await executeAt("https://smartploy.obumai.com");
  assert.equal(valid.outcome.review_verified, true);
  const old = await executeAt("https://smartploy.obumai.com", { authSource: "cloudflare" });
  assert.equal(old.outcome.review_verified, false);
  assert.equal(old.outcome.reason, "sign_in_required");
  assert.equal(old.requests.length, 1);
});

test("untrusted origins, HTTP and nested frames never initiate a request", async () => {
  for (const origin of [
    "http://smartploy.komplyint.fi",
    "https://smartploy.komplyint.fi.evil.invalid",
    "https://smartploy.obumai.com.evil.invalid",
    "https://komplyint.fi",
    "https://example.invalid",
    "https://smartploy.komplyint.fi:444",
  ]) {
    const { outcome, requests } = await executeAt(origin);
    assert.equal(outcome.reason, "wrong_origin", origin);
    assert.deepEqual(requests, [], origin);
  }
  const frame = await executeAt("https://smartploy.komplyint.fi", { nested: true });
  assert.equal(frame.outcome.reason, "wrong_origin");
  assert.equal(frame.requests.length, 0);
});

test("signed-out or redirected first-party verification fails closed", async () => {
  const anon = await executeAt("https://smartploy.komplyint.fi", { signedIn: false });
  assert.equal(anon.outcome.reason, "sign_in_required");
  assert.equal(anon.requests.length, 1);
  const redirect = await executeAt("https://smartploy.komplyint.fi", {
    simulateRedirect: true,
  });
  assert.equal(redirect.outcome.reason, "smartploy_unreachable");
  assert.equal(redirect.requests.length, 1);
});

test("invalid packet metadata cannot reach signed-in server endpoint", async () => {
  const old = { location: globalThis.location, window: globalThis.window, fetch: globalThis.fetch };
  const top = {};
  globalThis.location = {
    origin: "https://smartploy.komplyint.fi", protocol: "https:",
  };
  globalThis.window = { top, self: top };
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw Error("No calls permitted"); };
  try {
    assert.deepEqual(
      await verifyReviewOnSmartPloy({ ...binding, expected_revision: 0 }),
      { review_verified: false, reason: "invalid_binding" },
    );
    assert.equal(calls, 0);
  } finally {
    for (const [key, value] of Object.entries(old)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
});
