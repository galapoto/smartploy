import type { EmployerSector, RankingCard } from "./types";

export type DisplayMode = "heatmap" | "percentage";
export type SectorFilter = "all" | EmployerSector;

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
