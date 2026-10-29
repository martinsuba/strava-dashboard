// Smoke test against a live (or locally previewed) site:
//   npm run smoke -- --base https://martinsuba.github.io/strava-dashboard/
// Loads the index, then one segment page and one ride page (links discovered from the index). Per page
// it waits for the loaded content, then for the page's data/...json response to finish (HTTP ok, JSON
// content type). Fails on a loading, not-found or "Could not load" view, and on page errors, console
// errors, failed requests or HTTP >= 400; networkidle is awaited before the browser closes so all
// requests are seen. Not part of test / test:acceptance.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");

function parseBase(argv) {
  const i = argv.indexOf("--base");
  const raw = i >= 0 ? argv[i + 1] : undefined;
  if (!raw) throw new Error("usage: npm run smoke -- --base <url>");
  const url = new URL(raw);
  if (!url.pathname.endsWith("/")) url.pathname += "/";
  return url;
}

async function main() {
  const base = parseBase(process.argv.slice(2));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const problems = [];
  page.on("pageerror", (err) => problems.push(`page error: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console error: ${msg.text()}`);
  });
  page.on("requestfailed", (req) =>
    problems.push(`request failed: ${req.url()} (${req.failure()?.errorText})`),
  );
  page.on("response", (res) => {
    if (res.status() >= 400) problems.push(`HTTP ${res.status()}: ${res.url()}`);
  });

  const steps = [];
  const TIMEOUT = 15_000;

  // Registered before navigating, so a response that arrives early is not missed.
  function expectData(rel) {
    const path = new URL(`data/${rel}`, base).pathname;
    return page.waitForResponse((res) => new URL(res.url()).pathname === path, {
      timeout: TIMEOUT,
    });
  }

  // The app's own non-content views: not-found (h1 "Not found" + fixed line), "Could not load ...", loading.
  const notFoundView = page
    .locator("h1", { hasText: /^Not found$/ })
    .locator("xpath=..")
    .getByText("There is nothing at this address.");
  const errorView = page.getByText(/^Could not load /);
  const loadingView = page.getByText("Loading…", { exact: true });

  // Waits for `loaded` (or a failure view), then for the page's data request to finish, then checks
  // that the data file really is JSON (a static host may answer a missing file with index.html).
  // `also` lists further selectors that must be present on the loaded page.
  async function checkPage({ label, rel, loaded, also = [], navigate }) {
    const dataResponse = expectData(rel);
    dataResponse.catch(() => {}); // reported below; avoids an unhandled rejection meanwhile
    await navigate();
    try {
      await loaded.or(notFoundView).or(errorView).first().waitFor({ timeout: TIMEOUT });
    } catch {
      /* diagnosed below */
    }
    if ((await notFoundView.count()) > 0) throw new Error(`${label}: shows the not-found view`);
    if ((await errorView.count()) > 0) throw new Error(`${label}: shows the error view`);
    if ((await loadingView.count()) > 0)
      throw new Error(`${label}: still shows the loading view after ${TIMEOUT / 1000}s`);
    if ((await loaded.count()) === 0) throw new Error(`${label}: loaded content not found`);
    for (const sel of also)
      if ((await page.locator(sel).count()) === 0)
        throw new Error(`${label}: expected content missing (${sel})`);
    let res;
    try {
      res = await dataResponse;
      await res.finished();
    } catch {
      throw new Error(`${label}: data/${rel} was not requested or did not finish`);
    }
    const type = res.headers()["content-type"] ?? "";
    if (!res.ok() || !type.includes("json"))
      throw new Error(
        `${label}: data/${rel} answered HTTP ${res.status()} (${type || "no content type"})`,
      );
    steps.push(label);
  }

  try {
    await checkPage({
      label: "index",
      rel: "index.json",
      loaded: page.locator("a[href^='#/ride/']").first(),
      also: ["a[href^='#/segment/']"],
      navigate: () => page.goto(base.href),
    });
    const segment = await page.getAttribute("a[href^='#/segment/']", "href");
    const ride = await page.getAttribute("a[href^='#/ride/']", "href");

    // Segment: the efforts table or the no-efforts message.
    await checkPage({
      label: `segment page ${segment}`,
      rel: `segments/${segment.slice("#/segment/".length)}.json`,
      loaded: page
        .locator(".panel--efforts table")
        .or(page.getByText("No efforts on this segment yet.")),
      navigate: () => page.goto(new URL(segment, base).href),
    });
    // Ride: the facts strip plus the matched-efforts list or the no-match message.
    await checkPage({
      label: `ride page ${ride}`,
      rel: `rides/${ride.slice("#/ride/".length)}.json`,
      loaded: page
        .locator(".panel--ride-segments table")
        .or(page.getByText("No segments matched on this ride.")),
      also: ["section[aria-label='Ride summary']"],
      navigate: () => page.goto(new URL(ride, base).href),
    });
  } catch (err) {
    problems.push(String(err instanceof Error ? err.message : err));
  } finally {
    // Let in-flight requests finish so the listeners above see them all before the browser closes.
    await page.waitForLoadState("networkidle").catch(() => {});
    await browser.close();
  }

  for (const s of steps) console.log(`ok: ${s}`);
  if (problems.length) {
    for (const p of problems) console.error(`FAIL: ${p}`);
    process.exit(1);
  }
  console.log("smoke passed");
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
