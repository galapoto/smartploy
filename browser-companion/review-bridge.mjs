/* SP15d - reuse existing packet validation and Chrome storage for a read-only
   SmartPloy-site verification. NO bearer credential, CV or browser submit. */
import { PacketError, validatePacket } from "./logic.mjs";

// Exact first-party allowlist. No caller-supplied origin, wildcard or redirect.
export const SMARTPLOY_ORIGIN = "https://smartploy.komplyint.fi";
export const SMARTPLOY_LEGACY_ORIGIN = "https://smartploy.obumai.com";
export const SMARTPLOY_REVIEW_ORIGINS = Object.freeze([
  SMARTPLOY_ORIGIN, SMARTPLOY_LEGACY_ORIGIN,
]);
export const REVIEW_SESSION_SECONDS = 5 * 60;

export function isSmartPloyTab(url) {
  try {
    const here = new URL(url);
    return SMARTPLOY_REVIEW_ORIGINS.includes(here.origin) &&
      !here.username && !here.password && here.port === "" &&
      here.protocol === "https:";
  } catch { return false; }
}

export function validateReviewPacket(source, now = Date.now()) {
  let item;
  try {
    if (typeof source === "string" && source.length > 40000)
      throw new PacketError("The application packet is too large");
    item = typeof source === "string" ? JSON.parse(source) : source;
  } catch (error) {
    if (error instanceof PacketError) throw error;
    throw new PacketError("Paste a reviewed SmartPloy browser packet first.");
  }
  // Reuse the exact existing packet, source-host, document and privacy gates.
  // The employer tab is not open yet, so validate against its own known URL.
  return validatePacket(item, item?.application_url, now);
}

const APPROVED_FIELD_NAMES = [
  "full_name", "first_name", "last_name", "email", "phone",
  "location", "linkedin", "github", "cover_letter"
];

export async function sha256Text(value) {
  if (typeof value !== "string") throw new PacketError("Text digest requires a string");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest))
    .map(n => n.toString(16).padStart(2,"0")).join("");
}

export async function approvedFieldsSha256(fields) {
  if (!fields || typeof fields !== "object" ||
      Object.keys(fields).length !== APPROVED_FIELD_NAMES.length ||
      APPROVED_FIELD_NAMES.some(k => typeof fields[k] !== "string")) {
    throw new PacketError("An exact approved contact/letter field set is required");
  }
  const pieces = APPROVED_FIELD_NAMES.map(k => {
    const value = fields[k];
    return String(new TextEncoder().encode(value).byteLength) + ":" + value;
  });
  return sha256Text("smartploy.fields.v1\0" + pieces.join("\0"));
}

export async function reviewSessionKey(packet) {
  const fields = [
    packet.workspace_id, String(packet.revision),
    packet.application_url, packet.document_sha256,
    packet.cv_pdf_sha256, String(packet.cv_pdf_size),
    await approvedFieldsSha256(packet.fields),
  ];
  if (fields.some(x => typeof x !== "string" || !x))
    throw new PacketError("Invalid reviewed packet binding");
  return "smartploy.review." +
    await sha256Text("smartploy.review.v1\0" + fields.join("\0"));
}

function sessionStorage(storage) {
  if (!storage || typeof storage.get !== "function" ||
      typeof storage.set !== "function") {
    throw new PacketError("Secure ephemeral Chrome session storage unavailable.");
  }
  return storage;
}

export async function recordVerifiedReview(storage, packet, result, now = Date.now()) {
  sessionStorage(storage);
  if (!result || result.review_verified !== true || result.review_state !== "pending" ||
      result.automatic_employer_submit_authorized !== false ||
      result.browser_grant_issued !== false ||
      result.external_actions_performed !== false) {
    throw new PacketError("SmartPloy did not verify this exact signed-in application review");
  }
  const expires = Date.parse(result.expires_at);
  const packetExpiry = Date.parse(packet.expires_at);
  if (!Number.isFinite(expires) || !Number.isFinite(packetExpiry) ||
      expires <= now || packetExpiry <= now ||
      expires > now + 10 * 60 * 1000 + 120000) {
    throw new PacketError("The signed-in review has expired or an invalid lifetime");
  }
  const until = Math.min(expires, packetExpiry, now + REVIEW_SESSION_SECONDS * 1000);
  if (until <= now) throw new PacketError("Review already expired");
  const key = await reviewSessionKey(packet);
  // Only an opaque key and expiry: never bearer credentials, names, answers,
  // original CV, tokens, employer URL, or raw packet in chrome.storage.
  await storage.set({ [key]: { marker: "signed-in-review-v1", expires_at: until } });
  return { expires_at: new Date(until).toISOString() };
}

