#!/usr/bin/env node
/**
 * Copies RDKit_minimal.wasm to public/ using Node module resolution
 * instead of hardcoded relative paths. Works with any pnpm hoisting mode.
 */
import { createRequire } from "module";
import { copyFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const wasmSource = require.resolve("@rdkit/rdkit/dist/RDKit_minimal.wasm");
const dest = join(__dirname, "..", "public", "RDKit_minimal.wasm");

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(wasmSource, dest);
console.log(`Copied RDKit WASM: ${wasmSource} -> ${dest}`);
