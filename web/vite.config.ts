import { defineConfig } from "vitest/config";

// Served from https://martinsuba.github.io/strava-dashboard/ (GitHub Pages project site).
export default defineConfig({
  base: "/strava-dashboard/",
  build: { outDir: "dist", emptyOutDir: true },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
