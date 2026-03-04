#!/usr/bin/env node
/**
 * Copies PrimeReact lara-light-teal and lara-dark-teal themes to public/
 * so they can be loaded dynamically at runtime by ThemeProvider.
 */
import { cpSync, mkdirSync } from "fs";
import { createRequire } from "module";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const themes = ["lara-light-teal", "lara-dark-teal"];
const destDir = join(__dirname, "..", "public", "primereact-themes");

mkdirSync(destDir, { recursive: true });

for (const theme of themes) {
  const src = dirname(
    require.resolve(`primereact/resources/themes/${theme}/theme.css`),
  );
  const dest = join(destDir, theme);
  cpSync(src, dest, { recursive: true });
  console.log(`Copied PrimeReact theme: ${theme}`);
}
