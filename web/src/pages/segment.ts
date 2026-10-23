import { fetchJson, NotFoundError } from "../lib/data";
import { h } from "../lib/dom";
import { formatDate, formatDuration } from "../lib/format";
import { renderNotFound } from "./not-found";

// Minimal Segment page (T-002): the "All efforts" table. T-009 adds summary, chart, ranks, sorting
// and "By year" (REQ-007, docs/DESIGN.md "Segment page").

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

function effortsTable(efforts: Effort[]): HTMLElement {
  const sorted = [...efforts].sort((a, b) => a.elapsed_s - b.elapsed_s || a.start_t - b.start_t);
  const rows = sorted.map((e) =>
    h("tr", {}, h("td", {}, formatDate(e.start_t)), h("td", {}, formatDuration(e.elapsed_s))),
  );
  return h(
    "table",
    {},
    h("caption", {}, "All efforts"),
    h(
      "thead",
      {},
      h("tr", {}, h("th", { scope: "col" }, "Date"), h("th", { scope: "col" }, "Time")),
    ),
    h("tbody", {}, ...rows),
  );
}

export function renderSegmentData(root: HTMLElement, data: SegmentData): void {
  root.replaceChildren(
    h("p", {}, h("a", { href: "#/" }, h("span", { "aria-hidden": "true" }, "← "), "All segments")),
    h("h1", {}, data.name),
    data.efforts.length === 0
      ? h("p", {}, "No efforts on this segment yet.")
      : effortsTable(data.efforts),
  );
}

export function renderSegment(root: HTMLElement, slug: string): void {
  const status = (text: string): void =>
    root.replaceChildren(
      h("h1", {}, "Segment"),
      h("p", { role: "status", "aria-live": "polite" }, text),
      h(
        "p",
        {},
        h("a", { href: "#/" }, h("span", { "aria-hidden": "true" }, "← "), "All segments"),
      ),
    );
  root.replaceChildren(h("h1", {}, "Segment"), h("p", { "aria-live": "polite" }, "Loading…"));
  fetchJson<SegmentData>(`segments/${slug}.json`).then(
    (data) => {
      // A newer navigation may have replaced the page meanwhile.
      if (window.location.hash.endsWith(`/segment/${slug}`)) renderSegmentData(root, data);
    },
    (err: unknown) => {
      if (err instanceof NotFoundError) renderNotFound(root);
      else
        status(
          "Could not load this segment. Check your connection and reload, or go back to all segments.",
        );
    },
  );
}
