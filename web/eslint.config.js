import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/dist/",
      "**/node_modules/",
      "**/public/",
      "**/test-results/",
      "**/playwright-report/",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: { ...globals.browser } },
  },
  {
    files: [
      "scripts/**",
      "*.config.{js,ts}",
      "**/tests/acceptance/web/**",
      "**/tests/screenshots/**",
    ],
    languageOptions: { globals: { ...globals.node } },
  },
);
