import { h } from "../lib/dom";

// docs/DESIGN.md "Not found": h1 "Not found" + link back to the index.
export function renderNotFound(root: HTMLElement): void {
  root.replaceChildren(
    h(
      "div",
      { class: "page-head" },
      h("h1", {}, "Not found"),
      h("p", { class: "meta" }, "There is nothing at this address."),
    ),
    h(
      "p",
      {},
      h(
        "a",
        { href: "#/", class: "back-link" },
        h("span", { "aria-hidden": "true" }, "← "),
        "Back to all segments",
      ),
    ),
  );
}
