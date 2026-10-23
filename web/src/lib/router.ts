// Hash routing (docs/ARCHITECTURE.md D-005): #/ , #/segment/<slug> , #/ride/<id>.
// GitHub Pages has no SPA rewrites, so everything after "#" is ours.

export type Route =
  | { page: "index" }
  | { page: "segment"; slug: string }
  | { page: "ride"; id: string }
  | { page: "not-found"; path: string };

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ID = /^[0-9]+$/;

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  if (path === "/") return { page: "index" };
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
