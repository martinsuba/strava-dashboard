import { renderIndex } from "./pages/index";
import { renderNotFound } from "./pages/not-found";
import { renderRide } from "./pages/ride";
import { renderSegment } from "./pages/segment";
import { parseRoute } from "./lib/router";

function render(): void {
  const root = document.getElementById("app");
  if (!root) return;
  const route = parseRoute(window.location.hash);
  switch (route.page) {
    case "index":
      renderIndex(root);
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
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", render);
render();
