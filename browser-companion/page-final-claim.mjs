/* SP26: single signed-in first-party transaction that reserves a sticky
   cross-device employer attempt. Serialized via chrome.scripting.executeScript
   into the current SmartPloy tab, never into an employer tab. No cookies,
   access tokens, CV or provider credentials are returned to Chrome. */
export async function reserveFinalClickOnSmartPloy(requested) {
  const allowedOrigins = [
    "https://smartploy.komplyint.fi", "https://smartploy.obumai.com",
  ];
  if (!allowedOrigins.includes(location.origin) || location.protocol !== "https:" ||
      (typeof window !== "undefined" && window.top !== window.self)) {
    return {claim_reserved: false, reason: "wrong_origin"};
  }
  if (!requested || typeof requested !== "object" ||
      !/^kit-[a-f0-9]{30}$/.test(requested.workspace_id) ||
      !Number.isInteger(requested.expected_revision) ||
      requested.expected_revision < 1 ||
      !/^[a-f0-9]{64}$/.test(requested.expected_document_sha256) ||
      !/^[a-f0-9]{64}$/.test(requested.expected_cv_pdf_sha256) ||
      !/^[a-f0-9]{64}$/.test(requested.expected_fields_sha256) ||
      !/^[a-f0-9]{64}$/.test(requested.expected_application_url_sha256) ||
      !Number.isInteger(requested.expected_cv_pdf_size) ||
      requested.expected_cv_pdf_size < 12 ||
      requested.expected_cv_pdf_size > 2 * 1024 * 1024 ||
      requested.confirm_one_job_final_click !== true ||
      requested.acknowledge_external_employer_transfer !== true ||
      requested.acknowledge_no_automatic_retry !== true) {
    return {claim_reserved: false, reason: "invalid_binding"};
  }
  try {
    const sessionResponse = await fetch("/api/v1/session", {
      method: "GET", credentials: "same-origin", cache: "no-store",
      redirect: "error", headers: {"Accept": "application/json"},
    });
    if (!sessionResponse.ok) {
      return {claim_reserved: false, reason: "sign_in_required"};
    }
    const session = await sessionResponse.json();
    if (session.authenticated !== true || session.auth_source !== "oidc" ||
        typeof session.user_id !== "string" ||
        !/^usr-[A-Za-z0-9_-]{8,128}$/.test(session.user_id)) {
      return {claim_reserved: false, reason: "sign_in_required"};
    }
    // Deliberately NO grant from a browser-local checkbox alone: the server
    // checks the original one-job review and two-person operator rights again
    // in its transaction, then consumes the one-use claim before this returns.
    const response = await fetch(
      "/api/v1/application-workspaces/" +
      encodeURIComponent(requested.workspace_id) + "/browser-final-attempt",
      {
        method: "POST", credentials: "same-origin", cache: "no-store",
        redirect: "error",
        headers: {
          "Accept": "application/json", "Content-Type": "application/json",
          "X-Smartploy-Expected-User-Id": session.user_id,
        },
        body: JSON.stringify({
          expected_revision: requested.expected_revision,
          expected_document_sha256: requested.expected_document_sha256,
          expected_cv_pdf_sha256: requested.expected_cv_pdf_sha256,
          expected_fields_sha256: requested.expected_fields_sha256,
          expected_application_url_sha256: requested.expected_application_url_sha256,
          expected_cv_pdf_size: requested.expected_cv_pdf_size,
          confirm_one_job_final_click: true,
          acknowledge_external_employer_transfer: true,
          acknowledge_no_automatic_retry: true,
        }),
      },
    );
    if (!response.ok) {
      return {
        claim_reserved: false,
        reason: response.status === 409 ? "review_or_permission_changed" :
          response.status === 403 ? "unavailable_or_not_authorized" :
          "outcome_uncertain_check_attempt_status",
      };
    }
    const item = await response.json();
    if (item.claim_reserved !== true ||
        !/^employer-claim-[a-f0-9]{32}$/.test(item.claim_id) ||
        typeof item.expires_at !== "string" ||
        item.external_actions_performed !== false ||
        item.provider_acknowledged !== false ||
        item.automatic_retry_authorized !== false ||
        item.one_job_browser_click_permitted !== true) {
      return {claim_reserved: false, reason: "invalid_server_response_check_attempt_status"};
    }
    return {
      claim_reserved: true,
      claim_id: item.claim_id,
      expires_at: item.expires_at,
      provider_acknowledged: false,
      external_actions_performed: false,
      automatic_retry_authorized: false,
    };
  } catch {
    // Server may already have committed a sticky claim. Never request it
    // again automatically; only manual operator reconciliation is safe.
    return {claim_reserved: false, reason: "outcome_uncertain_check_attempt_status"};
  }
}
