// Screenshots of every screen in docs/PLAN.md "Screens", from the fixture-built site
// (tests/fixtures/site-data, synthetic). Not an acceptance test: it never fails on content, it only
// captures. Output: screenshots/<screen>-<viewport>-<scheme>.png at the repo root.
// The design is light only (docs/DESIGN.md); dark captures check that a dark OS setting does not
// break the page.
import { test, type Page, type Route } from "@playwright/test";
import path from "node:path";

const OUT = path.resolve(__dirname, "../../screenshots");

const VIEWPORTS = {
  mobile: { width: 390, height: 844 },
  desktop: { width: 1280, height: 800 },
} as const;
const SCHEMES = ["light", "dark"] as const;

type Screen = {
  name: string;
  route: string;
  prepare?: (page: Page) => Promise<void>;
  after?: (page: Page) => Promise<void>;
};

const SCREENS: Screen[] = [
  { name: "index", route: "/" },
  {
    name: "index-no-segments",
    route: "/",
    prepare: async (page) => {
      await page.route("**/data/index.json", async (route: Route) => {
        const response = await route.fetch();
        const json = await response.json();
        await route.fulfill({ response, json: { ...json, segments: [] } });
      });
    },
  },
  { name: "segment", route: "/segment/hill-road-climb" },
  {
    name: "segment-by-date",
    route: "/segment/hill-road-climb",
    after: async (page) => {
      const sort = page.getByRole("button", { name: /newest|date/i });
      if (await sort.count()) await sort.first().click();
    },
  },
  { name: "segment-no-efforts", route: "/segment/quarry-descent" },
  { name: "ride", route: "/ride/3000000106" },
  { name: "ride-no-segments", route: "/ride/3000000109" },
  { name: "not-found", route: "/segment/does-not-exist" },
];

for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
  for (const colorScheme of SCHEMES) {
    test.describe(`${viewportName} ${colorScheme}`, () => {
      test.use({ viewport, colorScheme, deviceScaleFactor: 1 });
      for (const screen of SCREENS) {
        test(`${screen.name}`, async ({ page }) => {
          await screen.prepare?.(page);
          await page.goto(`./#${screen.route}`);
          await page.waitForLoadState("networkidle");
          await screen.after?.(page);
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(400); // let chart animations settle
          await page.screenshot({
            path: path.join(OUT, `${screen.name}-${viewportName}-${colorScheme}.png`),
            fullPage: true,
          });
        });
      }
    });
  }
}
