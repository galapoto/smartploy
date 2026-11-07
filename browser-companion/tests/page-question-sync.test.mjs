import test from "node:test";
import assert from "node:assert/strict";
import { rememberQuestionsOnSmartPloy } from "../page-question-sync.mjs";

function batch() {
  return {
    schema: "smartploy.pending_questions.v1",
    workspace_id: "kit-" + "a".repeat(30),
    expected_revision: 3,
    expected_document_sha256: "b".repeat(64),
    expected_cv_pdf_sha256: "c".repeat(64),
    expected_fields_sha256: "d".repeat(64),
    expected_application_url_sha256: "e".repeat(64),
    expected_cv_pdf_size: 12000,
    expires_at: Date.now() + 180000,
    questions: [{
      label: "Which programming languages have you worked with?",
      expected_id: "languages", expected_name: "languages",
      expected_placeholder: "",
    }],
  };
}
const owner = "usr-" + "f".repeat(32);
const approvedReview = {
  review_verified: true, review_state: "pending",
  automatic_employer_submit_authorized: false,
  browser_grant_issued: false, external_actions_performed: false,
};
const approvedSave = {
  questions: [{ question_key: "a".repeat(64), label: batch().questions[0].label }],
  remembered_count: 1, skipped_sensitive_or_duplicate: 0,
  answers_inferred_from_cv: 0, employer_actions_performed: 0,
};

async function run(origin, {
  nested = false, signedIn = true, authSource = "oidc",
  review = approvedReview, mode = "guided", save = approvedSave,
  reviewStatus = 200, saveStatus = 200, breakConnection = false,
  payload = batch(),
} = {}) {
  const previous = {
    fetch: globalThis.fetch, location: globalThis.location,
    window: globalThis.window,
  };
  const calls = [];
  const frame = {};
  globalThis.location = {
    origin, protocol: origin.startsWith("https:") ? "https:" : "http:",
  };
  globalThis.window = nested ? { top: {}, self: frame } : { top: frame, self: frame };
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    if (breakConnection) throw new TypeError("Network denied");
    if (url === "/api/v1/session") {
      return { ok: signedIn, async json() {
        return { authenticated: signedIn, auth_source: authSource, user_id: owner };
      } };
    }
    if (url.includes("/verify-reviewed-packet")) {
      return { ok: reviewStatus === 200, status: reviewStatus,
        async json() { return review; } };
    }
    if (url === "/api/v1/profile/application-questions" && opts.method === "GET") {
      return { ok: true, async json() { return { mode }; } };
    }
    if (url === "/api/v1/profile/application-questions/observe") {
      return { ok: saveStatus === 200, status: saveStatus,
        async json() { return save; } };
    }
    throw Error("Unexpected request " + url);
  };
  try {
    return { result: await rememberQuestionsOnSmartPloy(payload), calls };
  } finally {
    for (const [k,v] of Object.entries(previous)) {
      if (v === undefined) delete globalThis[k];
      else globalThis[k] = v;
    }
  }
}

test("signed-in OIDC first-party tab syncs only question prompts under exact review", async () => {
  const {result, calls} = await run("https://smartploy.komplyint.fi");
  assert.deepEqual(result, {
    synced: true, remembered_count: 1, skipped: 0,
    answers_inferred_from_cv: 0, employer_actions_performed: 0,
  });
  assert.deepEqual(calls.map(c=>c.url), [
    "/api/v1/session",
    "/api/v1/application-workspaces/" + batch().workspace_id + "/verify-reviewed-packet",
    "/api/v1/profile/application-questions",
    "/api/v1/profile/application-questions/observe",
  ]);
  for(const {url,opts} of calls) {
    assert.equal(url.startsWith("/api/v1/"), true);
    assert.equal(opts.credentials, "same-origin");
    assert.equal(opts.cache, "no-store");
    assert.equal(opts.redirect, "error");
    assert.equal(opts.headers.Authorization, undefined);
    assert.equal(opts.headers.Cookie, undefined);
    if(opts.method === "POST") {
      assert.equal(opts.headers["X-Smartploy-Expected-User-Id"], owner);
    }
  }
  assert.deepEqual(JSON.parse(calls[3].opts.body), {
    workspace_id: batch().workspace_id,
    expected_revision: 3, questions: batch().questions,
  });
  assert.equal(JSON.stringify(result).includes(owner), false);
  assert.equal(JSON.stringify(calls[3].opts.body).includes("PRIVATE ANSWER"), false);
});

test("old first-party hostname works, but untrusted hosts and nested frames never call network", async () => {
  const old = await run("https://smartploy.obumai.com");
  assert.equal(old.result.synced, true);
  for(const origin of [
    "http://smartploy.komplyint.fi",
    "https://smartploy.komplyint.fi.evil.invalid",
    "https://example.invalid",
    "https://smartploy.komplyint.fi:9443",
  ]) {
    const { result, calls } = await run(origin);
    assert.equal(result.reason, "wrong_origin");
    assert.equal(calls.length, 0);
  }
  const nested = await run("https://smartploy.komplyint.fi", {nested:true});
  assert.equal(nested.result.reason, "wrong_origin");
  assert.equal(nested.calls.length, 0);
});

test("CV-only mode is honored and no question observation POST is made", async () => {
  const {result,calls}=await run("https://smartploy.komplyint.fi", {mode:"cv_only"});
  assert.deepEqual(result, {synced:false,reason:"cv_only",profile_mode:"cv_only"});
  assert.equal(calls.length, 3);
  assert.equal(calls.some(c=>c.url.endsWith("/observe")), false);
});

test("anonymous, non-OIDC, expired packet and wrong revision all fail closed", async () => {
  const anon=await run("https://smartploy.komplyint.fi",{signedIn:false});
  assert.equal(anon.result.reason,"sign_in_required");
  assert.equal(anon.calls.length,1);
  const other=await run("https://smartploy.komplyint.fi",{authSource:"cloudflare"});
  assert.equal(other.result.reason,"sign_in_required");
  assert.equal(other.calls.length,1);
  const expired=await run("https://smartploy.komplyint.fi",{
    payload:{...batch(),expires_at:Date.now()-1},
  });
  assert.equal(expired.result.reason,"invalid_or_expired_handoff");
  assert.equal(expired.calls.length,0);
  const stale=await run("https://smartploy.komplyint.fi",{reviewStatus:409});
  assert.equal(stale.result.reason,"review_expired_or_changed");
  assert.equal(stale.calls.length,2);
});

test("server reply cannot authorize submission or silently claim unverified storage", async () => {
  const unsafe=await run("https://smartploy.komplyint.fi",{
    review:{...approvedReview,automatic_employer_submit_authorized:true},
  });
  assert.equal(unsafe.result.reason,"review_not_authorized");
  assert.equal(unsafe.calls.length,2);
  const writes=await run("https://smartploy.komplyint.fi",{saveStatus:403});
  assert.equal(writes.result.reason,"profile_write_unavailable");
  const unverified=await run("https://smartploy.komplyint.fi",{
    save:{...approvedSave,employer_actions_performed:1},
  });
  assert.equal(unverified.result.reason,"unverified_profile_response");
  const switched=await run("https://smartploy.komplyint.fi",{
    save:{...approvedSave,profile_mode:"cv_only"},
  });
  assert.equal(switched.result.reason,"cv_only");
  const offline=await run("https://smartploy.komplyint.fi",{breakConnection:true});
  assert.equal(offline.result.reason,"connection_or_identity_uncertain");
});
