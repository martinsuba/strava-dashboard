// Shared UI parts (docs/DESIGN.md "Layout"): panels, tables, buttons. Built with h(): no innerHTML.
import { h } from "./dom";

/** White bordered panel with a heading row. `labelId` is the id of its h2 (tables use aria-labelledby). */
export function panel(
  labelId: string,
  title: string,
  body: (Node | null)[],
  controls?: Node,
): HTMLElement {
  return h(
    "section",
    { class: "panel", "aria-labelledby": labelId },
    h("div", { class: "panel__head" }, h("h2", { id: labelId }, title), controls),
    ...body,
  );
}

export interface Column {
  label: string;
  numeric?: boolean;
}

/** Cell content; `numeric` right-aligns it, `className` adds styling classes. */
export interface Cell {
  content: Node | string;
  numeric?: boolean;
  className?: string;
}

export function cell(content: Node | string, opts: Omit<Cell, "content"> = {}): Cell {
  return { content, ...opts };
}

export function tableRow(cells: Cell[]): HTMLElement {
  return h(
    "tr",
    {},
    ...cells.map((c) => {
      const cls = [c.numeric ? "num" : "", c.className ?? ""].filter(Boolean).join(" ");
      return h("td", cls ? { class: cls } : {}, c.content);
    }),
  );
}

/** A real table named by the panel heading, inside an overflow-x box. */
export function dataTable(labelId: string, columns: Column[], rows: HTMLElement[]): HTMLElement {
  const head = h(
    "tr",
    {},
    ...columns.map((c) =>
      h("th", c.numeric ? { scope: "col", class: "num" } : { scope: "col" }, c.label),
    ),
  );
  return h(
    "div",
    { class: "table-scroll" },
    h("table", { "aria-labelledby": labelId }, h("thead", {}, head), h("tbody", {}, ...rows)),
  );
}

export function emptyState(...content: (Node | string)[]): HTMLElement {
  return h("div", { class: "empty-state" }, ...content);
}
