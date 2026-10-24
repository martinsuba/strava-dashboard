import { cell, dataTable, panel, tableRow } from "../lib/components";
import { fetchJson, NotFoundError } from "../lib/data";
import { h } from "../lib/dom";
import { formatDate, formatDuration, formatKm } from "../lib/format";
import type { IndexData } from "../lib/index-data";
import { rideHref } from "../lib/router";
import {
  chartLabel,
  chartModel,
  formatGap,
  metaLine,
  rankLabel,
  sortEfforts,
  summarize,
  yearOf,
  type Effort,
  type SegmentData,
  type SortMode,
  type Summary,
} from "../lib/segment-data";
import { renderNotFound } from "./not-found";

// Segment page (REQ-007, docs/DESIGN.md "Segment page"): summary strip, "Time by date" chart,
// "All efforts" (rank, sort, gap to PR) and "By year".

export type { Effort, SegmentData } from "../lib/segment-data";

const EFFORTS_SHOWN = 12;

function backLink(): HTMLElement {
  return h(
    "a",
    { href: "#/", class: "back-link" },
    h("span", { "aria-hidden": "true" }, "← "),
    "All segments",
  );
}

function summaryCell(label: string, value: string, note: string, pr = false): HTMLElement {
  return h(
    "div",
    { class: "summary__cell" },
    h("span", { class: "summary__label" }, label),
    h("span", { class: pr ? "summary__value summary__value--pr" : "summary__value" }, value),
    h("span", { class: "summary__note" }, note),
  );
}

function summaryStrip(s: Summary): HTMLElement {
  const prS = s.pr.elapsed_s;
  const gap = (seconds: number): string => `${formatGap(seconds - prS)} to PR`;
  return h(
    "section",
    { class: "summary", "aria-label": "Summary" },
    summaryCell(
      "Personal record",
      formatDuration(prS),
      `${formatDate(s.pr.start_t)} · ${formatKm(s.pr.avg_kmh)} km/h`,
      true,
    ),
    summaryCell("Median", formatDuration(s.medianS), gap(s.medianS)),
    summaryCell(
      "Latest",
      formatDuration(s.latest.elapsed_s),
      `${formatDate(s.latest.start_t)} · ${gap(s.latest.elapsed_s)}`,
    ),
    summaryCell(
      `This year (${s.year})`,
      String(s.yearCount),
      s.yearBestS === null ? "efforts" : `efforts · best ${formatDuration(s.yearBestS)}`,
    ),
  );
}

function chartPanel(efforts: Effort[]): { node: HTMLElement; canvas: HTMLCanvasElement } {
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", chartLabel(efforts));
  const hint = h(
    "span",
    { class: "chart-hint" },
    "faster is higher · ",
    h("span", { class: "chart-hint__dot", "aria-hidden": "true" }, "●"),
    " PR",
  );
  const node = panel(
    "trend-h",
    "Time by date",
    [h("div", { class: "chart-box" }, h("div", { class: "chart-box__inner" }, canvas))],
    hint,
  );
  return { node, canvas };
}

function badge(rank: number): HTMLElement {
  const cls = rank <= 3 ? `badge badge--${rank === 1 ? "pr" : rank}` : "badge badge--n";
  return h("span", { class: cls }, rankLabel(rank));
}

function effortRow(e: Effort): HTMLElement {
  return tableRow([
    cell(badge(e.rank)),
    cell(formatDate(e.start_t)),
    cell(h("a", { href: rideHref(e.activity_id) }, e.ride_name), { className: "cell-name" }),
    cell(formatDuration(e.elapsed_s), { numeric: true }),
    cell(formatKm(e.avg_kmh), { numeric: true, className: "muted" }),
    cell(formatGap(e.gap_to_pr_s), { numeric: true, className: "muted" }),
  ]);
}

