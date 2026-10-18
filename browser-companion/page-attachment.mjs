/* This standalone function is serialized into the user's explicitly selected
   HTTPS Lever tab by chrome.scripting.executeScript after user approval.
   It MUST NOT close over any popup variables, make external network requests or submit a form.
   The target employer page may itself upload immediately on input/change:
   the browser owner must consent to transferring the named PDF beforehand. */
export async function attachReviewedPdf(payload) {
  const stop = (reason) => ({ status: "blocked", reason });
  if (!payload || typeof payload !== "object") return stop("Invalid upload request.");
  let page, approved;
  try {
    page = new URL(location.href);
    approved = new URL(payload.application_url);
  } catch {
    return stop("The application URL is invalid.");
  }
  const posting = approved.pathname.replace(/\/apply\/?$/, "").replace(/\/$/, "");
  if (
    page.protocol !== "https:" || approved.protocol !== "https:" ||
    !["jobs.lever.co", "jobs.eu.lever.co"].includes(page.hostname) ||
    page.origin !== approved.origin || page.username || page.password ||
    approved.username || approved.password || page.port || approved.port ||
    !/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(posting) ||
    ![posting + "/apply", posting + "/apply/"].includes(page.pathname) ||
    location.href !== payload.inspected_url
  ) return stop("The employer job/form changed; reinspect before attaching.");
  if (
    !Number.isInteger(payload.index) || payload.index < 0 || payload.index >= 250 ||
    typeof payload.expected_id !== "string" ||
    typeof payload.expected_name !== "string" ||
    typeof payload.expected_label !== "string" ||
    typeof payload.expected_accept !== "string" ||
    typeof payload.file_name !== "string" ||
    payload.file_name.length > 150 || !/\.pdf$/i.test(payload.file_name) ||
    /[/\\\u0000-\u001f\u007f]/.test(payload.file_name) ||
    typeof payload.base64 !== "string" || payload.base64.length > 2800000 ||
    typeof payload.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(payload.sha256) ||
    !Number.isInteger(payload.size) || payload.size < 12 || payload.size > 2097152
  ) return stop("The approved PDF or upload field identity is invalid.");

  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  if (all.length > 250 || payload.index >= all.length) {
    return stop("The employer form changed since inspection.");
  }
  const input = all[payload.index];
  if (!input || input.tagName !== "INPUT" || input.type !== "file" ||
      input.disabled || input.readOnly || input.multiple || input.files?.length ||
      !input.closest("form") ||
      String(input.id || "") !== payload.expected_id ||
      String(input.name || "") !== payload.expected_name ||
      String(input.accept || "") !== payload.expected_accept) {
    return stop("The résumé input changed, is ambiguous, or already contains a file.");
  }
  const label = String(input.labels?.[0]?.innerText ||
    input.getAttribute("aria-label") ||
    (input.id ? document.querySelector('label[for="' + CSS.escape(input.id) + '"]')?.innerText : "") ||
    input.getAttribute("placeholder") || input.getAttribute("name") || input.id || "")
    .trim().slice(0, 150);
  if (label !== payload.expected_label) {
    return stop("The résumé label changed since inspection.");
  }
  if (input.closest("[hidden],[aria-hidden='true'],[inert]") ||
      getComputedStyle(input).display === "none" ||
      getComputedStyle(input).visibility === "hidden" ||
      input.getClientRects().length === 0) {
    return stop("The résumé input is no longer visible.");
  }
  const meaning = [label, input.name, input.id].join(" ")
    .replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[^\p{L}\p{N}]+/gu, " ").toLowerCase();
  if (!/(^|\s)(cv|resume|résumé|curriculum vitae|ansioluettelo|meritförteckning)(\s|$)/u.test(meaning) ||
      /(^|\s)(cover letter|passport|photo|image|identity document|transcript|certificate)(\s|$)/u.test(meaning)) {
    return stop("The target is not a unique résumé input.");
  }
  const accept = String(input.accept || "").toLowerCase();
  if (accept && !accept.split(",").some((x) =>
    [".pdf", "application/pdf", "application/*", "*/*"].includes(x.trim())
  )) return stop("Employer form does not support PDF attachments.");

  let bytes;
  try {
    const binary = atob(payload.base64);
    if (binary.length !== payload.size) return stop("PDF size changed during transfer.");
    bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    if (String.fromCharCode(...bytes.subarray(0, 5)) !== "%PDF-") {
      return stop("Uploaded bytes did not contain a PDF header.");
    }
    const trailing = bytes.subarray(Math.max(0, bytes.length - 2048));
    let suffix = "";
    for (const b of trailing) suffix += String.fromCharCode(b);
    if (!suffix.includes("%%EOF")) return stop("Uploaded PDF is incomplete.");
    const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const digest = Array.from(hash, (b) => b.toString(16).padStart(2, "0")).join("");
    if (digest !== payload.sha256) return stop("PDF digest changed during transfer.");
  } catch {
    return stop("PDF validation failed in the employer tab.");
  }

  // Recheck after async hashing: a hostile/fast-changing form must not redirect
  // the upload to a newly mounted control or a different account.
  if (location.href !== payload.inspected_url ||
      !input.isConnected || input.files?.length ||
      Array.from(document.querySelectorAll("input,textarea,select"))[payload.index] !== input) {
    return stop("The employer form changed during PDF validation.");
  }
  try {
    const selected = new File([bytes], payload.file_name, { type: "application/pdf" });
    const transfer = new DataTransfer();
    transfer.items.add(selected);
    input.files = transfer.files;
    if (!input.files || input.files.length !== 1 ||
        input.files[0].size !== payload.size ||
        input.files[0].name !== payload.file_name) {
      return stop("The browser did not accept the selected résumé.");
    }
    // The employer's own handlers may upload immediately; do not claim their
    // server accepted it. The only proof here is a local FileList assignment.
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    return { status: "attached_locally", reason: "PDF placed in the employer's résumé field. Verify upload status on the page." };
  } catch {
    return { status: "ambiguous", reason: "Attachment may have triggered employer processing. Inspect the page before doing anything else." };
  }
}
