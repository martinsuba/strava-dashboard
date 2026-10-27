// Smoke test against a live (or locally previewed) site:
//   npm run smoke -- --base https://martinsuba.github.io/strava-dashboard/
// Loads the index, then one segment page and one ride page (links discovered from the index) and
// fails on page errors, console errors or failed requests. Not part of test / test:acceptance.
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
  try {
    await page.goto(base.href, { waitUntil: "networkidle" });
    await page.waitForSelector("a[href^='#/segment/']", { timeout: 15_000 });
    steps.push("index");
    const segment = await page.getAttribute("a[href^='#/segment/']", "href");
    const ride = await page.getAttribute("a[href^='#/ride/']", "href");
    if (!ride) throw new Error("no ride link found on the index page");
    for (const [label, hash, selector] of [
      ["segment page", segment, "main h1, h1"],
      ["ride page", ride, "main h1, h1"],
    ]) {
      await page.goto(new URL(hash, base).href, { waitUntil: "networkidle" });
      await page.waitForSelector(selector, { timeout: 15_000 });
      // The app's not-found view: h1 exactly "Not found" next to its fixed explanatory line.
      const notFound = page
        .locator("h1", { hasText: /^Not found$/ })
        .locator("xpath=..")
        .getByText("There is nothing at this address.");
      if ((await notFound.count()) > 0)
        throw new Error(`${label} ${hash} shows the not-found view`);
      steps.push(`${label} ${hash}`);
    }
  } catch (err) {
    problems.push(String(err instanceof Error ? err.message : err));
  } finally {
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
