import { h } from "../lib/dom";

// docs/DESIGN.md "Not found": h1 "Not found" + link back to the index.
export function renderNotFound(root: HTMLElement): void {
  root.replaceChildren(
    h("h1", {}, "Not found"),
    h("p", {}, "There is nothing at this address."),
    h("p", {}, h("a", { href: "#/" }, "← Back to all segments")),
  );
}
