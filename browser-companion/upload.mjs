/* Reviewed PDF attachment policy for SmartPloy's own Lever browser companion.
   No network, browser API, storage, upload or submission occurs in this module.
   Existing SmartPloy packet and one-attempt gates remain authoritative. */
export class UploadError extends Error {}
export const MAX_PDF_BYTES = 2 * 1024 * 1024;

export function exactLeverForm(activeUrl, packetUrl) {
  try {
    const current = new URL(activeUrl);
    const intended = new URL(packetUrl);
    if (
      current.protocol !== "https:" || intended.protocol !== "https:" ||
      !["jobs.lever.co", "jobs.eu.lever.co"].includes(current.hostname) ||
      current.origin !== intended.origin ||
      current.username || current.password || intended.username || intended.password ||
      current.port || intended.port
    ) return false;
    const posting = intended.pathname.replace(/\/apply\/?$/, "").replace(/\/$/, "");
    if (!/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(posting)) return false;
    return current.pathname === posting + "/apply" ||
      current.pathname === posting + "/apply/";
  } catch {
    return false;
  }
}


/* SP41: reuse the same reviewed PDF + original-user confirmation path on an
   exact Ashby /application route. Pure URL validation; no upload or submit.
   The existing Lever-only final-click adapter stays unchanged. */
export function exactAssistedForm(activeUrl, packetUrl) {
  if (exactLeverForm(activeUrl, packetUrl)) return true;
  try {
    const current = new URL(activeUrl);
    const intended = new URL(packetUrl);
    if (
      current.protocol !== "https:" || intended.protocol !== "https:" ||
      current.hostname !== "jobs.ashbyhq.com" ||
      intended.hostname !== "jobs.ashbyhq.com" ||
      current.origin !== intended.origin ||
      current.username || current.password || intended.username || intended.password ||
      current.port || intended.port || current.search || intended.search ||
      current.hash || intended.hash
    ) return false;
    const posting = intended.pathname.replace(/\/application\/?$/, "").replace(/\/+$/, "");
    if (!/^\/[A-Za-z0-9_-]{1,100}\/[A-Za-z0-9_-]{1,160}$/.test(posting)) return false;
    return current.pathname === posting + "/application" ||
      current.pathname === posting + "/application/";
  } catch {
    return false;
  }
}

export function isLeverFinalProvider(packetUrl) {
  try {
    const url = new URL(packetUrl);
    return url.protocol === "https:" &&
      ["jobs.lever.co", "jobs.eu.lever.co"].includes(url.hostname) &&
      /^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+(?:\/apply\/?)?$/.test(url.pathname) &&
      !url.username && !url.password && !url.port;
  } catch {
    return false;
  }
}

function normalized(text) {
  return String(text || "").replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[^\p{L}\p{N}]+/gu, " ").toLowerCase().trim();
}

export function chooseResumeField(elements) {
  if (!Array.isArray(elements) || elements.length > 250) {
    throw new UploadError("Employer form inspection exceeds the safe field limit.");
  }
  const candidates = [];
  for (const row of elements) {
    if (!row || row.type !== "file") continue;
    const name = normalized([row.label, row.name, row.id].join(" "));
    if (!/(^|\s)(cv|resume|résumé|curriculum vitae|ansioluettelo|meritförteckning)(\s|$)/u.test(name)) {
      continue;
    }
    if (/(^|\s)(cover letter|passport|photo|image|identity document|transcript|certificate)(\s|$)/u.test(name)) {
      throw new UploadError("The employer's upload label is ambiguous. Attach the CV manually.");
    }
    if (!row.visible || row.disabled || row.readonly || row.multiple || row.hasValue) {
      throw new UploadError("The résumé field is hidden, disabled, multiple, or already contains a file.");
    }
    const accept = String(row.accept || "").trim().toLowerCase();
    if (accept && !accept.split(",").some((part) =>
      [".pdf", "application/pdf", "application/*", "*/*"].includes(part.trim())
    )) {
      throw new UploadError("This employer form does not advertise PDF support.");
    }
    if (!Number.isInteger(row.index) || row.index < 0 || row.index >= 250) {
      throw new UploadError("Employer form returned an invalid field identity.");
    }
    candidates.push({
      index: row.index,
      expected_id: String(row.id || ""),
      expected_name: String(row.name || ""),
      expected_label: String(row.label || ""),
      expected_accept: String(row.accept || "")
    });
  }
  if (candidates.length !== 1) {
    throw new UploadError(
      candidates.length ? "More than one résumé field found; attach manually." :
        "No unique visible résumé upload was found; attach manually."
    );
  }
  return candidates[0];
}

export function validatePdf(filename, mime, bytes) {
  if (
    typeof filename !== "string" || filename.length < 5 || filename.length > 150 ||
    /[/\\\u0000-\u001f\u007f]/.test(filename) ||
    !filename.toLowerCase().endsWith(".pdf") ||
    !["", "application/pdf"].includes(String(mime || "").toLowerCase()) ||
    !(bytes instanceof Uint8Array) || bytes.length < 12 || bytes.length > MAX_PDF_BYTES
  ) {
    throw new UploadError("Choose one reviewed PDF document of no more than 2 MiB.");
  }
  // Header + trailer are only type-integrity checks, never a malware scan.
  if (String.fromCharCode(...bytes.subarray(0, 5)) !== "%PDF-") {
    throw new UploadError("The selected file is not a PDF.");
  }
  const tail = bytes.subarray(Math.max(0, bytes.length - 2048));
  let suffix = "";
  for (const item of tail) suffix += String.fromCharCode(item);
  if (!suffix.includes("%%EOF")) {
    throw new UploadError("The selected PDF is incomplete. Export it again from SmartPloy.");
  }
  return { filename, size: bytes.length };
}

export function encodePdfBase64(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length > MAX_PDF_BYTES) {
    throw new UploadError("PDF exceeds the maximum supported upload size.");
  }
  const chunks = [];
  for (let i = 0; i < bytes.length; i += 16384) {
    chunks.push(String.fromCharCode(...bytes.subarray(i, i + 16384)));
  }
  return btoa(chunks.join(""));
}
