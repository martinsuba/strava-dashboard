import { cell, dataTable, emptyState, panel, tableRow } from "../lib/components";
import { fetchJson, NotFoundError } from "../lib/data";
import { h } from "../lib/dom";
import { formatDateTime, formatDuration, formatKm } from "../lib/format";
import {
  barPositions,
  newPrCount,
  prMark,
  rankOf,
  type RideData,
  type RideEffort,
} from "../lib/ride-data";
import { isCurrentRoute, segmentHref } from "../lib/router";
import { formatGap } from "../lib/segment-data";
import { renderNotFound } from "./not-found";

// Ride page (REQ-008, docs/DESIGN.md "Ride page", docs/design/ride-page.dc.html).

function backLink(): HTMLElement {
  return h(
    "a",
    { href: "#/rides", class: "back-link" },
    h("span", { "aria-hidden": "true" }, "← "),
    "All rides",
  );
}

function summaryCell(label: string, value: string, note?: string): HTMLElement {
  return h(
    "div",
    { class: "summary__cell" },
    h("span", { class: "summary__label" }, label),
    h("span", { class: "summary__value summary__value--ride" }, value),
    note ? h("span", { class: "summary__note summary__note--pr" }, note) : null,
  );
}

function summaryStrip(data: RideData): HTMLElement {
  const newPrs = newPrCount(data.efforts);
  return h(
    "section",
    { class: "summary summary--ride", "aria-label": "Ride summary" },
    summaryCell("Distance", `${formatKm(data.km)} km`),
    summaryCell("Moving time", formatDuration(data.moving_s)),
    summaryCell("Elapsed time", formatDuration(data.elapsed_s)),
    summaryCell(
      "Segments",
      String(data.efforts.length),
      newPrs > 0 ? `${newPrs} new PR` : undefined,
    ),
  );
}

function positionBar(e: RideEffort): HTMLElement {
  const { medianPct, todayPct } = barPositions(e);
  const dot = h("span", { class: e.is_pr ? "posbar__dot posbar__dot--pr" : "posbar__dot" });
  dot.style.left = `${todayPct}%`;
  const tick = h("span", { class: "posbar__median" });
  tick.style.left = `${medianPct}%`;
  // Decorative: the same information is in the Today, PR, Median, vs PR and Rank cells.
  return h("span", { class: "posbar", "aria-hidden": "true" }, tick, dot);
}

function effortRow(e: RideEffort): HTMLElement {
  const mark = prMark(e);
  return tableRow([
    cell(
      h(
        "span",
        { class: "seg-cell" },
        h("a", { href: segmentHref(e.slug), title: e.name }, e.name),
        mark ? h("span", { class: "chip-pr" }, mark) : null,
      ),
      { className: "cell-seg" },
    ),
    cell(formatDuration(e.elapsed_s), {
      numeric: true,
      className: e.is_pr ? "today today--pr" : "today",
    }),
    cell(formatDuration(e.pr_s), { numeric: true, className: "muted" }),
    cell(formatDuration(e.median_s), { numeric: true, className: "muted" }),
    cell(formatGap(e.gap_to_pr_s), { numeric: true, className: "muted" }),
    cell(positionBar(e), { className: "cell-bar" }),
    cell(rankOf(e), { numeric: true }),
  ]);
}

function segmentsPanel(efforts: RideEffort[]): HTMLElement {
  const item = (...content: (Node | string)[]): HTMLElement =>
    h("span", { class: "legend__item" }, ...content);
  const legend = h(
    "span",
    { class: "chart-hint legend" },
    item("bar: PR on the left, slowest on the right"),
    item(h("span", { class: "legend-tick", "aria-hidden": "true" }, "|"), " median"),
    item(h("span", { "aria-hidden": "true" }, "●"), " today"),
  );
  const body =
    efforts.length === 0
      ? emptyState("No segments matched on this ride.")
      : dataTable(
          "ride-seg-h",
          [
            { label: "Segment" },
            { label: "Today", numeric: true },
            { label: "PR", numeric: true },
            { label: "Median", numeric: true },
            { label: "vs PR", numeric: true },
            { label: "Where today ranks" },
            { label: "Rank", numeric: true },
          ],
          efforts.map(effortRow),
        );
  const node = panel(
    "ride-seg-h",
    "Segments on this ride",
    [body],
    efforts.length > 0 ? legend : undefined,
  );
  node.classList.add("panel--ride-segments");
  return node;
}

export function renderRideData(root: HTMLElement, data: RideData): void {
  const meta = [formatDateTime(data.date), data.gear].filter(Boolean).join(" · ");
  root.replaceChildren(
    h(
      "div",
      { class: "page-head" },
      backLink(),
      h("h1", {}, data.name),
      h("p", { class: "meta" }, meta),
    ),
    summaryStrip(data),
    segmentsPanel(data.efforts),
  );
}

export function renderRide(root: HTMLElement, id: string): void {
  root.replaceChildren(h("h1", {}, "Ride"), h("p", { "aria-live": "polite" }, "Loading…"));
  fetchJson<RideData>(`rides/${id}.json`).then(
    (data) => {
      // A newer navigation may have replaced the page meanwhile.
      if (isCurrentRoute(window.location.hash, { page: "ride", id })) renderRideData(root, data);
    },
    (err: unknown) => {
      if (!isCurrentRoute(window.location.hash, { page: "ride", id })) return;
      if (err instanceof NotFoundError) renderNotFound(root);
      else
        root.replaceChildren(
          h("h1", {}, "Ride"),
          h(
            "p",
            { role: "status", "aria-live": "polite" },
            "Could not load this ride. Check your connection and reload, or go back to all rides.",
          ),
          h("p", {}, backLink()),
        );
    },
  );
}
