import { h } from "../lib/dom";

// Placeholder (harness). T-008 builds the Index page: REQ-006, docs/DESIGN.md "Index".
export function renderIndex(root: HTMLElement): void {
  root.replaceChildren(h("h1", {}, "Segment Log"), h("p", {}, "Index page: not built yet."));
}
