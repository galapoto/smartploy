import type { EmployerSector, RankingCard } from "./types";

export type DisplayMode = "heatmap" | "percentage";
export type SectorFilter = "all" | EmployerSector;

/** Only absolute HTTP(S) URLs without credentials or control characters
 * can become navigable browser links. Job-feed URLs are untrusted data.
 */
export function safeExternalJobUrl(raw: string | null | undefined): string {
  if (typeof raw !== "string" || !raw || raw !== raw.trim() ||
      /[\u0000-\u001f\u007f\\]/.test(raw) ||
      !/^https?:\/\//i.test(raw)) return "";
  try {
    const parsed = new URL(raw);
    if (!["http:", "https:"].includes(parsed.protocol) ||
        !parsed.hostname || parsed.username || parsed.password) return "";
    return parsed.href;
  } catch {
    return "";
  }
}

export function scoreBand(score: number): string {
  if (score >= 90) return "exceptional";
  if (score >= 80) return "strong";
  if (score >= 70) return "worthwhile";
  if (score >= 60) return "possible";
  if (score >= 45) return "weak";
  return "poor";
}

export function queueLabel(queue: string): string {
  const labels: Record<string, string> = {
    exceptional: "Exceptional",
    auto_prepare: "Auto prepare",
    review: "Review",
    possible: "Possible"
  };
  return labels[queue] ?? queue.replaceAll("_", " ");
}

export function sectorLabel(sector: EmployerSector): string {
  if (sector === "public") return "Public";
  if (sector === "private") return "Private";
  return "Unknown";
}

export function filterBySector(items: RankingCard[], sector: SectorFilter): RankingCard[] {
  if (sector === "all") return items;
  return items.filter((item) => (item.job?.employer_sector ?? "unknown") === sector);
}

export function relativeFreshness(value: string, now = new Date()): string {
  if (!value) return "Freshness unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Freshness unknown";
  const diffMs = Math.max(0, now.getTime() - date.getTime());
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "Seen just now";
  if (minutes < 60) return "Seen " + minutes + "m ago";
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return "Seen " + hours + "h ago";
  const days = Math.floor(hours / 24);
  return "Seen " + days + "d ago";
}

/** Separate a vacancy's publication/discovery date from when its source last showed it.
 * No source observation proves that an employer is still accepting applicants.
 */
export interface ListingObservationLabels {
  origin: string;
  observation: string;
  caution: string | null;
}

const SOURCE_AGE_CAUTION_MS = 72 * 60 * 60 * 1000;
const ALLOWED_CLOCK_SKEW_MS = 5 * 60 * 1000;

function observationAgeMs(value: string, now: Date): number | null {
  if (!value || !Number.isFinite(now.getTime())) return null;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  const elapsed = now.getTime() - timestamp;
  if (elapsed < -ALLOWED_CLOCK_SKEW_MS) return null;
  return Math.max(0, elapsed);
}

function ageWords(elapsed: number): string {
  if (elapsed < 60_000) return "just now";
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 60) return minutes + "m ago";
  const hours = Math.floor(elapsed / 3_600_000);
  if (hours < 24) return hours + "h ago";
  return Math.floor(elapsed / 86_400_000) + "d ago";
}

export function listingObservationLabels(
  postedAt: string, firstSeenAt: string, lastSeenAt: string, now = new Date()
): ListingObservationLabels {
  const postedAge = observationAgeMs(postedAt, now);
  const firstAge = observationAgeMs(firstSeenAt, now);
  const observedAge = observationAgeMs(lastSeenAt, now);

  const origin = postedAge !== null ? "Posted " + ageWords(postedAge)
    : firstAge !== null ? "First discovered " + ageWords(firstAge)
    : "Publication date unknown";

  if (observedAge === null) {
    return {
      origin, observation: "Last source observation unknown",
      caution: "Source observation time is unknown — confirm on employer site."
    };
  }

  return {
    origin,
    observation: "Last observed " + ageWords(observedAge),
    caution: observedAge >= SOURCE_AGE_CAUTION_MS
      ? "Source was last observed at least 72h ago — confirm on employer site."
      : null
  };
}

export function formatState(state: string): string {
  return state.replaceAll("_", " ");
}


export function relativeSchedule(value: string, now = new Date()): string {
  if (!value) return "Schedule unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Schedule unknown";
  const diffMs = date.getTime() - now.getTime();
  if (diffMs <= 0) return "Due now";
  const minutes = Math.ceil(diffMs / 60000);
  if (minutes < 60) return "in " + minutes + "m";
  const hours = Math.ceil(minutes / 60);
  if (hours < 24) return "in " + hours + "h";
  const days = Math.ceil(hours / 24);
  return "in " + days + "d";
}

export function formatCadence(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "unknown cadence";
  if (seconds % 3600 === 0) return "every " + seconds / 3600 + "h";
  if (seconds % 60 === 0) return "every " + seconds / 60 + "m";
  return "every " + seconds + "s";
}
