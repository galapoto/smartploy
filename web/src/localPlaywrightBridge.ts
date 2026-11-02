/** SP111: explicit, applicant-local Playwright bridge transport.
 * No SmartPloy API/proxy, hidden remote browser, cookies or redirects.
 * A production HTTPS app may be refused local-network access by the browser:
 * that refusal is a blocker, never a reason to forward data elsewhere.
 */
const BRIDGE_ORIGIN = "http://127.0.0.1:48741";
const ALLOWED_PAGE_ORIGINS = new Set([
  "https://smartploy.komplyint.fi",
  "https://smartploy.obumai.com",
  "http://127.0.0.1:4173",
  "http://localhost:4173",
]);

export type LocalBridgeField = { key: string; label: string };
export type LocalBridgeOpened = {
  ok: true; stage: "opened"; token: string;
  company: string; role_title: string;
  submitted: false; uploaded: false;
};
export type LocalBridgeInspected = {
  ok: true; stage: "inspected"; plan_id: string;
  total_controls: number; approved_fields: LocalBridgeField[];
  submitted: false; uploaded: false;
};
export type LocalBridgeFilled = {
  ok: true; stage: "filled"; filled: number; planned: number;
  stopped_on_change: boolean; submitted: false; uploaded: false;
};
export type LocalBridgeStopped = {
  ok: true; stage: "stopped"; submitted: false; uploaded: false;
};
type BridgeStage = "opened" | "inspected" | "filled" | "stopped";
type BridgeResult = LocalBridgeOpened | LocalBridgeInspected | LocalBridgeFilled | LocalBridgeStopped;

export function localBridgeOriginAllowed(origin: string): boolean {
  return ALLOWED_PAGE_ORIGINS.has(origin);
}

export async function callLocalPlaywrightBridge<T extends BridgeResult>(
  route: "prepare" | "inspect" | "fill" | "stop",
  payload: Record<string, unknown>,
  options: { token?: string; expectedStage: BridgeStage }
): Promise<T> {
  if (!localBridgeOriginAllowed(window.location.origin)) {
    throw new Error("Local Playwright connection is allowed only from an approved SmartPloy origin.");
  }
  if (options.token && !/^[A-Za-z0-9_-]{40,100}$/.test(options.token)) {
    throw new Error("Invalid local browser session. Restart the helper.");
  }
  if (route !== "prepare" && !options.token) {
    throw new Error("Pair your local browser before sending an action.");
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers.Authorization = "Bearer " + options.token;
  let response: Response;
  try {
    response = await fetch(BRIDGE_ORIGIN + "/v1/" + route, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
      cache: "no-store",
      headers,
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("Local helper unavailable or local-network permission denied. " +
      "Run python bridge.py on this computer, allow localhost access, or use the Chrome companion.");
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error("Untrusted or invalid response from the local Playwright helper.");
  }
  if (!data || typeof data !== "object") {
    throw new Error("Invalid local Playwright response.");
  }
  const body = data as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(
      typeof body.error === "string" && body.error.length <= 300
        ? body.error : "The local Playwright helper refused this action."
    );
  }
  if (
    body.ok !== true || body.stage !== options.expectedStage
    || body.submitted !== false || body.uploaded !== false
  ) {
    throw new Error("Local browser response failed the review-only safety contract.");
  }
  // Never allow unbounded or forged fields to become an actionable preview.
  if (route === "prepare" && (
    typeof body.token !== "string" ||
    !/^[A-Za-z0-9_-]{40,100}$/.test(body.token)
  )) throw new Error("Local pairing did not return a valid session.");
  if (route === "inspect" && (
    typeof body.plan_id !== "string" ||
    !/^[A-Za-z0-9_-]{16,100}$/.test(body.plan_id) ||
    !Array.isArray(body.approved_fields) || body.approved_fields.length > 250 ||
    body.approved_fields.some((field) => (
      !field || typeof field.key !== "string" ||
      !/^[a-z_]{2,40}$/.test(field.key) ||
      typeof field.label !== "string" || field.label.length > 100
    ))
  )) throw new Error("Unsafe or invalid local form preview.");
  if (route === "fill" && (
    !Number.isSafeInteger(body.filled) ||
    !Number.isSafeInteger(body.planned) ||
    (body.filled as number) < 0 || (body.planned as number) < 0 ||
    (body.filled as number) > (body.planned as number) ||
    body.stopped_on_change !== ((body.filled as number) !== (body.planned as number))
  )) throw new Error("Local form-fill result could not be verified.");
  return body as T;
}