export async function requireVerifiedReview(storage, packet, now = Date.now()) {
  sessionStorage(storage);
  const key = await reviewSessionKey(packet);
  const item = (await storage.get(key))[key];
  if (!item || item.marker !== "signed-in-review-v1" ||
      !Number.isFinite(item.expires_at) ||
      item.expires_at <= now || item.expires_at > now + REVIEW_SESSION_SECONDS * 1000) {
    throw new PacketError(
      "Verify this exact packet from your signed-in SmartPloy tab first. " +
      "Verification lasts up to five minutes and never authorizes final submission."
    );
  }
  return true;
}


/* SP26 browser final-click stamp. The server has ALREADY burned its sticky
   employer-job attempt before this arrives. This session marker is NOT a
   bearer key, cannot authorize server work or be transferred across devices.
   Final click requires this + local browser attempt marker + explicit UI
   confirmation, and always ends as an unverified employer outcome. */
export async function finalAttemptSessionKey(packet) {
  const original = await reviewSessionKey(packet);
  return original.replace(/^smartploy\.review\./, "smartploy.final.");
}

export async function recordOneUseFinalAttempt(storage, packet, result, now = Date.now()) {
  sessionStorage(storage);
  if (!result || result.claim_reserved !== true ||
      !/^employer-claim-[a-f0-9]{32}$/.test(result.claim_id || "") ||
      result.provider_acknowledged !== false ||
      result.external_actions_performed !== false ||
      result.automatic_retry_authorized !== false) {
    throw new PacketError(
      "Server final-action claim is missing or unverified. Check attempt status; do not retry."
    );
  }
  const expires = Date.parse(result.expires_at);
  if (!Number.isFinite(expires) || expires <= now ||
      expires > now + 90_000 + 120_000 ||
      Date.parse(packet.expires_at) <= now) {
    throw new PacketError(
      "Server final-action claim expired or untrusted. No employer click is permitted."
    );
  }
  await requireVerifiedReview(storage, packet, now);
  const key = await finalAttemptSessionKey(packet);
  if ((await storage.get(key))[key]) {
    throw new PacketError("A final employer attempt already exists in this browser session.");
  }
  const marker = {
    marker: "reserved-final-click-v1", claim_id: result.claim_id,
    expires_at: Math.min(expires, now + 90_000),
  };
  await storage.set({[key]: marker});
  if (JSON.stringify((await storage.get(key))[key]) !== JSON.stringify(marker)) {
    throw new PacketError("One-use browser claim was not durably stored. Never retry the server claim.");
  }
  return {expires_at: new Date(marker.expires_at).toISOString()};
}

export async function requireOneUseFinalAttempt(storage, packet, now = Date.now()) {
  sessionStorage(storage);
  await requireVerifiedReview(storage, packet, now);
  const key = await finalAttemptSessionKey(packet);
  const item = (await storage.get(key))[key];
  if (!item || item.marker !== "reserved-final-click-v1" ||
      !/^employer-claim-[a-f0-9]{32}$/.test(item.claim_id || "") ||
      !Number.isFinite(item.expires_at) ||
      item.expires_at <= now || item.expires_at > now + 90_000) {
    throw new PacketError(
      "No current one-use server claim for this exact job and CV. " +
      "Return to the signed-in SmartPloy tab or review the prior attempt."
    );
  }
  return true;
}

export async function consumeLocalFinalAttempt(storage, packet, now = Date.now()) {
  await requireOneUseFinalAttempt(storage, packet, now);
  const key = await finalAttemptSessionKey(packet);
  await storage.set({[key]: {marker: "consumed-final-click-v1"}});
  return true;
}
