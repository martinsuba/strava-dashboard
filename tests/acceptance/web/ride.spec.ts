// REQ-008: Activity (ride) page. Data: tests/fixtures/site-data/rides/*.json. UI contract
// (docs/TESTS.md): matched efforts are in a table named "Segments on this ride"; a PR mark is text
// containing the word "PR" inside a cell (e.g. the "NEW PR" chip); unmarked rows have no such cell.
// Assertions are per cell: a row's text concatenates its cells without spaces.
import { expect, test } from "@playwright/test";
import { cellsMatching, fixme, open } from "./helpers";

const PR_MARK = /\bPR\b/;

test.describe("REQ-008 ride page", { tag: "@REQ-008" }, () => {
  fixme("REQ-008: shows date, name, distance, moving/elapsed time and gear", async ({ page }) => {
    await open(page, "/ride/3000000108");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evening loop");
    const main = page.locator("main");
    await expect(main).toContainText("18 Oct 2026");
    await expect(main).toContainText("42.6");
    await expect(main).toContainText("1:38:12");
    await expect(main).toContainText("1:46:40");
    await expect(main).toContainText("Road bike");
  });

  fixme(
    "REQ-008: each matched effort shows time, PR, average, gap to PR and rank",
    async ({ page }) => {
      await open(page, "/ride/3000000106");
      const table = page.getByRole("table", { name: "Segments on this ride" });
      await expect(table.locator("tbody tr")).toHaveCount(2);
      const hill = table.locator("tbody tr").filter({ hasText: "Hill Road climb" });
      for (const text of ["6:17", "5:41", "6:20", "0:36"]) await expect(hill).toContainText(text);
      await expect(cellsMatching(hill, /^\s*5\s*\/\s*8\s*$/)).toHaveCount(1);
      const lake = table.locator("tbody tr").filter({ hasText: "Lakeside flat" });
      for (const text of ["3:58", "4:10"]) await expect(lake).toContainText(text);
      await expect(cellsMatching(lake, /^\s*1\s*\/\s*3\s*$/)).toHaveCount(1);
      await expect(hill.getByRole("link", { name: "Hill Road climb" })).toHaveAttribute(
        "href",
        /#\/segment\/hill-road-climb$/,
      );
    },
  );

  fixme(
    "REQ-008: an effort is marked when it is the PR or was the PR at the time",
    async ({ page }) => {
      await open(page, "/ride/3000000106");
      let rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
      await expect(
        cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK),
      ).not.toHaveCount(0); // current PR
      await expect(cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK)).toHaveCount(
        0,
      ); // 5th of 8

      await open(page, "/ride/3000000104"); // 2023: both were PRs at the time, neither is now
      rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
      await expect(
        cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK),
      ).not.toHaveCount(0);
      await expect(
        cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK),
      ).not.toHaveCount(0);

      await open(page, "/ride/3000000108"); // ranks 3/8 and 3/3, never a PR
      rows = page.getByRole("table", { name: "Segments on this ride" }).locator("tbody tr");
      await expect(rows).toHaveCount(2);
      await expect(cellsMatching(rows.filter({ hasText: "Hill Road climb" }), PR_MARK)).toHaveCount(
        0,
      );
      await expect(cellsMatching(rows.filter({ hasText: "Lakeside flat" }), PR_MARK)).toHaveCount(
        0,
      );
    },
  );

  fixme("REQ-008: a ride with no matched segments says so", async ({ page }) => {
    await open(page, "/ride/3000000109");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Recovery spin");
    await expect(page.getByText(/no segments matched/i)).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  });
});
