// REQ-008: Activity (ride) page. Data: tests/acceptance/web/site-data/rides/*.json. UI contract
// (docs/TESTS.md): matched efforts are in a table named "Segments on this ride"; a PR mark is text
// containing the word "PR" inside a cell (e.g. the "NEW PR" chip); unmarked rows have no such cell.
// Assertions are per cell: a row's text concatenates its cells without spaces.
import { expect, test } from "@playwright/test";
import { cellsMatching, open } from "./helpers";

const PR_MARK = /\bPR\b/;

test.describe("REQ-008 ride page", { tag: "@REQ-008" }, () => {
  test("REQ-008: shows date, name, distance, moving/elapsed time and gear", async ({ page }) => {
    await open(page, "/ride/3000000108");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evening loop");
    const main = page.locator("main");
    await expect(main).toContainText("18 Oct 2026");
    await expect(main).toContainText("42.6");
    await expect(main).toContainText("1:38:12");
    await expect(main).toContainText("1:46:40");
    await expect(main).toContainText("Road bike");
  });

  test("REQ-008: each matched effort shows time, PR, median, gap to PR and rank", async ({
    page,
  }) => {
    await open(page, "/ride/3000000106");
    const table = page.getByRole("table", { name: "Segments on this ride" });
    await expect(table.locator("tbody tr")).toHaveCount(2);
    const hill = table.locator("tbody tr").filter({ hasText: "Hill Road climb" });
    for (const text of ["6:17", "5:41", "6:14", "0:36"]) await expect(hill).toContainText(text);
    await expect(cellsMatching(hill, /^\s*5\s*\/\s*8\s*$/)).toHaveCount(1);
    const lake = table.locator("tbody tr").filter({ hasText: "Lakeside flat" });
    for (const text of ["3:58", "4:12"]) await expect(lake).toContainText(text);
    await expect(cellsMatching(lake, /^\s*1\s*\/\s*3\s*$/)).toHaveCount(1);
    await expect(hill.getByRole("link", { name: "Hill Road climb" })).toHaveAttribute(
      "href",
      /#\/segment\/hill-road-climb$/,
    );
  });

  test("REQ-008: an effort is marked when it is the PR or was the PR at the time", async ({
    page,
  }) => {
    await open(page, "/ride/3000000106");
    let rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
    await expect(cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK)).not.toHaveCount(
      0,
    ); // current PR
    await expect(cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK)).toHaveCount(
      0,
    ); // 5th of 8

    await open(page, "/ride/3000000104"); // 2023: both were PRs at the time, neither is now
    rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
    await expect(
      cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK),
    ).not.toHaveCount(0);
    await expect(cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK)).not.toHaveCount(
      0,
    );

    await open(page, "/ride/3000000108"); // ranks 3/8 and 3/3, never a PR
    rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK)).toHaveCount(
      0,
    );
    await expect(cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK)).toHaveCount(0);
  });

  test("REQ-008: a ride with no matched segments says so", async ({ page }) => {
    await open(page, "/ride/3000000109");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Recovery spin");
    await expect(page.getByText(/no segments matched/i)).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  });
  // Plan v2 criterion: times are Europe/Bratislava time for any viewer (D-007). Ride 3000000108 starts
  // at 15:05Z on 18 Oct 2026 (CEST, UTC+2), so it shows 17:05; the browser runs in New York (11:05 local).
  test.describe("time zone", () => {
    test.use({ timezoneId: "America/New_York" });

    test("REQ-008: a 15:05 UTC ride shows 17:05 whatever the viewer's time zone", async ({
      page,
    }) => {
      await open(page, "/ride/3000000108");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evening loop");
      await expect(page.locator("main")).toContainText("18 Oct 2026, 17:05");
      await expect(page.locator("main")).not.toContainText("11:05");
    });
  });

  // Position bar: track = .posbar (role img), median tick and today's dot are measured in the DOM.
  // Expected fractions come from the fixture JSON, never from pixels.
  test("REQ-008: the position bar runs from PR to slowest with a median tick and today's mark", async ({
    page,
  }) => {
    const fixture = (id: string): Promise<{ efforts: Record<string, number | string>[] }> =>
      page.request.get(`./data/rides/${id}.json`).then((r) => r.json());
    const mmss = (s: number): string => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    const cases = [
      { id: "3000000106", slug: "hill-road-climb", name: "Hill Road climb", today: "mid" },
      { id: "3000000105", slug: "hill-road-climb", name: "Hill Road climb", today: "pr" },
      { id: "3000000101", slug: "hill-road-climb", name: "Hill Road climb", today: "slowest" },
    ];
    for (const c of cases) {
      const e = (await fixture(c.id)).efforts.find((x) => x["slug"] === c.slug);
      if (!e) throw new Error(`fixture ${c.id} has no ${c.slug}`);
      const [today, pr, median, slowest] = ["elapsed_s", "pr_s", "median_s", "slowest_s"].map((k) =>
        Number(e[k]),
      ) as [number, number, number, number];
      const frac = (v: number): number => (v - pr) / (slowest - pr);
      if (c.today === "mid") expect(today > pr && today < slowest).toBe(true);
      if (c.today === "pr") expect(today).toBe(pr);
      if (c.today === "slowest") expect(today).toBe(slowest);

      await open(page, `/ride/${c.id}`);
      const row = page
        .getByRole("table", { name: "Segments on this ride" })
        .locator("tbody tr")
        .filter({ hasText: c.name });
      const bar = row.getByRole("img");
      await expect(bar).toHaveAttribute(
        "aria-label",
        `Today ${mmss(today)}, PR ${mmss(pr)}, median ${mmss(median)}, slowest ${mmss(slowest)}`,
      );
      const track = await bar.boundingBox();
      const tick = await bar.locator(".posbar__median").boundingBox();
      const dot = await bar.locator(".posbar__dot").boundingBox();
      if (!track || !tick || !dot) throw new Error("bar parts not rendered");
      const centre = (b: { x: number; width: number }): number =>
        (b.x + b.width / 2 - track.x) / track.width;
      expect(Math.abs(centre(tick) - frac(median))).toBeLessThan(0.02);
      expect(Math.abs(centre(dot) - frac(today))).toBeLessThan(0.02);
      if (c.today === "pr") expect(centre(dot)).toBeLessThan(0.02);
      if (c.today === "slowest") expect(centre(dot)).toBeGreaterThan(0.98);
    }
    await open(page, "/ride/3000000106");
    const legend = page.locator(".legend");
    await expect(legend).toContainText("bar: PR on the left, slowest on the right");
    await expect(legend).toContainText("median");
    await expect(legend).toContainText("today");
  });
});
