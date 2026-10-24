import { cell, dataTable, emptyState, panel, tableRow } from "../lib/components";
import { fetchJson } from "../lib/data";
import { h } from "../lib/dom";
import { formatDate, formatDuration, formatKm } from "../lib/format";
import { splitRides, type IndexData, type IndexRide, type IndexSegment } from "../lib/index-data";
import { parseRoute, rideHref, segmentHref } from "../lib/router";

// Index page (REQ-006, docs/DESIGN.md "Index"): segment list and ride list.

const RIDES_SHOWN = 50;

function segmentRow(s: IndexSegment): HTMLElement {
  const hasPr = s.pr_s !== null;
  return tableRow([
    cell(h("a", { href: segmentHref(s.slug) }, s.name), { className: "cell-name" }),
    cell(String(s.efforts), { numeric: true }),
    cell(
      hasPr
        ? h(
            "span",
            {},
            h("span", { class: "pr-time" }, formatDuration(s.pr_s ?? 0)),
            h("span", { class: "pr-tag" }, "PR"),
          )
        : h(
            "span",
            { class: "muted" },
            h("span", { "aria-hidden": "true" }, "—"),
            h("span", { class: "visually-hidden" }, "no PR yet"),
          ),
      { numeric: true },
    ),
    cell(s.pr_date ? formatDate(s.pr_date) : h("span", { class: "muted" }, "—")),
  ]);
}

function segmentsPanel(segments: IndexSegment[]): HTMLElement {
  const sorted = [...segments].sort((a, b) => a.name.localeCompare(b.name, "sk"));
  if (sorted.length === 0) {
    return panel("segments-h", "Segments", [
      emptyState(
        h("p", {}, "No segments defined yet."),
        h(
          "p",
          {},
          "Add one with ",
          h("code", {}, "sdash segment add"),
          ", then rebuild the site data.",
        ),
      ),
    ]);
  }
  return panel("segments-h", "Segments", [
    dataTable(
      "segments-h",
      [
        { label: "Name" },
        { label: "Efforts", numeric: true },
        { label: "PR time", numeric: true },
        { label: "PR date" },
      ],
      sorted.map(segmentRow),
    ),
  ]);
}

function rideRow(r: IndexRide): HTMLElement {
  return tableRow([
    cell(formatDate(r.date)),
    cell(h("a", { href: rideHref(r.id) }, r.name), { className: "cell-name" }),
    cell(formatKm(r.km), { numeric: true }),
    cell(String(r.n_efforts), { numeric: true }),
  ]);
}

function ridesPanel(rides: IndexRide[]): HTMLElement {
  if (rides.length === 0) {
    return panel("rides-h", "Rides", [emptyState(h("p", {}, "No rides yet."))]);
  }
  const { shown, rest, showAllLabel } = splitRides(rides, RIDES_SHOWN);
  const table = dataTable(
    "rides-h",
    [
      { label: "Date" },
      { label: "Name" },
      { label: "km", numeric: true },
      { label: "Matched", numeric: true },
    ],
    shown.map(rideRow),
  );
  const body: (Node | null)[] = [table];
  if (showAllLabel) {
    const button = h("button", { type: "button", class: "button" }, showAllLabel);
    button.addEventListener("click", () => {
      const tbody = table.querySelector("tbody");
      if (!tbody) return;
      const extra = rest.map(rideRow);
      tbody.append(...extra);
      button.parentElement?.remove();
      extra[0]?.querySelector("a")?.focus();
    });
    body.push(h("div", { class: "panel__foot" }, button));
  }
  return panel("rides-h", "Rides", body);
}

export function renderIndexData(root: HTMLElement, data: IndexData, focusRides = false): void {
  const rides = ridesPanel(data.rides);
  rides.id = "rides";
  root.replaceChildren(h("h1", {}, "Segments"), segmentsPanel(data.segments), rides);
  if (focusRides) rides.scrollIntoView();
}

export function renderIndex(root: HTMLElement, focusRides = false): void {
  root.replaceChildren(h("h1", {}, "Segments"), h("p", { "aria-live": "polite" }, "Loading…"));
  fetchJson<IndexData>("index.json").then(
    (data) => {
      // A newer navigation may have replaced the page meanwhile.
      const page = parseRoute(window.location.hash).page;
      if (page === "index" || page === "rides") renderIndexData(root, data, focusRides);
    },
    () => {
      root.replaceChildren(
        h("h1", {}, "Segments"),
        h(
          "p",
          { role: "status" },
          "Could not load the data. Check your connection and reload the page.",
        ),
      );
    },
  );
}
