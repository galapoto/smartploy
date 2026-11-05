import type { BrowserReceiptImport } from "./types";
/** SP111–SP112: explicit, applicant-local Playwright bridge transport.
 * Uses existing same-origin SmartPloy saved-CV GET only on separate user
 * consent. Never proxies employer/browser activity via SmartPloy's server.
 * No hidden remote browser, cookies to localhost or redirects.
 * A production HTTPS app may be refused local-network access by the browser:
 * that refusal is a blocker, never a reason to forward data elsewhere.
 */
const BRIDGE_ORIGIN = "http://127.0.0.1:48741";
const ALLOWED_PAGE_ORIGINS = new Set([
  "https://smartploy.komplyint.fi",
  "https://smartploy.obumai.com",
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
  cv_attachment: { available: boolean; label: string; attach_id: string };
  submitted: false; uploaded: false;
};
export type LocalBridgeFilled = {
  ok: true; stage: "filled"; filled: number; planned: number;
  stopped_on_change: boolean; submitted: false; uploaded: false;
};
export type LocalBridgeAttached = {
  ok: true; stage: "attached"; attached_locally: true;
  employer_upload_confirmed: false; submitted: false; uploaded: true;
};
/** SP113 observation is NOT an employer acknowledgement or send grant. */
/** SP114: original Chrome question rules, not generated model answers.
 * Applicant must type truthful answers and approve a one-time form fill.
 */
export type LocalReviewedQuestion = {
  index: number;
  label: string;
  type: "text" | "textarea";
  expected_id: string;
  expected_name: string;
  expected_placeholder: string;
  expected_max_length: number;
  max_answer_length: number;
};
export type LocalQuestionsInspected = {
  ok: true; stage: "questions_inspected"; plan_id: string;
  questions: LocalReviewedQuestion[]; human_only: string[];
  submitted: false; uploaded: false;
};
export type LocalAnswersFilled = {
  ok: true; stage: "answers_filled";
  status: "filled_for_review" | "partial_needs_review" | "blocked";
  filled: number; planned: number;
  submitted: false; uploaded: false;
};
export type LocalBridgeObserved = {
  ok: true; stage: "observed";
  confirmed: boolean; receipt: BrowserReceiptImport | null;
  employer_acknowledged: false;
  submitted: false; uploaded: false;
};
export type LocalBridgeStopped = {
  ok: true; stage: "stopped"; submitted: false; uploaded: false;
};
type BridgeStage = "opened" | "inspected" | "filled" | "questions_inspected" | "answers_filled" | "observed" | "stopped";
type BridgeResult = LocalBridgeOpened | LocalBridgeInspected | LocalBridgeFilled | LocalQuestionsInspected | LocalAnswersFilled | LocalBridgeObserved | LocalBridgeStopped;

export function localBridgeOriginAllowed(origin: string): boolean {
  return ALLOWED_PAGE_ORIGINS.has(origin);
}

export async function callLocalPlaywrightBridge<T extends BridgeResult>(
  route: "prepare" | "inspect" | "fill" | "questions" | "fill-questions" | "observe" | "stop",
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
    const requestInit: RequestInit & { targetAddressSpace: "loopback" } = {
      method: "POST",
      // Chromium Local Network Access: loopback identity, mixed-content
      // exemption and user permission prompt. Older browsers ignore this.
      targetAddressSpace: "loopback",
      mode: "cors",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
      cache: "no-store",
      headers,
      body: JSON.stringify(payload),
    };
    response = await fetch(BRIDGE_ORIGIN + "/v1/" + route, requestInit);
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
    !body.cv_attachment || typeof body.cv_attachment !== "object" ||
    (body.cv_attachment as Record<string, unknown>).available !== true &&
      (body.cv_attachment as Record<string, unknown>).available !== false ||
    typeof (body.cv_attachment as Record<string, unknown>).label !== "string" ||
    ((body.cv_attachment as Record<string, unknown>).label as string).length > 100 ||
    typeof (body.cv_attachment as Record<string, unknown>).attach_id !== "string" ||
    ((body.cv_attachment as Record<string, unknown>).available === true &&
      !/^[A-Za-z0-9_-]{16,100}$/.test(
        (body.cv_attachment as Record<string, unknown>).attach_id as string)) ||
    ((body.cv_attachment as Record<string, unknown>).available === false &&
      (body.cv_attachment as Record<string, unknown>).attach_id !== "") ||
    body.approved_fields.some((field) => (
      !field || typeof field.key !== "string" ||
      !/^[a-z_]{2,40}$/.test(field.key) ||
      typeof field.label !== "string" || field.label.length > 100
    ))
  )) throw new Error("Unsafe or invalid local form preview.");
  // The server only imports this independently via the original signed-in
  // owner-scoped API after a second applicant approval. Browser observation
  // must never become "submitted" or provider-acknowledged by type coercion.
  if (route === "observe") {
    if (body.employer_acknowledged !== false ||
        typeof body.confirmed !== "boolean" ||
        (body.confirmed === false && body.receipt !== null) ||
        (body.confirmed === true && (
          !body.receipt || typeof body.receipt !== "object" ||
          Object.keys(body.receipt as object).sort().join("|") !== [
            "application_url", "confirmation_page_sha256", "confirmation_page_url",
            "confirmed_visible", "document_revision", "document_sha256",
            "observed_at", "reference", "schema", "workspace_id"
          ].sort().join("|")
        ))) {
      throw new Error("The local browser did not provide a bounded, unverified receipt.");
    }
    if (body.confirmed) {
      const r = body.receipt as Record<string, unknown>;
      if (r.schema !== "smartploy.browser_receipt.v1" ||
          r.confirmed_visible !== true ||
          typeof r.workspace_id !== "string" ||
          !/^kit-[a-f0-9]{30}$/.test(r.workspace_id) ||
          !Number.isSafeInteger(r.document_revision) ||
          (r.document_revision as number) < 1 ||
          typeof r.document_sha256 !== "string" ||
          !/^[a-f0-9]{64}$/.test(r.document_sha256) ||
          typeof r.application_url !== "string" ||
          typeof r.confirmation_page_url !== "string" ||
          typeof r.reference !== "string" ||
          !/^[A-Za-z0-9][A-Za-z0-9._/-]{3,63}$/.test(r.reference) ||
          typeof r.confirmation_page_sha256 !== "string" ||
          !/^[a-f0-9]{64}$/.test(r.confirmation_page_sha256) ||
          typeof r.observed_at !== "string" ||
          !Number.isFinite(Date.parse(r.observed_at))) {
        throw new Error("The visible receipt's job, reference or evidence format is invalid.");
      }
      let actual: URL;
      let employer: URL;
      try {
        actual = new URL(r.confirmation_page_url as string);
        employer = new URL(r.application_url as string);
      } catch {
        throw new Error("The employer confirmation URL is invalid.");
      }
      const greenhouseHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io"];
      if (actual.protocol !== "https:" || employer.protocol !== "https:" ||
          actual.username || actual.password || employer.username || employer.password ||
          actual.search || actual.hash || actual.port || employer.search || employer.hash ||
          employer.port || (actual.origin !== employer.origin &&
          !(greenhouseHosts.includes(actual.hostname) &&
            greenhouseHosts.includes(employer.hostname)))) {
        throw new Error("The employer confirmation belongs to another origin.");
      }
    }
  }
  if (route === "questions") {
    if (!/^[A-Za-z0-9_-]{16,100}$/.test(String(body.plan_id || "")) ||
        !Array.isArray(body.questions) || body.questions.length > 12 ||
        !Array.isArray(body.human_only) || body.human_only.length > 250 ||
        body.human_only.some(item => typeof item !== "string" ||
          !item.length || item.length > 150) ||
        body.questions.some(q => {
          if (!q || typeof q !== "object") return true;
          const item = q as Record<string, unknown>;
          return !Number.isSafeInteger(item.index) ||
            (item.index as number) < 0 || (item.index as number) >= 250 ||
            typeof item.label !== "string" ||
            !item.label.length || item.label.length > 150 ||
            (item.type !== "text" && item.type !== "textarea") ||
            ["expected_id", "expected_name", "expected_placeholder"].some(key =>
              typeof item[key] !== "string" ||
              (item[key] as string).length > 150
            ) ||
            !Number.isSafeInteger(item.expected_max_length) ||
            !Number.isSafeInteger(item.max_answer_length) ||
            (item.max_answer_length as number) < 2 ||
            (item.max_answer_length as number) > 1500;
        })
    ) throw new Error("Invalid employer question review; complete manually.");
  }
  if (route === "fill-questions" && (
    !["filled_for_review", "partial_needs_review", "blocked"].includes(
      String(body.status || "")) ||
    !Number.isSafeInteger(body.filled) || !Number.isSafeInteger(body.planned) ||
    (body.filled as number) < 0 || (body.planned as number) < 0 ||
    (body.planned as number) > 12 ||
    (body.filled as number) > (body.planned as number)
  )) throw new Error("Uncertain employer answer result; inspect manually.");
  if (route === "fill" && (
    !Number.isSafeInteger(body.filled) ||
    !Number.isSafeInteger(body.planned) ||
    (body.filled as number) < 0 || (body.planned as number) < 0 ||
    (body.filled as number) > (body.planned as number) ||
    body.stopped_on_change !== ((body.filled as number) !== (body.planned as number))
  )) throw new Error("Local form-fill result could not be verified.");
  return body as T;
}


