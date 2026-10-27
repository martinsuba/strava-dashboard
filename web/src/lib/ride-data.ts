// Ride page data and pure helpers (REQ-008). Schema: docs/ARCHITECTURE.md "Site JSON" rides/<id>.json.

import { formatDuration } from "./format";

export interface RideEffort {
  slug: string;
  name: string;
  elapsed_s: number;
  pr_s: number;
  avg_s: number;
  median_s: number;
  slowest_s: number;
  gap_to_pr_s: number;
  rank: number;
  of: number;
  is_pr: boolean;
  is_pr_at_time: boolean;
}

export interface RideData {
  id: string;
  date: string;
  name: string;
  km: number;
  elapsed_s: number;
  moving_s: number;
  gear: string | null;
  efforts: RideEffort[];
}

export interface BarPositions {
  /** Percent from the left end (the PR) for the median tick and today's dot, 0..100. */
  medianPct: number;
  todayPct: number;
}

/** Position bar: the PR is the left end (0), the slowest effort of the segment the right end (100). */
export function barPositions(
  e: Pick<RideEffort, "pr_s" | "median_s" | "slowest_s" | "elapsed_s">,
): BarPositions {
  const span = e.slowest_s - e.pr_s;
  if (span <= 0) return { medianPct: 0, todayPct: 0 };
  const scale = (s: number): number =>
    Math.round(Math.min(100, Math.max(0, ((s - e.pr_s) / span) * 100)) * 10) / 10;
  return { medianPct: scale(e.median_s), todayPct: scale(e.elapsed_s) };
}

/** Accessible text of the position bar, e.g. "Today 6:17, PR 5:41, median 6:14, slowest 7:36". */
export function barLabel(
  e: Pick<RideEffort, "pr_s" | "median_s" | "slowest_s" | "elapsed_s">,
): string {
  return `Today ${formatDuration(e.elapsed_s)}, PR ${formatDuration(e.pr_s)}, median ${formatDuration(e.median_s)}, slowest ${formatDuration(e.slowest_s)}`;
}

/** Rank as "8 / 24". */
export function rankOf(e: Pick<RideEffort, "rank" | "of">): string {
  return `${e.rank} / ${e.of}`;
}

/** Text of the PR chip: "NEW PR" if it was the PR at the time, "PR" if only the current PR, else null. */
export function prMark(e: Pick<RideEffort, "is_pr" | "is_pr_at_time">): string | null {
  return e.is_pr_at_time ? "NEW PR" : e.is_pr ? "PR" : null;
}

export function newPrCount(efforts: RideEffort[]): number {
  return efforts.filter((e) => e.is_pr_at_time).length;
}
