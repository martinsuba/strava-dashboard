// REQ-007: Segment page. Data: tests/acceptance/web/site-data/segments/hill-road-climb.json (8 efforts)
// and quarry-descent.json (none). UI contract (docs/TESTS.md): tables named "All efforts" and
// "By year"; the trend chart is a <canvas> with an aria-label containing "PR m:ss".
import { expect, test } from "@playwright/test";
import { open, orangePixels } from "./helpers";

const HILL = "/segment/hill-road-climb";
const BY_TIME = ["5:41", "5:55", "6:05", "6:12", "6:17", "6:19", "6:35", "7:36"];
const BY_DATE = [
  "18 Oct 2026",
  "7 Jun 2026",
  "4 May 2025",
  "12 Jun 2024",
  "10 Sep",
  "13 Jun 2021",
  "19 Jul 2020",
  "4 May 2019",
];

test.describe("REQ-007 segment page", { tag: "@REQ-007" }, () => {
  test("REQ-007: table lists every effort with date and elapsed time", async ({ page }) => {
    await open(page, HILL);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hill Road climb");
    const rows = page.getByRole("table", { name: "All efforts" }).locator("tbody tr");
    await expect(rows).toHaveCount(8);
    const pairs: [string, string][] = [
      ["12 Jun 2024", "5:41"],
      ["7 Jun 2026", "5:55"],
      ["4 May 2019", "7:36"],
      ["4 May 2025", "6:17"],
    ];
    for (const [date, time] of pairs) {
      await expect(rows.filter({ hasText: date })).toContainText(time);
    }
  });

  test("REQ-007: each effort shows ride name, average speed, rank and gap to PR", async ({
    page,
  }) => {
    await open(page, HILL);
    const rows = page.getByRole("table", { name: "All efforts" }).locator("tbody tr");
    const fourth = rows.nth(3); // default sort: by time
    await expect(fourth).toContainText("Evening spin");
    await expect(fourth).toContainText("6:12");
    await expect(fourth).toContainText("23.2");
    await expect(fourth).toContainText("0:31");
    await expect(fourth.getByRole("cell").first()).toHaveText(/^\s*4\s*$/);
    const last = rows.nth(7);
    await expect(last).toContainText("Morning loop");
    await expect(last).toContainText("18.9");
    await expect(last).toContainText("1:55");
    await expect(last.getByRole("cell").first()).toHaveText(/^\s*8\s*$/);
    await expect(rows.nth(0)).toContainText("Hill repeats");
    await expect(rows.nth(0)).toContainText("25.3");
  });

  test("REQ-007: sortable by time (default) and by date", async ({ page }) => {
    await open(page, HILL);
    const rows = page.getByRole("table", { name: "All efforts" }).locator("tbody tr");
    for (const [i, time] of BY_TIME.entries()) await expect(rows.nth(i)).toContainText(time);
    await page.getByRole("button", { name: /newest|date/i }).click();
    for (const [i, date] of BY_DATE.entries()) await expect(rows.nth(i)).toContainText(date);
    await expect(rows.nth(0)).toContainText("6:05");
    await page.getByRole("button", { name: /fastest|time/i }).click();
    for (const [i, time] of BY_TIME.entries()) await expect(rows.nth(i)).toContainText(time);
  });

  test("REQ-007: top three efforts are marked PR, 2nd and 3rd", async ({ page }) => {
    await open(page, HILL);
    const rows = page.getByRole("table", { name: "All efforts" }).locator("tbody tr");
    await expect(rows.nth(0).getByRole("cell").first()).toHaveText(/^\s*PR\s*$/);
    await expect(rows.nth(1).getByRole("cell").first()).toHaveText(/^\s*2nd\s*$/);
    await expect(rows.nth(2).getByRole("cell").first()).toHaveText(/^\s*3rd\s*$/);
    await expect(
      rows
        .nth(3)
        .getByRole("cell")
        .filter({ hasText: /\bPR\b|2nd|3rd/ }),
    ).toHaveCount(0);
    // the marks follow the effort, not the row position
    await page.getByRole("button", { name: /newest|date/i }).click();
    await expect(rows.filter({ hasText: "12 Jun 2024" }).getByRole("cell").first()).toHaveText(
      /^\s*PR\s*$/,
    );
  });

  test("REQ-007: chart of elapsed time against date with the PR highlighted", async ({ page }) => {
    await open(page, HILL);
    const chart = page.locator("canvas").first();
    await expect(chart).toBeVisible();
    await expect(chart).toHaveAttribute("aria-label", /PR 5:41/);
    const box = await chart.boundingBox();
    expect(box && box.width > 200 && box.height > 120).toBeTruthy();
    // PR dot drawn in --orange (#FC4C02); normal efforts are grey
    await expect.poll(() => chart.evaluate(orangePixels), { timeout: 5_000 }).toBeGreaterThan(20);
  });

  test("REQ-007: summary shows effort count and best time per year", async ({ page }) => {
    await open(page, HILL);
    const years = page.getByRole("table", { name: "By year" }).locator("tbody tr");
    await expect(years).toHaveCount(7);
    const expected: [string, string, string][] = [
      ["2026", "2", "5:55"],
      ["2025", "1", "6:17"],
      ["2024", "1", "5:41"],
      ["2019", "1", "7:36"],
    ];
    for (const [year, count, best] of expected) {
      const row = years.filter({ hasText: year });
      await expect(row.getByRole("cell").nth(1)).toHaveText(new RegExp(`^\\s*${count}\\s*$`));
      await expect(row).toContainText(best);
    }
  });

  test("REQ-007: a segment with no efforts says so instead of an empty table or chart", async ({
    page,
  }) => {
    await open(page, "/segment/quarry-descent");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Quarry descent");
    await expect(page.getByText(/no efforts/i)).toBeVisible();
    await expect(page.locator("canvas")).toHaveCount(0);
    await expect(page.getByRole("table")).toHaveCount(0);
  });
  // T-016: chart fixture ridge-track (8 efforts, Oct 2019 - May 2021, one at 13:00 above the cap).
  // Not listed on the index; opened by URL. Plot area exposed as data-plot-left / data-plot-right
  // (CSS px, canvas-relative) so that the drawn dot can be compared with its date.
  test("REQ-007: the PR dot is drawn within the horizontal band of its date's year", async ({
    page,
  }) => {
    await open(page, "/segment/ridge-track");
    const chart = page.locator("canvas").first();
    await expect(chart).toHaveAttribute("aria-label", /PR 4:50/);
    // PR is on 20 Jun 2020; x axis runs 1 Jan 2019 - 1 Jan 2022, i.e. 2020 is the middle third.
    // Poll: the dot must be there once the animation is over and must stay there.
    const measure = (): Promise<number> =>
      chart.evaluate((c: HTMLCanvasElement) => {
        const ctx = c.getContext("2d");
        if (!ctx) return -1;
        const dpr = c.width / c.getBoundingClientRect().width;
        const { data } = ctx.getImageData(0, 0, c.width, c.height);
        let minX = Infinity;
        for (let y = 0; y < c.height; y++) {
          for (let x = 0; x < c.width; x++) {
            const i = (y * c.width + x) * 4;
            const r = data[i] ?? 0;
            const g = data[i + 1] ?? 0;
            const b = data[i + 2] ?? 0;
            if (
              (data[i + 3] ?? 0) > 200 &&
              Math.abs(r - 252) < 16 &&
              Math.abs(g - 76) < 20 &&
              b < 40
            ) {
              minX = Math.min(minX, x);
              break;
            }
          }
        }
        const left = Number(c.dataset["plotLeft"]);
        const right = Number(c.dataset["plotRight"]);
        // leftmost orange pixel = dot centre - radius 8; fraction of the plot width
        return ((minX / dpr + 8 - left) / (right - left)) as number;
      });
    await expect.poll(measure, { timeout: 5_000 }).toBeGreaterThan(1 / 3);
    await expect.poll(measure, { timeout: 5_000 }).toBeLessThan(2 / 3);
    await page.waitForTimeout(1_000);
    expect(await measure()).toBeGreaterThan(1 / 3);
    expect(await measure()).toBeLessThan(2 / 3);
  });

  // T-016: a resize right after mount (Playwright's full-page capture resizes the viewport to the page
  // height) must not leave any dot away from its date. data-dot-error = largest horizontal distance
  // in CSS px between a drawn dot (all datasets) and where the x scale puts its date.
  for (const trigger of ["full-page screenshot", "taller viewport"] as const) {
    test(`REQ-007: every dot stays at its date after a resize right after mount (${trigger})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await open(page, "/segment/ridge-track");
      const chart = page.locator("canvas").first();
      await expect(chart).toBeVisible();
      // record the worst error over every frame drawn from now on (an animation would show here)
      await chart.evaluate((c) => {
        const w = window as unknown as { worstDotError: number };
        w.worstDotError = 0;
        new MutationObserver(() => {
          w.worstDotError = Math.max(w.worstDotError, Number(c.dataset["dotError"]));
        }).observe(c, { attributes: true, attributeFilter: ["data-dot-error"] });
      });
      if (trigger === "full-page screenshot") await page.screenshot({ fullPage: true });
      else await page.setViewportSize({ width: 1280, height: 2400 });
      const error = (): Promise<number> => chart.evaluate((c) => Number(c.dataset["dotError"]));
      const worst = (): Promise<number> =>
        page.evaluate(() => (window as unknown as { worstDotError: number }).worstDotError);
      expect(await error()).toBeLessThan(1);
      await page.waitForTimeout(1_200);
      expect(await error()).toBeLessThan(1);
      expect(await worst()).toBeLessThan(1);
    });
  }

  test("REQ-007: the panel header and the chart label state the efforts above the cap", async ({
    page,
  }) => {
    await open(page, "/segment/ridge-track");
    await expect(page.getByText("1 slower effort above the cap")).toBeVisible();
    await expect(page.locator("canvas").first()).toHaveAttribute(
      "aria-label",
      /1 slower effort above the cap/,
    );
    // a segment without such efforts says nothing about a cap
    await open(page, HILL);
    await expect(page.getByText(/above the cap/)).toHaveCount(0);
    await expect(page.locator("canvas").first()).not.toHaveAttribute("aria-label", /cap/);
  });

  test("REQ-007: the segment median equals the ride page median", async ({ page }) => {
    await open(page, HILL);
    const cell = page.getByRole("region", { name: "Summary" }).locator(".summary__cell", {
      hasText: "Median",
    });
    await expect(cell).toContainText("6:14");
    await open(page, "/ride/3000000106");
    const row = page
      .getByRole("table", { name: "Segments on this ride" })
      .locator("tbody tr")
      .filter({ hasText: "Hill Road climb" });
    await expect(row).toContainText("6:14");
  });
});
