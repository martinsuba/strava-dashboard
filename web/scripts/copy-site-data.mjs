// Copy the committed synthetic site data (tests/fixtures/site-data) into web/public/data
// so `vite build` / `vite preview` serve it. web/public/data is git-ignored.
import { cpSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../tests/fixtures/site-data");
const dest = resolve(here, "../public/data");
rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log(`copied ${src} -> ${dest}`);
