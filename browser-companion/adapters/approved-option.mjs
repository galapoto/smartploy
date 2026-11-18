/* SmartPloy V4 - exact approved-option resolver.
 * Sanitized adaptation of the matchOption option-enumeration algorithm in:
 * vesaias/JobNavigator@623822529389d6919d86be07271e0ea94e20b514
 * extension/lib/autofill_match.js (MIT, Copyright 2026 JobNavigator Contributors).
 * DELIBERATE SAFETY DELTA: remove substring/fuzzy matches, automatic boolean
 * inference and global lookups. Require exactly one approved, enabled option.
 * This module has no DOM, network, credential, upload or submit capability.
 */
export function uniqueApprovedOption(approved, options) {
  if (typeof approved !== "string" || !approved || !Array.isArray(options)) return null;
  let matched = null;
  let hits = 0;
  options.forEach((option, index) => {
    if (!option || option.disabled || typeof option.value !== "string") return;
    if (option.value === approved) {
      hits++;
      matched = { index, value: option.value, label: option.label };
    }
  });
  return hits === 1 ? matched : null;
}
