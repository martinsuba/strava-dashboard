import { createRequire } from "node:module";

// Node 24 loads this ESM config natively; @playwright/test is CommonJS and its named exports are
// not detectable, so load it with require (typed via the import type).
const require = createRequire(import.meta.url);
const { defineConfig, devices } = require("@playwright/test") as typeof import("@playwright/test");

// Runs against the *built* site (`vite preview`), with tests/fixtures/site-data copied into
// public/data first: `npm run test:acceptance` / `npm run screenshots` do copy + build + test.
// Own port (4173 is vite's default and the staging preview in docs/DEPLOY.md). Override: PW_PORT.
const PORT = Number(process.env.PW_PORT ?? 4318);
const BASE = `http://localhost:${PORT}/strava-dashboard/`;

export default defineConfig({
  testDir: "../tests",
  // Specs live outside web/ (tests/acceptance/web, tests/screenshots); this tsconfig's "paths"
  // maps @playwright/test to web/node_modules so they resolve it.
  tsconfig: "./tsconfig.json",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : 1,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: BASE,
    timezoneId: "UTC",
    locale: "en-GB",
    colorScheme: "light",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npx vite preview --port ${PORT} --strictPort`,
    url: BASE,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    {
      name: "acceptance",
      testDir: "../tests/acceptance/web",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "screenshots",
      testDir: "../tests/screenshots",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
