// ESLint (v10) looks up the config from each linted file's directory. web/ has its own config;
// this root file makes the same config apply to the Playwright specs in tests/acceptance/web and
// tests/screenshots (run via `npm --prefix web run lint`).
export { default } from "./web/eslint.config.js";
