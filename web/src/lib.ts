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
