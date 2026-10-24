import "./styles/main.css";
import { renderIndex } from "./pages/index";
import { renderNotFound } from "./pages/not-found";
import { renderRide } from "./pages/ride";
import { renderSegment } from "./pages/segment";
import { runCleanups } from "./lib/cleanup";
import { parseRoute, type Route } from "./lib/router";

/** Segments is current on the index and segment pages, Rides on the rides shortcut and ride pages. */
function markActiveNav(page: Route["page"]): void {
  const active =
    page === "rides" || page === "ride" ? "rides" : page === "not-found" ? "" : "segments";
  for (const link of document.querySelectorAll<HTMLAnchorElement>(".site-nav a")) {
    if (link.dataset["nav"] === active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function render(): void {
  const root = document.getElementById("app");
  if (!root) return;
  runCleanups();
  const route = parseRoute(window.location.hash);
  switch (route.page) {
    case "index":
      renderIndex(root);
      break;
    case "rides":
      renderIndex(root, true);
      break;
    case "segment":
      renderSegment(root, route.slug);
      break;
    case "ride":
      renderRide(root, route.id);
      break;
    case "not-found":
      renderNotFound(root);
      break;
  }
  markActiveNav(route.page);
  if (route.page !== "rides") window.scrollTo(0, 0);
}

window.addEventListener("hashchange", render);
render();

// Hash routing owns the URL fragment, so the skip link focuses <main> instead of navigating.
document.querySelector(".skip-link")?.addEventListener("click", (event) => {
  event.preventDefault();
  document.getElementById("app")?.focus();
});
