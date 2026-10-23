// Site data lives next to the app: <base>/data/... (copied into web/public/data by sdash build-data,
// or from tests/acceptance/web/site-data for tests). Schema: docs/ARCHITECTURE.md "Site JSON".

export class NotFoundError extends Error {}

export async function fetchJson<T>(relPath: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${relPath}`);
  if (res.status === 404) throw new NotFoundError(relPath);
  if (!res.ok) throw new Error(`GET data/${relPath}: HTTP ${res.status}`);
  return (await res.json()) as T;
}
