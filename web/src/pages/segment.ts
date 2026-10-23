import { h } from "../lib/dom";

// Placeholder (harness). T-002/T-009 build the Segment page: REQ-007, docs/DESIGN.md "Segment page".
export function renderSegment(root: HTMLElement, slug: string): void {
  root.replaceChildren(
    h("h1", {}, "Segment"),
    h("p", {}, `Segment page for "${slug}": not built yet.`),
  );
}
