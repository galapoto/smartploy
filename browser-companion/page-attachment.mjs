/* This standalone function is serialized into the user's explicitly selected
   HTTPS Lever tab by chrome.scripting.executeScript after user approval.
   It MUST NOT close over any popup variables, make external network requests or submit a form.
   The target employer page may itself upload immediately on input/change:
   the browser owner must consent to transferring the named PDF beforehand. */
export async function attachReviewedPdf(payload) {
  const stop = (reason) => ({ status: "blocked", reason });
  if (!payload || typeof payload !== "object" ||
      (payload.kind !== undefined && !["cv","letter"].includes(payload.kind)))
    return stop("Invalid upload request.");
  const attachmentKind = payload.kind === "letter" ? "letter" : "cv";
  let page, approved;
  try {
    page = new URL(location.href);
    approved = new URL(payload.application_url);
  } catch {
    return stop("The application URL is invalid.");
  }
  const leverPosting = approved.pathname.replace(/\/apply\/?$/, "").replace(/\/$/, "");
  const ashbyPosting = approved.pathname.replace(/\/application\/?$/, "").replace(/\/+$/, "");
  const lever = ["jobs.lever.co", "jobs.eu.lever.co"].includes(page.hostname) &&
    /^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(leverPosting) &&
    [leverPosting + "/apply", leverPosting + "/apply/"].includes(page.pathname);
  const ashby = page.hostname === "jobs.ashbyhq.com" &&
    /^\/[A-Za-z0-9_-]{1,100}\/[A-Za-z0-9_-]{1,160}$/.test(ashbyPosting) &&
    !page.search && !approved.search && !page.hash && !approved.hash &&
    [ashbyPosting + "/application", ashbyPosting + "/application/"]
      .includes(page.pathname);
  const ghHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io"];
  const greenhouse = ghHosts.includes(page.hostname) &&
    ghHosts.includes(approved.hostname) &&
    /^\/[A-Za-z0-9_-]{1,100}\/jobs\/[0-9]{1,20}\/?$/.test(approved.pathname) &&
    page.pathname.replace(/\/+$/, "") === approved.pathname.replace(/\/+$/, "") &&
    !page.search && !approved.search && !page.hash && !approved.hash;
  if (
    page.protocol !== "https:" || approved.protocol !== "https:" ||
    (page.origin !== approved.origin && !greenhouse) ||
    page.username || page.password ||
    approved.username || approved.password || page.port || approved.port ||
    !(lever || ashby || greenhouse) || location.href !== payload.inspected_url ||
    (typeof window !== "undefined" && window.top !== window.self)
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
  const owningForm = input?.closest?.("form");
  // On Lever the *application submit* button, not any globally visible
  // upload control, is the authority for the destination form. A separate
  // profile/talent-pool form must never receive reviewed applicant PDFs.
  const leverApplicationForm = () => {
    if (!lever) return owningForm;
    const buttons = Array.from(document.querySelectorAll('button,input[type="submit"]'))
      .filter(button => {
        const title = String(button.innerText || button.value ||
          button.getAttribute?.("aria-label") || "")
          .replace(/\s+/g, " ").trim().toLowerCase();
        if (!["submit application","send application","lähetä hakemus",
              "skicka ansökan"].includes(title) || button.disabled ||
            button.closest?.("[hidden],[aria-hidden='true'],[inert]")) return false;
        const style = getComputedStyle(button);
        return style.display !== "none" && style.visibility !== "hidden" &&
          button.getClientRects().length > 0;
      });
    return buttons.length === 1 ? (buttons[0].form || buttons[0].closest("form")) : null;
  };
  if (lever && (!owningForm || leverApplicationForm() !== owningForm)) {
    return stop("The reviewed PDF input is not part of the final application form.");
  }
  if (!input || input.tagName !== "INPUT" || input.type !== "file" ||
      input.matches(":disabled") || input.readOnly || input.multiple || input.files?.length ||
      !owningForm || input.form !== owningForm ||
      String(input.id || "") !== payload.expected_id ||
      String(input.name || "") !== payload.expected_name ||
      String(input.accept || "") !== payload.expected_accept) {
    return stop("The résumé input changed, is ambiguous, or already contains a file.");
  }
  const readLabel = () => String(input.labels?.[0]?.innerText ||
    input.getAttribute("aria-label") ||
    (input.id ? document.querySelector('label[for="' + CSS.escape(input.id) + '"]')?.innerText : "") ||
    input.getAttribute("placeholder") || input.getAttribute("name") || input.id || "")
    .trim().slice(0, 150);
  const label = readLabel();
  if (label !== payload.expected_label) {
    return stop("The résumé label changed since inspection.");
  }
  if (input.closest("[hidden],[aria-hidden='true'],[inert]") ||
      getComputedStyle(input).display === "none" ||
      getComputedStyle(input).visibility === "hidden" ||
      input.getClientRects().length === 0) {
    return stop("The résumé input is no longer visible.");
  }
  const matchesApprovedKind = (currentLabel) => {
    const meaning = [currentLabel, input.name, input.id].join(" ")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/[^\p{L}\p{N}]+/gu, " ").toLowerCase();
    const isCV = /(^|\s)(cv|resume|résumé|curriculum vitae|ansioluettelo|meritförteckning)(\s|$)/u.test(meaning);
    const isLetter = /(^|\s)(cover letter|application letter|motivation letter|saatekirje|hakemuskirje|personligt brev)(\s|$)/u.test(meaning);
    const ambiguous = /(^|\s)(passport|photo|image|identity document|transcript|certificate|reference letter)(\s|$)/u.test(meaning);
    return !ambiguous && (attachmentKind === "cv" ?
      isCV && !isLetter : isLetter && !isCV);
  };
  if (!matchesApprovedKind(label)) {
    return stop("The target is not a unique approved " +
      (attachmentKind === "cv" ? "résumé" : "cover-letter") + " input.");
  }
  const acceptsPdf = () => {
    const accept = String(input.accept || "").toLowerCase();
    return !accept || accept.split(",").some((x) =>
      [".pdf", "application/pdf", "application/*", "*/*"].includes(x.trim()));
  };
  if (!acceptsPdf()) return stop("Employer form does not support PDF attachments.");

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
  const latest = Array.from(document.querySelectorAll("input,textarea,select"));
  // Do not transfer a reviewed document if an employer-side reactive update
  // has repurposed the very same DOM node during the async SHA-256 operation.
  // All checks remain synchronous until FileList assignment and input/change.
  if (location.href !== payload.inspected_url ||
      !input.isConnected || latest.length !== all.length ||
      latest.some((node, index) => node !== all[index]) ||
      latest[payload.index] !== input ||
      input.tagName !== "INPUT" || input.type !== "file" ||
      input.matches(":disabled") || input.readOnly || input.multiple ||
      input.files?.length || input.closest("form") !== owningForm ||
      input.form !== owningForm ||
      (lever && leverApplicationForm() !== owningForm) ||
      String(input.id || "") !== payload.expected_id ||
      String(input.name || "") !== payload.expected_name ||
      String(input.accept || "") !== payload.expected_accept ||
      readLabel() !== payload.expected_label ||
      !matchesApprovedKind(readLabel()) || !acceptsPdf() ||
      input.closest("[hidden],[aria-hidden='true'],[inert]") ||
      getComputedStyle(input).display === "none" ||
      getComputedStyle(input).visibility === "hidden" ||
      input.getClientRects().length === 0) {
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
      return stop("The browser did not accept the selected reviewed PDF.");
    }
    // The employer's own handlers may upload immediately; do not claim their
    // server accepted it. The only proof here is a local FileList assignment.
    input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    return { status: "attached_locally", reason: "Reviewed " +
      (attachmentKind === "cv" ? "CV" : "cover-letter") +
      " PDF placed in the employer's exact upload field. Verify its upload indicator." };
  } catch {
    return { status: "ambiguous", reason: "Attachment may have triggered employer processing. Inspect the page before doing anything else." };
  }
}


