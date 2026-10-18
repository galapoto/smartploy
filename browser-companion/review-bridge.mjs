/* SP15d - reuse existing packet validation and Chrome storage for a read-only
   SmartPloy-site verification. NO bearer credential, CV or browser submit. */
import { PacketError, validatePacket } from "./logic.mjs";

export const SMARTPLOY_ORIGIN = "https://smartploy.obumai.com";
export const REVIEW_SESSION_SECONDS = 5 * 60;

export function isSmartPloyTab(url) {
  try {
    const here = new URL(url);
    return here.origin === SMARTPLOY_ORIGIN && !here.username && !here.password &&
      here.port === "" && here.protocol === "https:";
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
