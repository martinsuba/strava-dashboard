import { h } from "../lib/dom";

// Placeholder (harness). T-010 builds the Ride page: REQ-008, docs/DESIGN.md "Ride page".
export function renderRide(root: HTMLElement, id: string): void {
  root.replaceChildren(
    h("h1", {}, "Ride"),
    h("p", { class: "meta" }, `Ride page for ${id}: not built yet.`),
  );
}