/* SP-V4-ONE-PROFILE-APPLY-001: read-only, exact approved letter text proof.
   Chrome serializes this standalone function into an employer tab. It never
   writes, uploads, calls a network API or consumes final-submit permission.
   A text fallback is valid only if the employer has NO dedicated letter
   upload field and the reviewed text is visibly present in the ONE final
   Lever form, with its original exact account-approved value. */
export function verifyReviewedCoverLetterText(applicationUrl, inspectedUrl, approvedText) {
  const deny = (reason) => ({ready:false,reason});
  if (typeof approvedText !== "string" || approvedText.trim().length < 60 ||
      approvedText.length > 10000 || typeof inspectedUrl !== "string") {
    return deny("Approved cover-letter text is missing or invalid.");
  }
  let here, intended;
  try {
    here = new URL(location.href);
    intended = new URL(applicationUrl);
  } catch { return deny("Employer application URL is invalid."); }
  const posting = intended.pathname.replace(/\/apply\/?$/, "").replace(/\/+$/, "");
  if (location.href !== inspectedUrl || here.protocol !== "https:" ||
      intended.protocol !== "https:" ||
      !["jobs.lever.co","jobs.eu.lever.co"].includes(here.hostname) ||
      here.origin !== intended.origin || here.search || here.hash ||
      intended.search || intended.hash ||
      here.username || here.password || intended.username || intended.password ||
      here.port || intended.port ||
      !/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(posting) ||
      ![posting+"/apply",posting+"/apply/"].includes(here.pathname) ||
      (typeof window !== "undefined" && window.top !== window.self)) {
    return deny("Selected employer job or browser context changed.");
  }
  const visible = (el) => Boolean(el && !el.closest?.("[hidden],[aria-hidden='true'],[inert]") &&
    getComputedStyle(el).display !== "none" &&
    getComputedStyle(el).visibility !== "hidden" &&
    el.getClientRects().length > 0);
  const submitButtons = Array.from(document.querySelectorAll('button,input[type="submit"]'))
    .filter(el => visible(el) && !el.disabled &&
      ["submit application","send application","lähetä hakemus","skicka ansökan"]
        .includes(String(el.innerText || el.value || el.getAttribute("aria-label") || "")
          .replace(/\s+/g, " ").trim().toLowerCase()));
  if (submitButtons.length !== 1) {
    return deny("Unique employer submission form could not be identified.");
  }
  const form = submitButtons[0].closest("form");
  if (!form || !visible(form)) return deny("Reviewed employer form is unavailable.");
  const all = Array.from(document.querySelectorAll("input,textarea,select"));
  if (all.length > 250) return deny("Employer form exceeds the safe field limit.");
  const labelFor = (el) => String(el.labels?.[0]?.innerText ||
    el.getAttribute("aria-label") ||
    (el.id ? document.querySelector('label[for="'+CSS.escape(el.id)+'"]')?.innerText : "") ||
    el.getAttribute("placeholder") || el.name || el.id || "").trim().slice(0,150);
  const approvedLetterField = (el) => {
    const meaning = [labelFor(el),el.name,el.id].join(" ")
      .normalize("NFKC").replace(/([a-z0-9])([A-Z])/g,"$1 $2")
      .replace(/[^\p{L}\p{N}]+/gu," ").toLowerCase().trim();
    return /(^|\s)(cover letter|application letter|motivation letter|saatekirje|hakemuskirje|personligt brev)(\s|$)/u.test(meaning) &&
      !/(^|\s)(cv|resume|résumé|passport|identity|photo|reference|salary|visa|consent|privacy|attestation|signature|disability)(\s|$)/u.test(meaning);
  };
  // A dedicated letter input must use the separately reviewed PDF, even when
  // it is hidden, disabled, occupied, or owned by another form.
  if (all.some(el => el.type === "file" && approvedLetterField(el))) {
    return deny("Employer provides a separate cover-letter upload; use the reviewed PDF.");
  }
  const candidates = all.filter(el =>
    (el.tagName === "TEXTAREA" ||
      (el.tagName === "INPUT" && (el.type || "").toLowerCase() === "text")) &&
    approvedLetterField(el));
  if (candidates.length !== 1) {
    return deny("An exact unique employer cover-letter text field was not found.");
  }
  const field = candidates[0];
  if (!visible(field) || field.disabled || field.matches(":disabled") ||
      field.readOnly || !field.isConnected || field.form !== form ||
      field.closest("form") !== form || !String(field.name || "").trim() ||
      String(field.value || "").trim() !== approvedText.trim()) {
    return deny("Approved cover-letter text is missing, altered, or not in the submitted form.");
  }
  return {ready:true,mode:"reviewed_cover_letter_text"};
}
