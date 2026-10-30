import { safeExternalJobUrl } from "./lib";
import type { SearchJobCard } from "./types";

/**
 * SP75: build a *selection suggestion*, not an application or an employer
 * action. Recommendations are CV-text retrieval hints, never proof of
 * qualification. Candidate must explicitly click Prepare applications.
 */
export const AUTOAPPLY_SELECTION_LIMIT = 15;

export function isSafeCVShortlistMatch(row: SearchJobCard): boolean {
  return row.lane === "recommended" &&
    row.job.source_current === true &&
    // An incidental mention of a skill in an unrelated occupation (e.g.
    // "Python" in a driver's advert) is not sufficient for bulk selection.
    // Exact role/title alignment is a stricter gate than a weak keyword rank.
    row.reasons.some((reason) => reason.startsWith("Job title matches ")) &&
    safeExternalJobUrl(row.job.application_url) !== null;
}

export type AutoApplyShortlist = {
  selected: string[];
  added: string[];
  eligible: number;
};

export function addCVShortlist(
  previouslySelected: readonly string[],
  recommended: readonly SearchJobCard[],
): AutoApplyShortlist {
  const selected: string[] = [];
  const seen = new Set<string>();
  for (const key of previouslySelected) {
    if (key && !seen.has(key) && selected.length < AUTOAPPLY_SELECTION_LIMIT) {
      selected.push(key);
      seen.add(key);
    }
  }
  const added: string[] = [];
  let eligible = 0;
  for (const row of recommended) {
    if (!isSafeCVShortlistMatch(row) || !row.canonical_key) continue;
    if (!seen.has(row.canonical_key)) eligible += 1;
    if (seen.has(row.canonical_key) || selected.length >= AUTOAPPLY_SELECTION_LIMIT) continue;
    selected.push(row.canonical_key);
    added.push(row.canonical_key);
    seen.add(row.canonical_key);
  }
  return { selected, added, eligible };
}

/**
 * Reject stale, hidden or retired keys before the private application
 * mutation loop. This does not replace the API's own current-posting check.
 */
export function visibleCurrentKeys(
  selected: readonly string[],
  visible: readonly SearchJobCard[],
): string[] {
  const current = new Set(visible.filter((row) =>
    row.job.source_current && !!safeExternalJobUrl(row.job.application_url)
  ).map((row) => row.canonical_key));
  return [...new Set(selected)].filter((key) => current.has(key));
}