function effortsPanel(efforts: Effort[]): HTMLElement {
  let mode: SortMode = "fastest";
  let showAll = efforts.length <= EFFORTS_SHOWN;

  const table = dataTable(
    "efforts-h",
    [
      { label: "Rank" },
      { label: "Date" },
      { label: "Ride" },
      { label: "Time", numeric: true },
      { label: "km/h", numeric: true },
      { label: "Gap", numeric: true },
    ],
    [],
  );
  const tbody = table.querySelector("tbody");
  const foot = h("div", { class: "panel__foot" });
  const showAllButton = h(
    "button",
    { type: "button", class: "button" },
    `Show all ${efforts.length} efforts`,
  );
  foot.append(showAllButton);

  const fastest = h("button", { type: "button", "aria-pressed": "true" }, "Fastest");
  const newest = h("button", { type: "button", "aria-pressed": "false" }, "Newest");
  const toggle = h(
    "div",
    { class: "toggle", role: "group", "aria-label": "Sort efforts" },
    fastest,
    newest,
  );

  const draw = (): void => {
    const sorted = sortEfforts(efforts, mode);
    tbody?.replaceChildren(...(showAll ? sorted : sorted.slice(0, EFFORTS_SHOWN)).map(effortRow));
    fastest.setAttribute("aria-pressed", String(mode === "fastest"));
    newest.setAttribute("aria-pressed", String(mode === "newest"));
    foot.hidden = showAll;
  };
  fastest.addEventListener("click", () => {
    mode = "fastest";
    draw();
  });
  newest.addEventListener("click", () => {
    mode = "newest";
    draw();
  });
  showAllButton.addEventListener("click", () => {
    const shown = tbody?.rows.length ?? 0;
    showAll = true;
    draw();
    tbody?.rows[shown]?.querySelector("a")?.focus();
  });
  draw();

  const node = panel("efforts-h", "All efforts", [table, foot], toggle);
  node.classList.add("panel--efforts");
  return node;
}

function yearsPanel(data: SegmentData, prS: number): HTMLElement {
  const rows = [...data.per_year]
    .sort((a, b) => b.year - a.year)
    .map((y) =>
      tableRow([
        cell(String(y.year)),
        cell(String(y.count), { numeric: true }),
        cell(formatDuration(y.best_s), {
          numeric: true,
          className: y.best_s === prS ? "best-pr" : "",
        }),
      ]),
    );
  const node = panel("years-h", "By year", [
    dataTable(
      "years-h",
      [{ label: "Year" }, { label: "Efforts", numeric: true }, { label: "Best", numeric: true }],
      rows,
    ),
  ]);
  node.classList.add("panel--years");
  return node;
}

/**
 * Render the page. `year` is the calendar year behind "This year": that of index.json `generated`
 * (so a build is reproducible and tests need no clock); the caller falls back to the latest effort.
 */
export function renderSegmentData(root: HTMLElement, data: SegmentData, year?: number): void {
  const head = h(
    "div",
    { class: "page-head" },
    backLink(),
    h("h1", {}, data.name),
    h("p", { class: "meta" }, metaLine(data)),
  );
  const model = chartModel(data.efforts);
  const first = sortEfforts(data.efforts, "newest")[0];
  const s = summarize(data.efforts, year ?? (first ? yearOf(first.start_t) : 0));
  if (!model || !s) {
    root.replaceChildren(head, h("p", {}, "No efforts on this segment yet."));
    return;
  }
  const chart = chartPanel(data.efforts);
  root.replaceChildren(
    head,
    summaryStrip(s),
    chart.node,
    h("div", { class: "split" }, effortsPanel(data.efforts), yearsPanel(data, s.pr.elapsed_s)),
  );
  // Chart.js is a separate chunk, loaded only on this page; the table and summary show meanwhile.
  void import("../lib/segment-chart").then(({ mountSegmentChart }) => {
    if (chart.canvas.isConnected) mountSegmentChart(chart.canvas, model, data.efforts);
  });
}

async function generatedYear(): Promise<number | undefined> {
  try {
    const index = await fetchJson<IndexData>("index.json");
    const t = Date.parse(index.generated);
    return Number.isNaN(t) ? undefined : yearOf(t / 1000);
  } catch {
    return undefined;
  }
}

export function renderSegment(root: HTMLElement, slug: string): void {
  void import("../lib/segment-chart").then(({ disposeSegmentChart }) => disposeSegmentChart());
  const status = (text: string): void =>
    root.replaceChildren(
      h("h1", {}, "Segment"),
      h("p", { role: "status", "aria-live": "polite" }, text),
      h("p", {}, backLink()),
    );
  root.replaceChildren(h("h1", {}, "Segment"), h("p", { "aria-live": "polite" }, "Loading…"));
  Promise.all([fetchJson<SegmentData>(`segments/${slug}.json`), generatedYear()]).then(
    ([data, year]) => {
      // A newer navigation may have replaced the page meanwhile.
      if (window.location.hash.endsWith(`/segment/${slug}`)) renderSegmentData(root, data, year);
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
