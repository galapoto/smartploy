/* One verified, reference-bearing employer confirmation -> signed-in SmartPloy.
   Runs ONLY in the user's existing authenticated first-party browser tab.
   It does NOT submit to employers. No cookies, tokens or full CV leave the tab.
   User confirms the actual receipt before this is invoked. The backend
   independently validates owner/workspace/job/documents/URL and freezes it.
*/
export async function saveOneObservedReceiptOnSmartPloy(requested) {
  const allowed = [
    "https://smartploy.komplyint.fi", "https://smartploy.obumai.com"
  ];
  if (!allowed.includes(location.origin) || location.protocol !== "https:" ||
      (typeof window !== "undefined" && window.top !== window.self) ||
      !requested || typeof requested !== "object" ||
      !/^kit-[a-f0-9]{30}$/.test(requested.workspace_id || "") ||
      !requested.receipt || typeof requested.receipt !== "object" ||
      requested.receipt.workspace_id !== requested.workspace_id ||
      requested.receipt.confirmed_visible !== true ||
      typeof requested.receipt.reference !== "string" ||
      requested.receipt.reference.length < 3 ||
      requested.receipt.reference.length > 250 ||
      requested.confirm_user_observed !== true) {
    return {saved:false,reason:"invalid_visible_receipt_binding"};
  }
  try {
    const sessionRes = await fetch("/api/v1/session", {
      credentials:"same-origin",cache:"no-store",redirect:"error",
      headers:{"Accept":"application/json"}
    });
    if (!sessionRes.ok) return {saved:false,reason:"sign_in_required"};
    const session = await sessionRes.json();
    if (session.authenticated !== true || session.auth_source !== "oidc" ||
        typeof session.user_id !== "string" ||
        !/^usr-[A-Za-z0-9_-]{8,128}$/.test(session.user_id)) {
      return {saved:false,reason:"sign_in_required"};
    }
    const response = await fetch(
      "/api/v1/application-workspaces/" +
      encodeURIComponent(requested.workspace_id) + "/browser-receipt",{
        method:"POST",credentials:"same-origin",cache:"no-store",redirect:"error",
        headers:{"Accept":"application/json","Content-Type":"application/json",
          "X-Smartploy-Expected-User-Id":session.user_id},
        body:JSON.stringify({
          confirm_user_observed:true,receipt:requested.receipt
        })
      }
    );
    if (!response.ok) {
      return {saved:false,reason:response.status === 409 ?
        "receipt_already_recorded_check_application" :
        "receipt_not_saved_check_application"};
    }
    const payload=await response.json();
    if (!payload?.receipt || payload.external_confirmation_verified !== false ||
        payload.receipt.workspace_id !== requested.workspace_id) {
      return {saved:false,reason:"receipt_save_result_uncertain_check_application"};
    }
    return {saved:true,reference:requested.receipt.reference,
      external_confirmation_verified:false,record_state:"browser_observed"};
  } catch {
    return {saved:false,reason:"receipt_outcome_uncertain_check_application_no_retry"};
  }
}
