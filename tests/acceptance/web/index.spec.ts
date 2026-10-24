// REQ-006: Index page. Data: tests/acceptance/web/site-data (synthetic). UI contract (docs/TESTS.md):
// the two lists are tables named "Segments" and "Rides" (caption or aria-labelledby the panel
// heading); times m:ss, dates "12 Jun 2024" (UTC), as in docs/DESIGN.md.
import { expect, test } from "@playwright/test";
import { cellsMatching, exactly, open, withNoSegments } from "./helpers";

test.describe("REQ-006 index page", { tag: "@REQ-006" }, () => {
  test("REQ-006: segment list shows name, effort count, PR time and PR date", async ({ page }) => {
    await open(page, "/");
    const table = page.getByRole("table", { name: "Segments" });
    await expect(table.locator("tbody tr")).toHaveCount(3);
    const hill = table.getByRole("row").filter({ hasText: "Hill Road climb" });
    await expect(cellsMatching(hill, exactly("8"))).toHaveCount(1);
    await expect(hill).toContainText("5:41");
    await expect(hill).toContainText("12 Jun 2024");
    const lake = table.getByRole("row").filter({ hasText: "Lakeside flat" });
    await expect(cellsMatching(lake, exactly("3"))).toHaveCount(1);
    await expect(lake).toContainText("3:58");
    await expect(lake).toContainText("4 May 2025");
    const quarry = table.getByRole("row").filter({ hasText: "Quarry descent" });
    await expect(cellsMatching(quarry, exactly("0"))).toHaveCount(1);
  });

  test("REQ-006: ride list shows rides newest first with date, name, distance, segments matched", async ({
    page,
  }) => {
    await open(page, "/");
    const rows = page.getByRole("table", { name: "Rides" }).locator("tbody tr");
    // [date, name, km, segments matched], newest first (values from site-data/index.json)
    const newestFirst: [string, string, string, string][] = [
      ["18 Oct 2026", "Evening loop", "42.6", "2"],
      ["1 Sept? 2026", "Recovery spin", "18.0", "0"],
      ["7 Jun 2026", "Sunday long ride", "88.3", "1"],
      ["4 May 2025", "Gravel detour", "44.1", "2"],
      ["12 Jun 2024", "Hill repeats", "31.2", "1"],
      ["10 Sept? 2023", "Evening spin", "25.5", "2"],
      ["13 Jun 2021", "Hill repeats", "30.8", "1"],
      ["19 Jul 2020", "Hill repeats", "31.0", "1"],
      ["4 May 2019", "Morning loop", "28.4", "1"],
    ];
    await expect(rows).toHaveCount(newestFirst.length);
    for (const [i, [date, name, km, matched]] of newestFirst.entries()) {
      const row = rows.nth(i);
      await expect(cellsMatching(row, new RegExp(`^\\s*(\\w{3} )?${date}\\s*$`))).toHaveCount(1);
      await expect(row.getByRole("link")).toHaveText(name);
      const kmCell = new RegExp(`^\\s*${km.replace(".", "\\.")}(\\s*km)?\\s*$`);
      await expect(cellsMatching(row, kmCell)).toHaveCount(1);
      await expect(row.getByRole("cell").last()).toHaveText(exactly(matched));
    }
  });

  test("REQ-006: clicking a segment opens its page", async ({ page }) => {
    await open(page, "/");
    await page
      .getByRole("table", { name: "Segments" })
      .getByRole("link", { name: "Hill Road climb" })
      .click();
    await expect(page).toHaveURL(/#\/segment\/hill-road-climb$/);
    await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toHaveCount(0);
  });

  test("REQ-006: clicking a ride opens its page", async ({ page }) => {
    await open(page, "/");
    await page
      .getByRole("table", { name: "Rides" })
      .getByRole("link", { name: "Evening loop" })
      .click();
    await expect(page).toHaveURL(/#\/ride\/3000000108$/);
    await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toHaveCount(0);
  });

  test("REQ-006: no segments defined shows an empty state explaining how to add one", async ({
    page,
  }) => {
    await withNoSegments(page);
    await open(page, "/");
    await expect(page.getByText(/sdash segment add/)).toBeVisible();
    await expect(page.getByRole("table", { name: "Rides" }).locator("tbody tr")).toHaveCount(9);
  });
});

test("harness smoke: the built site boots and an unknown route shows Not found", async ({
  page,
}) => {
  await open(page, "/no-such-page");
  await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toBeVisible();
  await page.getByRole("link", { name: /back/i }).click();
  await expect(page).toHaveURL(/#\/$/);
});
