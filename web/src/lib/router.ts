// Hash routing (docs/ARCHITECTURE.md D-005): #/ , #/rides (index, scrolled to the rides list), #/segment/<slug> , #/ride/<id>.
// GitHub Pages has no SPA rewrites, so everything after "#" is ours.

export type Route =
  | { page: "index" }
  | { page: "rides" }
  | { page: "segment"; slug: string }
  | { page: "ride"; id: string }
  | { page: "not-found"; path: string };

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ID = /^[0-9]+$/;

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  if (path === "/") return { page: "index" };
  if (path === "/rides") return { page: "rides" };
  const parts = path.split("/").slice(1);
  if (parts.length === 2) {
    const [kind, raw] = parts as [string, string];
    let value: string;
    try {
      value = decodeURIComponent(raw);
    } catch {
      return { page: "not-found", path };
    }
    if (kind === "segment" && SLUG.test(value)) return { page: "segment", slug: value };
    if (kind === "ride" && ID.test(value)) return { page: "ride", id: value };
  }
  return { page: "not-found", path };
}

export function segmentHref(slug: string): string {
  return `#/segment/${encodeURIComponent(slug)}`;
}

export function rideHref(id: string): string {
  return `#/ride/${encodeURIComponent(id)}`;
}

/** True while `hash` still routes to the page being rendered (trailing slash / percent-encoding safe). */
export function isCurrentRoute(
  hash: string,
  expected: { page: "segment"; slug: string } | { page: "ride"; id: string },
): boolean {
  const route = parseRoute(hash);
  if (route.page !== expected.page) return false;
  return route.page === "segment"
    ? expected.page === "segment" && route.slug === expected.slug
    : route.page === "ride" && expected.page === "ride" && route.id === expected.id;
}
