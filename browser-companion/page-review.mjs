/* Serialized by chrome.scripting.executeScript ONLY into a tab whose URL was
   independently verified to be the signed-in SmartPloy origin. This function
   is self-contained for Chrome's MV3 ISOLATED world. It does NOT inspect cookies,
   access employer pages or transfer a login token to the extension. */
export async function verifyReviewOnSmartPloy(requested) {
  const origin = "https://smartploy.obumai.com";
  if (location.origin !== origin || location.protocol !== "https:") {
    return {review_verified: false, reason: "wrong_origin"};
  }
  if (
    !requested || typeof requested !== "object" ||
    !/^kit-[a-f0-9]{30}$/.test(requested.workspace_id) ||
    !Number.isInteger(requested.expected_revision) ||
    requested.expected_revision < 1 ||
    !/^[a-f0-9]{64}$/.test(requested.expected_document_sha256) ||
    !/^[a-f0-9]{64}$/.test(requested.expected_cv_pdf_sha256) ||
    !/^[a-f0-9]{64}$/.test(requested.expected_fields_sha256) ||
    !/^[a-f0-9]{64}$/.test(requested.expected_application_url_sha256) ||
    !Number.isInteger(requested.expected_cv_pdf_size) ||
    requested.expected_cv_pdf_size < 12 ||
    requested.expected_cv_pdf_size > 2 * 1024 * 1024
  ) {
    return {review_verified: false, reason: "invalid_binding"};
  }
  try {
    // Runs with the website's origin, so Chrome's ordinary HttpOnly
    // SmartPloy cookie applies. Neither cookie nor account ID is returned.
    const sessionResponse = await fetch("/api/v1/session", {
      method: "GET", credentials: "same-origin", cache: "no-store",
      headers: {"Accept": "application/json"},
    });
    if (!sessionResponse.ok) {
      return {review_verified: false, reason: "sign_in_required"};
    }
    const session = await sessionResponse.json();
    if (session.authenticated !== true || session.auth_source !== "oidc" ||
        typeof session.user_id !== "string" ||
        !/^usr-[A-Za-z0-9_-]{8,128}$/.test(session.user_id)) {
      return {review_verified: false, reason: "sign_in_required"};
    }
    // Only hash/revision metadata of a reviewed packet moves to the user's
    // own SmartPloy endpoint. Same-origin Origin/Fetch-Metadata & the expected
    // account precondition are independently verified by the backend.
    const response = await fetch(
      "/api/v1/application-workspaces/" +
      encodeURIComponent(requested.workspace_id) + "/verify-reviewed-packet",
      {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {
          "Accept": "application/json", "Content-Type": "application/json",
          "X-Smartploy-Expected-User-Id": session.user_id
        },
        body: JSON.stringify({
          expected_revision: requested.expected_revision,
          expected_document_sha256: requested.expected_document_sha256,
          expected_cv_pdf_sha256: requested.expected_cv_pdf_sha256,
          expected_fields_sha256: requested.expected_fields_sha256,
          expected_application_url_sha256: requested.expected_application_url_sha256,
          expected_cv_pdf_size: requested.expected_cv_pdf_size
        }),
      }
    );
    if (!response.ok) {
      return {review_verified: false, reason:
        response.status === 409 ? "review_stale_or_missing" : "not_authorized"};
    }
    const verdict = await response.json();
    if (
      verdict.review_verified !== true || verdict.review_state !== "pending" ||
      verdict.automatic_employer_submit_authorized !== false ||
      verdict.browser_grant_issued !== false ||
      verdict.external_actions_performed !== false ||
      typeof verdict.expires_at !== "string"
    ) {
      return {review_verified: false, reason: "not_authorized"};
    }
    // Strictly non-bearer data for the MV3 popup. Never a final-click lease.
    return {
      review_verified: true, review_state: "pending",
      expires_at: verdict.expires_at,
      automatic_employer_submit_authorized: false,
      external_actions_performed: false,
      browser_grant_issued: false,
    };
  } catch {
    return {review_verified: false, reason: "smartploy_unreachable"};
  }
}
