import { test, type Locator, type Page, type Route } from "@playwright/test";

/**
 * Not-yet-implemented acceptance test: registered as `test.fixme` (reported as skipped) so CI stays
 * green while signalling "not done". The task that implements the REQ replaces `fixme(` with
 * `test(`. Set ACCEPTANCE_RUN_ALL=1 to run fixme tests anyway (they must fail before the feature).
 */
export const fixme = process.env.ACCEPTANCE_RUN_ALL ? test : test.fixme;

/** Cells of a row whose text matches `re`. Assert per cell: a row's text joins cells without spaces. */
export function cellsMatching(row: Locator, re: RegExp): Locator {
  return row.getByRole("cell").filter({ hasText: re });
}

/** Regex matching a whole cell text exactly (ignoring surrounding whitespace). */
export function exactly(text: string): RegExp {
  return new RegExp(`^\\s*${text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}\\s*$`);
}

/** Open a hash route of the built site, e.g. open(page, "/segment/hill-road-climb"). */
export async function open(page: Page, route: string): Promise<void> {
  await page.goto(`./#${route}`);
}

/** Serve index.json with its segment list emptied (index empty state). */
export async function withNoSegments(page: Page): Promise<void> {
  await page.route("**/data/index.json", async (route: Route) => {
    const response = await route.fetch();
    const json = await response.json();
    await route.fulfill({ response, json: { ...json, segments: [] } });
  });
}

/** Number of canvas pixels close to the PR orange #FC4C02 (docs/DESIGN.md --orange). */
export function orangePixels(canvas: HTMLCanvasElement): number {
  const ctx = canvas.getContext("2d");
  if (!ctx || canvas.width === 0 || canvas.height === 0) return 0;
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  let n = 0;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i] ?? 0;
    const g = data[i + 1] ?? 0;
    const b = data[i + 2] ?? 0;
    const a = data[i + 3] ?? 0;
    if (a > 200 && Math.abs(r - 252) < 16 && Math.abs(g - 76) < 20 && b < 40) n += 1;
  }
  return n;
}
