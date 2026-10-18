/* Exact applicant/job idempotency key + browser-wide exclusive final-action lock.
   No site access, user profile persistence or submit authority in this module.
   Within ONE Chrome browser profile this prevents two popups from racing a
   one-shot attempt; cross-device claims still require a server-side ledger. */
export class AttemptError extends Error {}

export async function oneAttemptKey(packet) {
  if (!packet || typeof packet.workspace_id !== "string" ||
      !/^kit-[a-f0-9]{30}$/.test(packet.workspace_id)) {
    throw new AttemptError("Approved applicant workspace is invalid.");
  }
  let url;
  try { url = new URL(packet.application_url); }
  catch { throw new AttemptError("Approved employer job URL is invalid."); }
  if (url.protocol !== "https:" ||
      !["jobs.lever.co","jobs.eu.lever.co"].includes(url.hostname) ||
      url.username || url.password || url.port) {
    throw new AttemptError("Employer URL is not an authorized Lever posting.");
  }
  const job = url.pathname.replace(/\/apply\/?$/, "").replace(/\/+$/, "");
  if (!/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/u.test(job)) {
    throw new AttemptError("Approved job ID is invalid.");
  }
  // Stable across CV edits/revisions, letter changes, /apply suffix, URL
  // query strings and fragments. Only account/workspace + exact job counts.
  const identity = [packet.workspace_id, url.origin, job].join("\0");
  const bytes = new Uint8Array(await crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(identity)
  ));
  return "smartploy.submit." + Array.from(
    bytes, b => b.toString(16).padStart(2,"0")
  ).join("");
}

export async function withSubmissionLock(key, lockManager, callback) {
  if (!/^smartploy\.submit\.[a-f0-9]{64}$/.test(String(key || "")) ||
      typeof callback !== "function" ||
      !lockManager || typeof lockManager.request !== "function") {
    // Never silently fall back to an unprotected final click.
    throw new AttemptError("Exclusive application lock unavailable. Submit manually instead.");
  }
  return lockManager.request(key, { mode: "exclusive" }, async (lock) => {
    if (!lock) throw new AttemptError("Another application attempt holds the lock.");
    return callback();
  });
}
