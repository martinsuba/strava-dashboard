// Ride page data and pure helpers (REQ-008). Schema: docs/ARCHITECTURE.md "Site JSON" rides/<id>.json.

export interface RideEffort {
  slug: string;
  name: string;
  elapsed_s: number;
  pr_s: number;
  avg_s: number;
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

/** Extra room right of the slower of average and today, so neither marker sits on the bar's end. */
export const BAR_MARGIN = 1.25;

export interface BarPositions {
  /** Percent from the left end (the PR) for the average tick and today's dot, 0..100. */
  avgPct: number;
  todayPct: number;
}

/**
 * Position bar: the PR is the left end. rides/<id>.json has no slowest time (and a page fetches only
 * its own JSON, D-005), so the right end is PR + BAR_MARGIN x the larger of (average, today) - PR.
 */
export function barPositions(e: Pick<RideEffort, "pr_s" | "avg_s" | "elapsed_s">): BarPositions {
  const span = Math.max(e.avg_s, e.elapsed_s, e.pr_s) - e.pr_s;
  if (span <= 0) return { avgPct: 0, todayPct: 0 };
  const scale = (s: number): number =>
    Math.round(Math.min(100, Math.max(0, ((s - e.pr_s) / (span * BAR_MARGIN)) * 100)) * 10) / 10;
  return { avgPct: scale(e.avg_s), todayPct: scale(e.elapsed_s) };
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
