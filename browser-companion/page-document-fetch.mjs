/* SmartPloy first-party PDF bridge. Injected ONLY into a signed-in
   SmartPloy tab after the user has explicitly started the exact job.
   No third-party request, no persistent storage, no token/cookie extraction.
   It fetches the SAME account's already rendered and reviewed PDF.
   The calling popup verifies the exact employer URL again before upload.
*/
export async function readOwnReviewedPdf(spec) {
  const blocked = reason => ({ready:false,reason});
  if (location.origin !== "https://smartploy.komplyint.fi" ||
      window.top !== window.self || !spec ||
      !/^kit-[0-9a-f]{30}$/.test(spec.workspace_id || "") ||
      !["cv","letter"].includes(spec.kind) ||
      !/^[a-f0-9]{64}$/.test(spec.sha256 || "") ||
      !Number.isInteger(spec.size) || spec.size < 12 ||
      spec.size > 2 * 1024 * 1024) {
    return blocked("The signed-in SmartPloy document request is not valid.");
  }
  try {
    const session = await fetch("/api/v1/session", {
      credentials:"same-origin",cache:"no-store",redirect:"error"
    });
    if (!session.ok || (await session.json())?.authenticated !== true) {
      return blocked("Sign in to your SmartPloy account again.");
    }
    const resource = "/api/v1/application-workspaces/" +
      encodeURIComponent(spec.workspace_id) + "/download/" + spec.kind + "/pdf";
    const response = await fetch(resource, {
      credentials:"same-origin",cache:"no-store",redirect:"error"
    });
    if (!response.ok || !String(response.headers.get("content-type") || "")
        .toLowerCase().startsWith("application/pdf")) {
      return blocked("Current reviewed PDF is unavailable in this signed-in account.");
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length !== spec.size || bytes.length > 2 * 1024 * 1024 ||
        String.fromCharCode(...bytes.subarray(0,5)) !== "%PDF-") {
      return blocked("The generated PDF differs from the approved document size.");
    }
    const suffix = bytes.subarray(Math.max(0,bytes.length-2048));
    let tail="";
    for (const b of suffix) tail += String.fromCharCode(b);
    if (!tail.includes("%%EOF")) return blocked("The PDF is incomplete.");
    const hash = new Uint8Array(await crypto.subtle.digest("SHA-256",bytes));
    const digest = Array.from(hash, b=>b.toString(16).padStart(2,"0")).join("");
    if (digest !== spec.sha256) {
      return blocked("The saved document changed; review and generate a new packet.");
    }
    const chunks=[];
    for(let i=0;i<bytes.length;i+=8192){
      chunks.push(String.fromCharCode(...bytes.subarray(i,i+8192)));
    }
    return {
      ready:true, kind:spec.kind, sha256:digest, size:bytes.length,
      filename:spec.kind==="cv" ? "SmartPloy-CV.pdf" : "SmartPloy-Cover-Letter.pdf",
      base64:btoa(chunks.join(""))
    };
  } catch {
    return blocked("Cannot securely read the saved SmartPloy PDF. Download and attach it manually.");
  }
}
