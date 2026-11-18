/* Strict first-party, signed-in, READ-ONLY browser final-action readiness.
   Runs only inside the user's own SmartPloy tab. The popup and employer
   tab never fetch an applicant session, issue authorization or send a job.
*/
export async function readOneJobFinalActionReadinessOnSmartPloy(workspaceId) {
  const denied=(reason)=>({ready:false,reason});
  if (!/^kit-[0-9a-f]{30}$/.test(workspaceId || "") ||
      !["https://smartploy.komplyint.fi",
        "https://smartploy.obumai.com"].includes(location.origin) ||
      location.protocol!=="https:" ||
      window.top!==window.self) {
    return denied("untrusted_account_context");
  }
  try {
    const options={
      credentials:"same-origin",cache:"no-store",redirect:"error",
      headers:{"Accept":"application/json"}
    };
    const session=await fetch("/api/v1/session",options);
    if(!session.ok) return denied("sign_in_required");
    const account=await session.json();
    if(account.authenticated!==true || account.auth_source!=="oidc") {
      return denied("sign_in_required");
    }
    const response=await fetch(
      "/api/v1/application-workspaces/"+encodeURIComponent(workspaceId)+
      "/final-action-readiness",options
    );
    if(!response.ok) return denied("readiness_unavailable");
    const data=await response.json();
    const permitted=data?.operator_permission_reviewed===true;
    const enabled=data?.trusted_one_use_browser_redemption_available===true;
    // A popup's local JS state resets when closed. The account-owned source
    // of truth survives that reset and can never be treated as a new job.
    const previous=data?.previous_employer_attempt_reserved===true;
    return {
      ready:permitted && enabled && !previous,
      previous_employer_attempt_reserved:previous,
      reason:previous?"previous_employer_attempt_reserved" :
        !permitted?"employer_permission_not_approved" :
        !enabled?"browser_final_click_disabled":"ready"
    };
  } catch {
    return denied("readiness_unavailable");
  }
}
