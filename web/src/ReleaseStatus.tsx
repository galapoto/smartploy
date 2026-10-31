import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";

/**
 * The deployed browser code, static /release.json and API /healthz must agree.
 * This is release identity only: it does not certify employer submissions,
 * authenticated acceptance or that this is the newest GitHub commit.
 */
export type ReleaseParity =
  "checking" | "aligned" | "update_available" | "mixed" | "unverified" | "development";

const REVISION = /^[0-9a-f]{12}$/;
const MANIFEST_SCHEMA = "smartploy-web-release-v1";
const DEFAULT_BUILD_REVISION = import.meta.env.VITE_SMARTPLOY_BUILD_REVISION || "dev";

export function assessReleaseParity(
  buildRevision: string,
  apiRevision: string | undefined,
  webRevision: string | null | undefined,
): ReleaseParity {
  if (buildRevision === "dev") return "development";
  if (!REVISION.test(buildRevision) || !apiRevision || !REVISION.test(apiRevision)) {
    return "unverified";
  }
  if (webRevision === undefined) return "checking";
  if (!webRevision || !REVISION.test(webRevision)) return "unverified";
  if (buildRevision === webRevision && webRevision === apiRevision) return "aligned";
  if (webRevision === apiRevision && webRevision !== buildRevision) return "update_available";
  return "mixed";
}

async function readWebRevision(): Promise<string> {
  // Always same-origin, public metadata only. Never send CVs or private API data.
  const response = await fetch("/release.json", {
    method: "GET", cache: "no-store", credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok || response.redirected ||
      !response.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    throw new Error("RELEASE_MANIFEST_NOT_JSON");
  }
  const length = Number(response.headers.get("content-length") || 0);
  if (length > 4096) throw new Error("RELEASE_MANIFEST_TOO_LARGE");
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("RELEASE_MANIFEST_INVALID");
  }
  const manifest = payload as Record<string, unknown>;
  if (Object.keys(manifest).sort().join(",") !== "release_revision,schema" ||
      manifest.schema !== MANIFEST_SCHEMA ||
      typeof manifest.release_revision !== "string" ||
      (manifest.release_revision !== "dev" && !REVISION.test(manifest.release_revision))) {
    throw new Error("RELEASE_MANIFEST_INVALID");
  }
  return manifest.release_revision;
}

export default function ReleaseStatus(props: {
  apiRevision?: string;
  buildRevision?: string;
  onReload?: () => void;
}) {
  const buildRevision = props.buildRevision ?? DEFAULT_BUILD_REVISION;
  const [webRevision, setWebRevision] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const latest = await readWebRevision();
        if (active) setWebRevision(latest);
      } catch {
        if (active) setWebRevision(null);
      }
    };
    void check();
    const timer = window.setInterval(() => { void check(); }, 90_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [props.apiRevision]);

  const status = assessReleaseParity(buildRevision, props.apiRevision, webRevision);
  const reload = props.onReload || (() => window.location.reload());
  return <div className={"release-status release-status-" + status}
    role="status" aria-label="SmartPloy running release status">
    {status === "aligned" ? <>
      <CheckCircle2 size={15} aria-hidden="true" />
      <span>App version <code>{buildRevision}</code> · UI and API match</span>
    </> : status === "update_available" ? <>
      <RefreshCw size={16} aria-hidden="true" />
      <span><strong>Updated SmartPloy is available.</strong> Save any unsaved CV or letter changes before refreshing.</span>
      <button type="button" className="release-status-action" onClick={reload}>Reload updated app</button>
    </> : status === "mixed" ? <>
      <AlertTriangle size={16} aria-hidden="true" />
      <span>Release mismatch: the UI assets and server report different versions. Your latest features may not be visible yet.</span>
    </> : status === "unverified" ? <>
      <AlertTriangle size={16} aria-hidden="true" />
      <span>Running release cannot be verified. Some features may still be on an older version.</span>
    </> : status === "development" ? <>
      <span>Development preview · not a production release</span>
    </> : <>
      <span>Checking deployed app version…</span>
    </>}
  </div>;
}