/** Reuse SmartPloy's server-side revision-locked CV PDF output and the
 * Chrome companion's exact SHA/size checks. The CV remains in applicant
 * browser memory and is never sent to a SmartPloy browser-proxy service.
 */
export async function fetchExactReviewedCvPdf(
  path: string, reviewed: { cv_pdf_sha256: string; cv_pdf_size: number }
): Promise<ArrayBuffer> {
  if (!localBridgeOriginAllowed(window.location.origin) ||
      !/^[a-f0-9]{64}$/.test(reviewed.cv_pdf_sha256) ||
      !Number.isSafeInteger(reviewed.cv_pdf_size) ||
      reviewed.cv_pdf_size < 12 || reviewed.cv_pdf_size > 2 * 1024 * 1024) {
    throw new Error("Invalid reviewed PDF identity.");
  }
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin ||
      !url.pathname.includes("/application-workspaces/") ||
      !url.pathname.endsWith("/download/cv/pdf")) {
    throw new Error("Only the current SmartPloy saved CV PDF can be attached.");
  }
  const response = await fetch(url.pathname + url.search, {
    method: "GET", mode: "same-origin", credentials: "same-origin",
    redirect: "error", cache: "no-store", referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new Error("Could not fetch the current saved CV PDF.");
  const contentLength = response.headers.get("content-length");
  if (contentLength && Number(contentLength) > 2 * 1024 * 1024) {
    throw new Error("CV PDF exceeds the approved size limit.");
  }
  const data = await response.arrayBuffer();
  if (data.byteLength !== reviewed.cv_pdf_size ||
      data.byteLength < 12 || data.byteLength > 2 * 1024 * 1024) {
    throw new Error("Saved CV PDF size changed; review and export it again.");
  }
  const bytes = new Uint8Array(data);
  if (String.fromCharCode(...bytes.subarray(0, 5)) !== "%PDF-") {
    throw new Error("Saved document is not a valid PDF.");
  }
  const tail = bytes.subarray(Math.max(0, bytes.length - 2048));
  let trailer = "";
  for (const item of tail) trailer += String.fromCharCode(item);
  if (!trailer.includes("%%EOF")) throw new Error("The saved CV PDF is incomplete.");
  if (!window.crypto?.subtle) throw new Error("Secure SHA-256 verification is unavailable.");
  const digest = Array.from(new Uint8Array(await window.crypto.subtle.digest(
    "SHA-256", data,
  ))).map(byte => byte.toString(16).padStart(2, "0")).join("");
  if (digest !== reviewed.cv_pdf_sha256) {
    throw new Error("Saved CV PDF digest changed; upload blocked.");
  }
  return data;
}

/** The ONLY direct PDF upload path: one explicit applicant gesture,
 * one exact locally reviewed input, no employer Submit or background retry.
 * Server validates packet SHA again and burns the attempt before Playwright
 * sets the employer file input (which may auto-upload immediately).
 */
export async function attachExactReviewedCvLocally(
  pdf: ArrayBuffer, token: string, attachId: string
): Promise<LocalBridgeAttached> {
  if (!localBridgeOriginAllowed(window.location.origin) ||
      !/^[A-Za-z0-9_-]{40,100}$/.test(token) ||
      !/^[A-Za-z0-9_-]{16,100}$/.test(attachId) ||
      pdf.byteLength < 12 || pdf.byteLength > 2 * 1024 * 1024) {
    throw new Error("Invalid reviewed local CV attachment request.");
  }
  let response: Response;
  try {
    const requestInit: RequestInit & { targetAddressSpace: "loopback" } = {
      method: "POST", mode: "cors", targetAddressSpace: "loopback",
      credentials: "omit", redirect: "error", cache: "no-store",
      referrerPolicy: "no-referrer",
      headers: {
        "Content-Type": "application/pdf",
        "Authorization": "Bearer " + token,
        "X-Smartploy-Attach-Id": attachId,
        "X-Smartploy-Attach-Confirmation": "ATTACH REVIEWED CV",
      },
      body: pdf,
    };
    response = await fetch(BRIDGE_ORIGIN + "/v1/attach", requestInit);
  } catch {
    throw new Error("Local PDF transfer uncertain. Inspect the employer browser; never retry blindly.");
  }
  let data: unknown;
  try { data = await response.json(); }
  catch { throw new Error("Uncertain CV attachment response. Inspect the employer browser manually."); }
  if (!data || typeof data !== "object") {
    throw new Error("Unknown local attachment result; inspect employer browser.");
  }
  const body = data as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(typeof body.error === "string" && body.error.length <= 300
      ? body.error : "The local helper refused the reviewed PDF.");
  }
  if (body.ok !== true || body.stage !== "attached" ||
      body.attached_locally !== true || body.uploaded !== true ||
      body.submitted !== false || body.employer_upload_confirmed !== false) {
    throw new Error("Unexpected attachment response. Inspect employer browser; do not retry.");
  }
  return body as LocalBridgeAttached;
}
