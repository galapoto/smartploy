/* SP117: user-triggered ONLY on an active, signed-in first-party SmartPloy
 * tab through chrome.scripting.executeScript({ world: "ISOLATED" }).
 * Self-contained: Chrome serializes this function without imported helpers.
 *
 * Browser session cookie stays inside the signed-in tab. The extension gets
 * only counts and a non-authoritative result, NEVER a user ID, raw answer,
 * CV, login token or employer submission authorization.
 */
export async function rememberQuestionsOnSmartPloy(batch) {
  const origins = ["https://smartploy.komplyint.fi", "https://smartploy.obumai.com"];
  if (!origins.includes(location.origin) || location.protocol !== "https:" ||
      (typeof window !== "undefined" && window.top !== window.self)) {
    return { synced: false, reason: "wrong_origin" };
  }
  const hex = /^[a-f0-9]{64}$/;
  if (!batch || typeof batch !== "object" ||
      batch.schema !== "smartploy.pending_questions.v1" ||
      !/^kit-[a-f0-9]{30}$/.test(batch.workspace_id || "") ||
      !Number.isInteger(batch.expected_revision) || batch.expected_revision < 1 ||
      !hex.test(batch.expected_document_sha256 || "") ||
      !hex.test(batch.expected_cv_pdf_sha256 || "") ||
      !hex.test(batch.expected_fields_sha256 || "") ||
      !hex.test(batch.expected_application_url_sha256 || "") ||
      !Number.isInteger(batch.expected_cv_pdf_size) ||
      batch.expected_cv_pdf_size < 12 || batch.expected_cv_pdf_size > 2 * 1024 * 1024 ||
      !Number.isFinite(batch.expires_at) || batch.expires_at <= Date.now() ||
      batch.expires_at > Date.now() + 5 * 60 * 1000 ||
      !Array.isArray(batch.questions) || batch.questions.length < 1 ||
      batch.questions.length > 12 ||
      batch.questions.some(q => !q || typeof q !== "object" ||
        typeof q.label !== "string" || q.label.trim().length < 3 ||
        q.label.length > 150 ||
        ["expected_id", "expected_name", "expected_placeholder"].some(k =>
          typeof q[k] !== "string" || q[k].length > 150))) {
    return { synced: false, reason: "invalid_or_expired_handoff" };
  }
  const options = {
    credentials: "same-origin", cache: "no-store", redirect: "error",
    headers: { Accept: "application/json" },
  };
  try {
    const sessionResponse = await fetch("/api/v1/session", { ...options, method: "GET" });
    if (!sessionResponse.ok) return { synced: false, reason: "sign_in_required" };
    const session = await sessionResponse.json();
    if (session.authenticated !== true || session.auth_source !== "oidc" ||
        typeof session.user_id !== "string" ||
        !/^usr-[A-Za-z0-9_-]{8,128}$/.test(session.user_id)) {
      return { synced: false, reason: "sign_in_required" };
    }
    // Reuse the SAME first-party exact document/field review gate as the
    // existing Chrome packet verification. A random or stale workspace alone
    // cannot inject question memory into another signed-in profile.
    const reviewResponse = await fetch(
      "/api/v1/application-workspaces/" +
        encodeURIComponent(batch.workspace_id) + "/verify-reviewed-packet",
      {
        ...options, method: "POST",
        headers: {
          ...options.headers, "Content-Type": "application/json",
          "X-Smartploy-Expected-User-Id": session.user_id,
        },
        body: JSON.stringify({
          expected_revision: batch.expected_revision,
          expected_document_sha256: batch.expected_document_sha256,
          expected_cv_pdf_sha256: batch.expected_cv_pdf_sha256,
          expected_fields_sha256: batch.expected_fields_sha256,
          expected_application_url_sha256: batch.expected_application_url_sha256,
          expected_cv_pdf_size: batch.expected_cv_pdf_size,
        }),
      },
    );
    if (!reviewResponse.ok) {
      return { synced: false, reason: "review_expired_or_changed" };
    }
    const review = await reviewResponse.json();
    if (review.review_verified !== true || review.review_state !== "pending" ||
        review.automatic_employer_submit_authorized !== false ||
        review.browser_grant_issued !== false ||
        review.external_actions_performed !== false) {
      return { synced: false, reason: "review_not_authorized" };
    }

    const settingsResponse = await fetch("/api/v1/profile/application-questions",
      { ...options, method: "GET" });
    if (!settingsResponse.ok) {
      return { synced: false, reason: "profile_unavailable" };
    }
    const settings = await settingsResponse.json();
    if (settings.mode === "cv_only") {
      return { synced: false, reason: "cv_only", profile_mode: "cv_only" };
    }
    if (settings.mode !== "guided") {
      return { synced: false, reason: "profile_unavailable" };
    }

    // A changed OIDC account cannot borrow an earlier session read; the
    // owner-specific expected-user header must still match the active cookie.
    const response = await fetch("/api/v1/profile/application-questions/observe", {
      ...options, method: "POST",
      headers: {
        ...options.headers, "Content-Type": "application/json",
        "X-Smartploy-Expected-User-Id": session.user_id,
      },
      body: JSON.stringify({
        workspace_id: batch.workspace_id,
        expected_revision: batch.expected_revision,
        questions: batch.questions,
      }),
    });
    if (!response.ok) {
      return { synced: false, reason: response.status === 409
        ? "workspace_changed" : "profile_write_unavailable" };
    }
    const saved = await response.json();
    if (saved.profile_mode === "cv_only") {
      return { synced: false, reason: "cv_only", profile_mode: "cv_only" };
    }
    if (!Array.isArray(saved.questions) ||
        !Number.isInteger(saved.remembered_count) ||
        saved.remembered_count !== saved.questions.length ||
        saved.remembered_count > batch.questions.length ||
        saved.answers_inferred_from_cv !== 0 ||
        saved.employer_actions_performed !== 0) {
      return { synced: false, reason: "unverified_profile_response" };
    }
    return {
      synced: true, remembered_count: saved.remembered_count,
      skipped: Number.isInteger(saved.skipped_sensitive_or_duplicate)
        ? saved.skipped_sensitive_or_duplicate : 0,
      answers_inferred_from_cv: 0, employer_actions_performed: 0,
    };
  } catch {
    return { synced: false, reason: "connection_or_identity_uncertain" };
  }
}
