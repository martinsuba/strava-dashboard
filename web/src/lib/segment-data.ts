// Segment page logic without DOM (REQ-007): sorting, summary figures, chart model.
import { DISPLAY_TIME_ZONE, formatDate, formatDuration } from "./format";

export interface Effort {
  segment_slug: string;
  activity_id: string;
  ride_name: string;
  start_t: number; // epoch seconds, UTC
  elapsed_s: number;
  distance_m: number;
  avg_kmh: number;
  rank: number;
  gap_to_pr_s: number;
  is_pr_at_time: boolean;
}

export interface SegmentData {
  name: string;
  ref_length_m: number;
  efforts: Effort[];
  per_year: { year: number; count: number; best_s: number }[];
}

export type SortMode = "fastest" | "newest";

/** Fastest first (ties: earlier ride first), or newest first (ties: faster first). Input is not mutated. */
export function sortEfforts(efforts: readonly Effort[], mode: SortMode): Effort[] {
  const byTime = (a: Effort, b: Effort): number =>
    a.elapsed_s - b.elapsed_s || a.start_t - b.start_t;
  const byDate = (a: Effort, b: Effort): number =>
    b.start_t - a.start_t || a.elapsed_s - b.elapsed_s;
  return [...efforts].sort(mode === "fastest" ? byTime : byDate);
}

/** Rank cell text: PR, 2nd, 3rd, then the number. */
export function rankLabel(rank: number): string {
  return rank === 1 ? "PR" : rank === 2 ? "2nd" : rank === 3 ? "3rd" : String(rank);
}

/** Gap to the PR as "+m:ss"; the PR itself shows an em dash. */
export function formatGap(gapSeconds: number): string {
  return gapSeconds <= 0 ? "—" : `+${formatDuration(gapSeconds)}`;
}

/** Calendar year of an epoch-seconds instant in Europe/Bratislava. */
export function yearOf(epochSeconds: number): number {
  return Number(
    new Intl.DateTimeFormat("en-GB", { timeZone: DISPLAY_TIME_ZONE, year: "numeric" }).format(
      new Date(epochSeconds * 1000),
    ),
  );
}

/** Median of the elapsed times, rounded to whole seconds (mean of the two middle values when even). */
export function medianSeconds(efforts: readonly Effort[]): number {
  const t = efforts.map((e) => e.elapsed_s).sort((a, b) => a - b);
  const mid = Math.floor(t.length / 2);
  if (t.length === 0) return 0;
  return Math.round(t.length % 2 === 1 ? (t[mid] ?? 0) : ((t[mid - 1] ?? 0) + (t[mid] ?? 0)) / 2);
}

export interface Summary {
  pr: Effort;
  medianS: number;
  latest: Effort;
  year: number;
  yearCount: number;
  yearBestS: number | null;
}

/** Summary strip figures; null without efforts. `year` is the "This year" calendar year. */
export function summarize(efforts: readonly Effort[], year: number): Summary | null {
  const [pr] = sortEfforts(efforts, "fastest");
  const [latest] = sortEfforts(efforts, "newest");
  if (!pr || !latest) return null;
  const thisYear = efforts.filter((e) => yearOf(e.start_t) === year);
  return {
    pr,
    medianS: medianSeconds(efforts),
    latest,
    year,
    yearCount: thisYear.length,
    yearBestS: thisYear.length ? Math.min(...thisYear.map((e) => e.elapsed_s)) : null,
  };
}

/** Meta line: "2.40 km · 8 efforts · first ridden 4 May 2019". */
export function metaLine(data: SegmentData): string {
  const km = (data.ref_length_m / 1000).toFixed(2);
  const n = data.efforts.length;
  const first = sortEfforts(data.efforts, "newest").at(-1);
  const parts = [`${km} km`, `${n} ${n === 1 ? "effort" : "efforts"}`];
  if (first) parts.push(`first ridden ${formatDate(first.start_t)}`);
  return parts.join(" · ");
}

/** aria-label of the chart canvas (contract: contains "PR m:ss"). */
export function chartLabel(efforts: readonly Effort[]): string {
  const s = summarize(efforts, 0);
  const oldest = sortEfforts(efforts, "newest").at(-1);
  if (!s || !oldest) return "No efforts";
  const from = yearOf(oldest.start_t);
  const to = yearOf(s.latest.start_t);
  const range = from === to ? `in ${from}` : `from ${from} to ${to}`;
  return `Elapsed time for ${efforts.length} ${efforts.length === 1 ? "effort" : "efforts"} ${range}; PR ${formatDuration(s.pr.elapsed_s)} on ${formatDate(s.pr.start_t)}`;
}

export interface ChartPoint {
  x: number; // epoch ms
  y: number; // elapsed seconds
  ride: string;
}

export interface ChartModel {
  efforts: ChartPoint[]; // without the PR
  pr: ChartPoint;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  yStep: number;
  years: number[]; // x ticks at Jan 1 of these years
}

const STEPS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];

/** Chart data: efforts as points, the PR separate; axis ranges padded to round steps (~5 y ticks). */
export function chartModel(efforts: readonly Effort[]): ChartModel | null {
  const s = summarize(efforts, 0);
  if (!s) return null;
  const toPoint = (e: Effort): ChartPoint => ({
    x: e.start_t * 1000,
    y: e.elapsed_s,
    ride: e.ride_name,
  });
  const times = efforts.map((e) => e.elapsed_s);
  const lo = Math.min(...times);
  const hi = Math.max(...times);
  const yStep = STEPS.find((st) => (hi - lo) / st <= 4) ?? 7200;
  const yMin = Math.max(0, Math.floor((lo - yStep * 0.25) / yStep) * yStep);
  let yMax = Math.ceil((hi + yStep * 0.25) / yStep) * yStep;
  if (yMax <= yMin) yMax = yMin + yStep;
  const firstYear = yearOf(Math.min(...efforts.map((e) => e.start_t)));
  const lastYear = yearOf(Math.max(...efforts.map((e) => e.start_t)));
  const years: number[] = [];
  for (let y = firstYear; y <= lastYear + 1; y++) years.push(y);
  const prIndex = efforts.indexOf(s.pr);
  return {
    efforts: efforts.filter((_, i) => i !== prIndex).map(toPoint),
    pr: toPoint(s.pr),
    xMin: Date.UTC(firstYear, 0, 1),
    xMax: Date.UTC(lastYear + 1, 0, 1),
    yMin,
    yMax,
    yStep,
    years,
  };
}
