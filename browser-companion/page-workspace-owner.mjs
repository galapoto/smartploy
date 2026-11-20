/* Exact owner-only first-party workspace probe. Chrome injects this standalone
 * function ONLY into a trusted SmartPloy tab, never an employer origin.
 * No uploads, writes, token export, or browser-submit side effects.
 */
/** Isolated-world READ-ONLY owner check, usable even AFTER a claimed final
 * employer attempt when a previous pending review may no longer exist.
 * Return one boolean, never the account, job details, document or session.
 */
export async function inspectOwnWorkspaceOnSmartPloy(spec) {
  const denied=()=>({owner_verified:false});
  if (!spec || typeof spec !== "object" ||
      !/^kit-[a-f0-9]{30}$/.test(spec.workspace_id || "") ||
      !Number.isInteger(spec.revision) || spec.revision < 1 ||
      typeof spec.application_url !== "string" ||
      spec.application_url.length < 14 || spec.application_url.length > 1500 ||
      !["https://smartploy.komplyint.fi",
        "https://smartploy.obumai.com"].includes(location.origin) ||
      location.protocol !== "https:" ||
      window.top !== window.self) return denied();
  try {
    const options={
      credentials:"same-origin",cache:"no-store",redirect:"error",
      headers:{"Accept":"application/json"}
    };
    const session=await fetch("/api/v1/session",options);
    if (!session.ok) return denied();
    const account=await session.json();
    if (account.authenticated !== true || account.auth_source !== "oidc")
      return denied();
    // The existing backend GET enforces tenant ownership. Never infer
    // ownership from a matching domain or a packet supplied by the popup.
    const response=await fetch(
      "/api/v1/application-workspaces/"+
        encodeURIComponent(spec.workspace_id),options
    );
    if (!response.ok) return denied();
    const workspace=(await response.json())?.workspace;
    return {owner_verified:
      workspace?.workspace_id === spec.workspace_id &&
      workspace?.revision === spec.revision &&
      workspace?.application_url === spec.application_url
    };
  } catch { return denied(); }
}

