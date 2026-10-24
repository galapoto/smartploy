/* SP26: reviewed ONE-CLICK Lever browser adapter.
   Executes ONLY after a separate first-party authenticated sticky claim was
   consumed and the popup persisted its no-retry local marker. Employer origin
   gets no SmartPloy cookie, claim ID, bearer token or full CV document body.
   A click is an attempted submission, never a provider-issued application ID.
   This function is self-contained for MV3 ISOLATED-world injection. */
export async function submitReviewedLeverOnce(expected) {
  const fail = (reason) => ({
    attempted: false, provider_acknowledged: false, reason,
  });
  if (!expected || typeof expected !== "object" ||
      typeof expected.application_url !== "string" ||
      !/^[a-f0-9]{64}$/.test(expected.cv_pdf_sha256) ||
      !Number.isSafeInteger(expected.cv_pdf_size) ||
      expected.cv_pdf_size < 12 || expected.cv_pdf_size > 2 * 1024 * 1024 ||
      typeof expected.email !== "string" || !expected.email.includes("@") ||
      typeof expected.full_name !== "string" || !expected.full_name.trim() ||
      typeof expected.cover_letter !== "string" ||
      expected.cover_letter.length < 60) {
    return fail("invalid_reviewed_binding");
  }
  if (typeof window !== "undefined" && window.top !== window.self) {
    return fail("nested_employer_frame");
  }
  const validUrl = (value) => {
    try {
      const u = new URL(value);
      if (u.protocol !== "https:" ||
          !["jobs.lever.co", "jobs.eu.lever.co"].includes(u.hostname) ||
          u.username || u.password || u.port || u.search || u.hash ||
          !/^\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\/apply\/?$/.test(u.pathname)) {
        return null;
      }
      return u;
    } catch {
      return null;
    }
  };
  const target = validUrl(expected.application_url);
  const here = validUrl(location.href);
  if (!target || !here || target.origin !== here.origin ||
      target.pathname.replace(/\/$/, "") !== here.pathname.replace(/\/$/, "")) {
    return fail("wrong_employer_job");
  }
  if (document.documentElement?.hasAttribute("data-smartploy-final-attempt")) {
    return fail("employer_form_already_attempted");
  }
  const visible = (element) => {
    if (!element || element.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" &&
      element.getClientRects().length > 0;
  };
  if (document.querySelector(
    'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.g-recaptcha,[data-sitekey],.cf-turnstile'
  )) return fail("security_challenge_requires_human");
  const buttons = Array.from(document.querySelectorAll('button,input[type="submit"]'))
    .filter((element) => {
      const title = String(
        element.innerText || element.value || element.getAttribute("aria-label") || ""
      ).replace(/\s+/g, " ").trim().toLowerCase();
      return visible(element) && !element.disabled &&
        ["submit application", "send application", "lähetä hakemus",
         "skicka ansökan"].includes(title);
    });
  if (buttons.length !== 1) return fail("nonunique_final_submit_control");
  const finalButton = buttons[0];
  const form = finalButton.closest("form");
  if (!form || !visible(form)) return fail("standard_employer_form_missing");

  // Inspect every form control for attachments, including non-visible inputs:
  // hidden populated file controls may still be sent with the employer form.
  const allElements = Array.from(form.querySelectorAll("input,textarea,select"));
  if (allElements.length > 250) return fail("dynamic_form_too_large");
  const elements = allElements.filter(visible);
  for (const item of elements) {
    if (item.disabled) continue;
    const type = String(item.type || "").toLowerCase();
    if (type === "password" || type === "hidden") continue;
    const required = item.required === true ||
      item.getAttribute("aria-required") === "true";
    const hasValue = type === "file" ? Boolean(item.files?.length) :
      ["checkbox", "radio"].includes(type) ? Boolean(item.checked) :
      Boolean(String(item.value || "").trim());
    if ((required && !hasValue) || (item.validity && !item.validity.valid)) {
      return fail("required_employer_field_unresolved");
    }
  }
  if (typeof form.checkValidity !== "function" || !form.checkValidity()) {
    return fail("employer_form_invalid");
  }

  const labelled = (element) => String(
    element.labels?.[0]?.innerText || element.getAttribute("aria-label") ||
    element.name || element.id || ""
  ).toLowerCase();
  const emailInputs = elements.filter((item) =>
    String(item.type || "").toLowerCase() === "email" ||
    item.autocomplete === "email" ||
    /(^|[^a-z])email([^a-z]|$)|sähköpost|e-post/.test(labelled(item))
  );
  if (emailInputs.length !== 1 ||
      String(emailInputs[0].value || "").trim().toLowerCase() !==
        expected.email.trim().toLowerCase()) {
    return fail("reviewed_email_changed_or_unverifiable");
  }
  const names = elements.filter((item) => item.autocomplete === "name" ||
    /^(full.?name|full.?legal.?name|name|koko nimi|namn)$/.test(labelled(item)));
  const fullNameMatches = names.length === 1 &&
    String(names[0].value || "").trim().replace(/\s+/g, " ") ===
    expected.full_name.trim().replace(/\s+/g, " ");
  const firsts = elements.filter((item) => item.autocomplete === "given-name");
  const lasts = elements.filter((item) => item.autocomplete === "family-name");
  const splitNameMatches = firsts.length === 1 && lasts.length === 1 &&
    [firsts[0].value, lasts[0].value].map(s => String(s || "").trim()).join(" ") ===
      expected.full_name.trim().replace(/\s+/g, " ");
  if (!fullNameMatches && !splitNameMatches) {
    return fail("reviewed_name_changed_or_unverifiable");
  }

  const letters = elements.filter((item) =>
    /cover.?letter|saatekirje|personligt brev/i.test(labelled(item)));
  if (letters.length > 1 ||
      (letters.length === 1 &&
       String(letters[0].value || "").trim() !== expected.cover_letter.trim())) {
    return fail("reviewed_cover_letter_changed_or_unverifiable");
  }

  const resumes = elements.filter((item) => {
    if (String(item.type || "").toLowerCase() !== "file") return false;
    return /cv|resume|r[ée]sum[ée]|ansioluettelo|meritförteckning/i.test(labelled(item));
  });
  if (resumes.length !== 1 || resumes[0].files?.length !== 1) {
    return fail("unique_reviewed_cv_attachment_missing");
  }
  // Only the one previously reviewed CV may be attached. Extra file inputs can
  // carry private or stale documents that are not covered by the CV digest.
  const otherAttachments = allElements.filter((item) =>
    String(item.type || "").toLowerCase() === "file" &&
    item !== resumes[0] && Boolean(item.files?.length)
  );
  if (otherAttachments.length) {
    return fail("unreviewed_extra_attachment_present");
  }
  const cv = resumes[0].files[0];
  if (cv.size !== expected.cv_pdf_size || cv.size > 2 * 1024 * 1024 ||
      !/\.pdf$/i.test(cv.name) ||
      (cv.type && cv.type.toLowerCase() !== "application/pdf")) {
    return fail("reviewed_cv_attachment_changed");
  }
  try {
    const buffer = await cv.arrayBuffer();
    // No CV bytes or file digest leave the employer tab.
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", buffer));
    const actual = Array.from(digest, b => b.toString(16).padStart(2, "0")).join("");
    if (actual !== expected.cv_pdf_sha256) return fail("reviewed_cv_attachment_changed");
  } catch {
    return fail("reviewed_cv_unverifiable");
  }

  // All DOM checks are refreshed just before the ONE click. A dynamic page
  // racing this click yields an uncertain result, never a silent retry.
  if (location.href !== here.href || finalButton.disabled || !visible(finalButton) ||
      finalButton.closest("form") !== form || !form.checkValidity() ||
      document.documentElement?.hasAttribute("data-smartploy-final-attempt")) {
    return fail("employer_form_changed");
  }
  document.documentElement?.setAttribute("data-smartploy-final-attempt", "1");
  try {
    finalButton.click();
    return {
      attempted: true,
      provider_acknowledged: false,
      automatic_retry_authorized: false,
      reason: "browser_click_attempted_employer_receipt_not_verified",
    };
  } catch {
    return fail("outcome_uncertain_do_not_retry");
  }
}
