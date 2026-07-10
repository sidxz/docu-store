# Design System Harmonization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chem-cellar, prot-cellar, docu-store, and daikon-gen3 read as one product suite — shared color tokens (docu-store's blue/slate), a user-switchable font preference (IBM Plex ⇄ Inter), Radix everywhere — distributed via one public npm package.

**Architecture:** A CSS-only package `@daikon/design-tokens` ships the canonical `--ds-*` primitive layer + a superset shadcn bridge + a `@theme` map, keyed to `data-theme` (light/dark) and `data-font` (plex/inter) attributes on `<html>`. Each app `@import`s it, deletes its local token block, drives the two attributes with a small persisted store, and loads both font families via `next/font`. daikon-gen3 additionally migrates its one base-ui component to Radix.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (Radix), next-themes / zustand, next/font (IBM Plex + Inter), npm (public registry).

## Global Constraints

- **Registry:** `@daikon/design-tokens`, **public npm**, published `--access public` (mirrors `@sentinel-auth/*` — zero Docker/CI/dev auth changes). Requires the `@daikon` npm org to exist with publish rights.
- **Dark selector:** `[data-theme="dark"]` for ALL apps. next-themes apps use `attribute="data-theme"`.
- **Font attribute:** `data-font` on `<html>`, values `plex` | `inter`, **default `plex`**. Persisted to `localStorage['ds-font']`.
- **Mono font:** always IBM Plex Mono. The preference switches the **sans/body** family only.
- **Font weights (verbatim from chem-cellar):** IBM Plex Sans `["400","500","600","700"]`, IBM Plex Mono `["400","500","600"]`. Inter: default weights, `display:"swap"`.
- **Palette source of truth:** docu-store's current `--ds-*` values, copied verbatim into the package.
- **No component-code color renames** — the package carries the union of every token name the four apps reference.
- **Commits:** each repo is its own git repo; commit within that repo. Do not push unless the user asks.

---

## Task 0: Spike — Tailwind v4 honors `@theme` from a node_modules import

**Files:**
- Temp only (throwaway); no commit.

**Why:** The entire package approach assumes Tailwind v4 processes `@theme` / `@custom-variant` from an `@import`ed CSS file resolved out of `node_modules`. If it doesn't, we fall back to shipping raw vars in the package and keeping a thin `@theme` map per app. Verify before building anything.

- [ ] **Step 1: Create a minimal local package and link it into one app**

In a scratch dir:
```bash
mkdir -p /tmp/dst-spike && cd /tmp/dst-spike
cat > package.json <<'JSON'
{ "name": "@daikon/design-tokens", "version": "0.0.0", "exports": { "./tokens.css": "./tokens.css" }, "files": ["tokens.css"] }
JSON
cat > tokens.css <<'CSS'
@theme inline { --color-spiketest: #ff00ff; }
:root { --ds-spike: #123456; }
CSS
```
In `chem-vault2/frontend`: `pnpm add file:/tmp/dst-spike`

- [ ] **Step 2: Import it and use the utility**

Prepend to `chem-vault2/frontend/src/app/globals.css` (after `@import "tailwindcss";`):
```css
@import "@daikon/design-tokens/tokens.css";
```
Add `className="bg-spiketest"` to any element on a rendered page.

- [ ] **Step 3: Build and verify the utility compiled**

Run: `cd chem-vault2/frontend && pnpm build`
Expected: build succeeds. Then grep the output CSS:
```bash
grep -r "spiketest" .next/ | head
```
Expected: a `.bg-spiketest{background-color:#ff00ff}` rule exists → **PASS, proceed with the package plan as written.**
If absent → **FALLBACK:** the package ships only `:root`/`[data-theme]`/`[data-font]` raw vars; each app keeps its own `@theme inline` map (pointing at the package's vars). Note this in Task 2 and each app task.

- [ ] **Step 4: Revert the spike**

```bash
cd chem-vault2/frontend && pnpm remove @daikon/design-tokens && git checkout src/app/globals.css
rm -rf /tmp/dst-spike
```
Revert the test className edit. Nothing from this task is committed.

---

## Task 1: Scaffold the `daikon-design-tokens` repo

**Files:**
- Create: `daikon-design-tokens/package.json`
- Create: `daikon-design-tokens/README.md`
- Create: `daikon-design-tokens/.gitignore`

**Interfaces:**
- Produces: package `@daikon/design-tokens` with export `"./tokens.css"`.

- [ ] **Step 1: Create the repo and package.json**

```bash
mkdir -p /Users/sidx/workspace/daikon-design-tokens && cd /Users/sidx/workspace/daikon-design-tokens && git init
```
Create `package.json`:
```json
{
  "name": "@daikon/design-tokens",
  "version": "1.0.0",
  "description": "Canonical design tokens for the DAIKON app suite (colors, fonts, radius).",
  "license": "UNLICENSED",
  "sideEffects": ["*.css"],
  "exports": { "./tokens.css": "./tokens.css" },
  "files": ["tokens.css"],
  "publishConfig": { "access": "public" },
  "scripts": { "test": "node test/contract.mjs" }
}
```

- [ ] **Step 2: Create README with the consumer contract**

Create `README.md`:
```markdown
# @daikon/design-tokens

Canonical design tokens for the DAIKON suite. Palette source of truth: docu-store.

## Usage
1. In your Tailwind v4 entry CSS, after `@import "tailwindcss";`:
   `@import "@daikon/design-tokens/tokens.css";`
   Then delete your local `:root` / `.dark` token block and `@custom-variant dark`.
2. Define the three font-family CSS vars via `next/font` in `layout.tsx`:
   `--font-plex-sans`, `--font-plex-mono`, `--font-inter`.
3. Drive two attributes on `<html>`: `data-theme` (`light`|`dark`) and
   `data-font` (`plex`|`inter`, default `plex`). Add the anti-flash snippet below to `<head>`.

## Anti-flash snippet (zustand-persist apps)
`(function(){try{var f=JSON.parse(localStorage.getItem('ds-font')||'{}');document.documentElement.setAttribute('data-font',(f.state&&f.state.font)||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}})()`
```

- [ ] **Step 3: Add .gitignore and commit**

```bash
printf "node_modules/\n" > .gitignore
git add -A && git commit -m "chore: scaffold @daikon/design-tokens package"
```

---

## Task 2: Author `tokens.css` (the union superset)

**Files:**
- Create: `daikon-design-tokens/tokens.css`

**Interfaces:**
- Produces: `:root` + `[data-theme="dark"]` + `[data-font="inter"]` + `@theme inline` covering the union of all four apps' token names. Utilities other tasks rely on: standard shadcn (`bg-primary`, `bg-background`, `text-muted-foreground`, `border`, `ring`, …), `success/warning/info(+foreground)`, `chart-1..5`, `sidebar*`, docu-store's `surface*/text-*/accent-*/ds-*/score-*` and `shadow-ds*`, `font-sans/mono`, `radius-sm..4xl`.

- [ ] **Step 1: Write tokens.css**

Create `daikon-design-tokens/tokens.css` with exactly this content:
```css
/*
 * @daikon/design-tokens — canonical design system for the DAIKON app suite.
 * Palette source of truth: docu-store. Consumed by chem-cellar, prot-cellar,
 * docu-store, daikon-gen3.
 *
 * Contract: apps supply --font-plex-sans/--font-plex-mono/--font-inter via
 * next/font and drive data-theme + data-font on <html>. See README.
 */

@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

:root {
  /* ── ds primitives (light) ── */
  --ds-surface: #ffffff;
  --ds-surface-elevated: #ffffff;
  --ds-surface-sunken: #f8fafc;
  --ds-surface-overlay: #ffffff;
  --ds-surface-hover: #f1f5f9;
  --ds-border: #e2e8f0;
  --ds-border-subtle: #f1f5f9;
  --ds-text-primary: #0f172a;
  --ds-text-secondary: #475569;
  --ds-text-muted: #94a3b8;
  --ds-text-inverse: #ffffff;
  --ds-accent: #3b82f6;
  --ds-accent-hover: #2563eb;
  --ds-accent-light: #eff6ff;
  --ds-accent-muted: #dbeafe;
  --ds-accent-text: #2563eb;
  --ds-accent-subtle: #f5f9ff;
  --ds-sidebar: #f1f5f9;
  --ds-sidebar-text: #475569;
  --ds-sidebar-text-active: #0f172a;
  --ds-sidebar-hover: rgba(15, 23, 42, 0.05);
  --ds-sidebar-active: rgba(59, 130, 246, 0.12);
  --ds-sidebar-border: #e2e8f0;
  --ds-success: #15803d;
  --ds-warning: #a16207;
  --ds-error: #b91c1c;
  --ds-info: #1d4ed8;
  --ds-score-excellent: #16a34a;
  --ds-score-good: #0d9488;
  --ds-score-fair: #d97706;
  --ds-score-poor: #ef4444;
  --ds-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --ds-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
  --ds-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);

  /* ── shadcn standard bridge (union of all suite apps) ── */
  --radius: 0.5rem;
  --background: var(--ds-surface);
  --foreground: var(--ds-text-primary);
  --card: var(--ds-surface-elevated);
  --card-foreground: var(--ds-text-primary);
  --popover: var(--ds-surface-overlay);
  --popover-foreground: var(--ds-text-primary);
  --primary: var(--ds-accent);
  --primary-foreground: var(--ds-text-inverse);
  --secondary: var(--ds-surface-sunken);
  --secondary-foreground: var(--ds-text-secondary);
  --muted: var(--ds-surface-sunken);
  --muted-foreground: var(--ds-text-muted);
  --accent: var(--ds-accent-light);
  --accent-foreground: var(--ds-accent-text);
  --destructive: var(--ds-error);
  --destructive-foreground: #ffffff;
  --border: var(--ds-border);
  --input: var(--ds-border);
  --ring: var(--ds-accent);

  /* semantic + foreground (cellar compat) */
  --success: var(--ds-success);
  --success-foreground: #ffffff;
  --warning: var(--ds-warning);
  --warning-foreground: #ffffff;
  --info: var(--ds-info);
  --info-foreground: #ffffff;

  /* charts — blue-anchored ramp (gen3 compat) */
  --chart-1: #3b82f6;
  --chart-2: #14b8a6;
  --chart-3: #8b5cf6;
  --chart-4: #f59e0b;
  --chart-5: #ef4444;

  /* sidebar — shadcn-standard names, mapped onto ds sidebar */
  --sidebar: var(--ds-sidebar);
  --sidebar-foreground: var(--ds-sidebar-text);
  --sidebar-primary: var(--ds-accent);
  --sidebar-primary-foreground: var(--ds-text-inverse);
  --sidebar-accent: var(--ds-accent-light);
  --sidebar-accent-foreground: var(--ds-accent-text);
  --sidebar-border: var(--ds-sidebar-border);
  --sidebar-ring: var(--ds-accent);

  /* fonts — preference-driven; apps supply the family vars */
  --font-sans: var(--font-plex-sans, "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif);
  --font-mono: var(--font-plex-mono, "IBM Plex Mono", ui-monospace, monospace);
}

[data-theme="dark"] {
  --ds-surface: #0f172a;
  --ds-surface-elevated: #1e293b;
  --ds-surface-sunken: #020617;
  --ds-surface-overlay: #1e293b;
  --ds-surface-hover: rgba(148, 163, 184, 0.08);
  --ds-border: #334155;
  --ds-border-subtle: #1e293b;
  --ds-text-primary: #f1f5f9;
  --ds-text-secondary: #94a3b8;
  --ds-text-muted: #64748b;
  --ds-text-inverse: #0f172a;
  --ds-accent: #60a5fa;
  --ds-accent-hover: #93bbfd;
  --ds-accent-light: rgba(59, 130, 246, 0.15);
  --ds-accent-muted: rgba(59, 130, 246, 0.1);
  --ds-accent-text: #60a5fa;
  --ds-accent-subtle: rgba(59, 130, 246, 0.08);
  --ds-sidebar: #0f172a;
  --ds-sidebar-text: #cbd5e1;
  --ds-sidebar-text-active: #ffffff;
  --ds-sidebar-hover: rgba(255, 255, 255, 0.05);
  --ds-sidebar-active: rgba(255, 255, 255, 0.1);
  --ds-sidebar-border: rgba(255, 255, 255, 0.06);
  --ds-success: #22c55e;
  --ds-warning: #f59e0b;
  --ds-error: #ef4444;
  --ds-info: #60a5fa;
  --ds-score-excellent: #22c55e;
  --ds-score-good: #2dd4bf;
  --ds-score-fair: #f59e0b;
  --ds-score-poor: #f87171;
  --ds-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
  --ds-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.3);
  --ds-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3);

  /* dark overrides for non-indirected bridge tokens */
  --destructive-foreground: #ffffff;
  --success-foreground: #052e16;
  --warning-foreground: #451a03;
  --info-foreground: #082f49;
  --chart-1: #60a5fa;
  --chart-2: #2dd4bf;
  --chart-3: #a78bfa;
  --chart-4: #fbbf24;
  --chart-5: #f87171;
}

[data-font="inter"] {
  --font-sans: var(--font-inter, "Inter", ui-sans-serif, system-ui, sans-serif);
  /* mono intentionally stays IBM Plex Mono */
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-info: var(--info);
  --color-info-foreground: var(--info-foreground);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);
  --color-surface: var(--ds-surface);
  --color-surface-elevated: var(--ds-surface-elevated);
  --color-surface-sunken: var(--ds-surface-sunken);
  --color-surface-overlay: var(--ds-surface-overlay);
  --color-surface-hover: var(--ds-surface-hover);
  --color-surface-default: var(--ds-surface);
  --color-surface-raised: var(--ds-surface-elevated);
  --color-border-default: var(--ds-border);
  --color-border-subtle: var(--ds-border-subtle);
  --color-text-primary: var(--ds-text-primary);
  --color-text-secondary: var(--ds-text-secondary);
  --color-text-muted: var(--ds-text-muted);
  --color-text-inverse: var(--ds-text-inverse);
  --color-accent-hover: var(--ds-accent-hover);
  --color-accent-light: var(--ds-accent-light);
  --color-accent-muted: var(--ds-accent-muted);
  --color-accent-text: var(--ds-accent-text);
  --color-accent-subtle: var(--ds-accent-subtle);
  --color-sidebar-text: var(--ds-sidebar-text);
  --color-sidebar-text-active: var(--ds-sidebar-text-active);
  --color-sidebar-hover: var(--ds-sidebar-hover);
  --color-sidebar-active: var(--ds-sidebar-active);
  --color-ds-success: var(--ds-success);
  --color-ds-warning: var(--ds-warning);
  --color-ds-error: var(--ds-error);
  --color-ds-info: var(--ds-info);
  --color-score-excellent: var(--ds-score-excellent);
  --color-score-good: var(--ds-score-good);
  --color-score-fair: var(--ds-score-fair);
  --color-score-poor: var(--ds-score-poor);
  --shadow-ds-sm: var(--ds-shadow-sm);
  --shadow-ds: var(--ds-shadow);
  --shadow-ds-md: var(--ds-shadow-md);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  --radius-2xl: calc(var(--radius) + 8px);
  --radius-3xl: calc(var(--radius) + 12px);
  --radius-4xl: calc(var(--radius) + 16px);
  --font-sans: var(--font-sans);
  --font-mono: var(--font-mono);
}

@layer base {
  *,
  ::before,
  ::after {
    border-color: var(--border);
  }
  body {
    font-family: var(--font-sans);
    background-color: var(--ds-surface);
    color: var(--ds-text-primary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  *:focus-visible {
    outline: 2px solid var(--ds-accent);
    outline-offset: 2px;
  }
  ::selection {
    background-color: var(--ds-accent-muted);
    color: var(--ds-text-primary);
  }
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background-color: var(--ds-text-muted); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background-color: var(--ds-text-secondary); }
}
```

> **If Task 0 fell back:** wrap the `@theme inline {…}` block’s move into each app instead — keep only `:root`/`[data-theme]`/`[data-font]`/`@layer base` here.

- [ ] **Step 2: Commit**

```bash
cd /Users/sidx/workspace/daikon-design-tokens
git add tokens.css && git commit -m "feat: add canonical tokens.css (union superset)"
```

---

## Task 3: Contract check — assert required tokens exist

**Files:**
- Create: `daikon-design-tokens/test/contract.mjs`

- [ ] **Step 1: Write the failing check**

Create `test/contract.mjs`:
```js
import { readFileSync } from "node:fs";
const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
const required = [
  '[data-theme="dark"]', '[data-font="inter"]',
  "--ds-accent: #3b82f6", "--primary: var(--ds-accent)",
  "--color-primary:", "--color-sidebar-primary:", "--color-success-foreground:",
  "--color-chart-5:", "--color-ds-success:", "--font-sans: var(--font-sans)",
];
const missing = required.filter((t) => !css.includes(t));
if (missing.length) { console.error("MISSING:", missing); process.exit(1); }
console.log("contract OK:", required.length, "tokens present");
```

- [ ] **Step 2: Run it**

Run: `cd /Users/sidx/workspace/daikon-design-tokens && node test/contract.mjs`
Expected: `contract OK: 10 tokens present`. If it fails, fix the missing token in `tokens.css` (do not weaken the check).

- [ ] **Step 3: Commit**

```bash
git add test/contract.mjs && git commit -m "test: token contract check"
```

---

## Task 4: Publish `@daikon/design-tokens@1.0.0` to public npm

**Files:** none (publish + optional CI workflow).

**Prerequisite:** the `@daikon` npm org must exist and the publishing user must be a member. If not ready, apps can consume `file:/Users/sidx/workspace/daikon-design-tokens` locally until publish is possible — note the switch-back in each app task.

- [ ] **Step 1: Dry-run the pack**

Run: `cd /Users/sidx/workspace/daikon-design-tokens && npm publish --dry-run --access public`
Expected: the tarball lists exactly `package.json`, `README.md`, `tokens.css` (not `test/`).

- [ ] **Step 2: Publish**

Run: `npm publish --access public`
Expected: `+ @daikon/design-tokens@1.0.0`. Verify: `npm view @daikon/design-tokens version` → `1.0.0`.

- [ ] **Step 3: Add release workflow and commit**

Create `.github/workflows/publish.yml`:
```yaml
name: publish
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions: { contents: read, id-token: write }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, registry-url: "https://registry.npmjs.org" }
      - run: node test/contract.mjs
      - run: npm publish --access public
        env: { NODE_AUTH_TOKEN: "${{ secrets.NPM_TOKEN }}" }
```
```bash
git add .github/workflows/publish.yml && git commit -m "ci: publish on tag"
```

---

## Task 5: docu-store — consume the package (dogfood)

**Files:**
- Modify: `docu-store/web/apps/portal/package.json` (add dep)
- Modify: `docu-store/web/apps/portal/src/app/globals.css:31-165` (replace `:root` + `[data-theme="dark"]` token blocks and the shadcn bridge lines within `@theme inline` with the import; KEEP feature-* colors, citation-flash, page transitions, streamdown `@source`, scrollbar/selection if desired)

**Interfaces:**
- Consumes: `@daikon/design-tokens/tokens.css`.

- [ ] **Step 1: Install the package**

```bash
cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal add @daikon/design-tokens
```
(If not yet published: `pnpm --filter portal add file:/Users/sidx/workspace/daikon-design-tokens`.)

- [ ] **Step 2: Replace the token blocks with the import**

In `docu-store/web/apps/portal/src/app/globals.css`:
- After line 19 (`@import "tw-animate-css";`), add: `@import "@daikon/design-tokens/tokens.css";`
- Delete the `:root { … }` block (lines 31–108) and the `[data-theme="dark"] { … }` block (lines 110–165) — these now come from the package.
- In the `@theme inline` block, delete the shadcn-standard and surface/text/accent/sidebar/ds/score/shadow lines that the package now provides (they duplicate). **KEEP** the `--color-feature-search/compounds/folder` lines (docu-store-local).
- Delete the `@custom-variant dark (…)` line (line 17) — the package defines it.
- **KEEP** the `@layer base { *{border-color} }`, body, citation-flash, page transitions, `@source` streamdown lines.

- [ ] **Step 3: Build and verify no regression**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal build`
Expected: build succeeds. Visually this should be a **near no-op** (docu-store was already blue/slate/data-theme). Spot-check via Task 8's method after fonts land.

- [ ] **Step 4: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add web/apps/portal/package.json web/apps/portal/src/app/globals.css web/pnpm-lock.yaml
git commit -m "refactor(portal): consume @daikon/design-tokens for colors"
```

---

## Task 6: docu-store — add IBM Plex + Inter fonts and font-family preference

**Files:**
- Modify: `docu-store/web/apps/portal/src/app/layout.tsx`
- Create: `docu-store/web/apps/portal/src/lib/stores/font-family-store.ts`
- Create: `docu-store/web/apps/portal/src/components/providers/FontFamilyProvider.tsx`
- Modify: `docu-store/web/apps/portal/src/components/providers/Providers.tsx:24-26,118-123`

**Interfaces:**
- Consumes: package's `[data-font]` switch + `--font-plex-*`/`--font-inter` contract.
- Produces: `useFontFamilyStore` (`{ font: "plex"|"inter"; setFont; toggle }`, storage key `ds-font`).

- [ ] **Step 1: Load both families + extend the anti-flash script in layout.tsx**

Replace the `Inter` import and font const, and extend the inline script:
```tsx
import { IBM_Plex_Mono, IBM_Plex_Sans, Inter } from "next/font/google";

const plexSans = IBM_Plex_Sans({ subsets: ["latin"], variable: "--font-plex-sans", weight: ["400", "500", "600", "700"], display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500", "600"], display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
```
Change the `<html>` className to include all three:
```tsx
<html lang="en" className={`${plexSans.variable} ${plexMono.variable} ${inter.variable}`} suppressHydrationWarning>
```
Extend the inline `__html` script — append before the closing `})()`:
```js
try{var g=JSON.parse(localStorage.getItem('ds-font')||'{}');document.documentElement.setAttribute('data-font',(g.state&&g.state.font)||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}
```

- [ ] **Step 2: Create the font-family store** (mirrors `font-scale-store.ts`)

Create `src/lib/stores/font-family-store.ts`:
```ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "ds-font"; // must match the inline anti-flash script in layout.tsx
export type FontFamily = "plex" | "inter";

interface FontFamilyState {
  font: FontFamily;
  setFont: (font: FontFamily) => void;
  toggle: () => void;
}

export const useFontFamilyStore = create<FontFamilyState>()(
  persist(
    (set, get) => ({
      font: "plex",
      setFont: (font) => set({ font }),
      toggle: () => set({ font: get().font === "plex" ? "inter" : "plex" }),
    }),
    { name: STORAGE_KEY },
  ),
);
```

- [ ] **Step 3: Create FontFamilyProvider** (mirrors `FontScaleProvider.tsx`)

Create `src/components/providers/FontFamilyProvider.tsx`:
```tsx
"use client";
import { useEffect, type ReactNode } from "react";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  return <>{children}</>;
}
```

- [ ] **Step 4: Wire into Providers.tsx**

Add import next to `FontScaleProvider` (line 25): `import { FontFamilyProvider } from "./FontFamilyProvider";`
Wrap inside `FontScaleProvider` (around lines 119–122):
```tsx
<FontScaleProvider>
  <FontFamilyProvider>
    <ConfirmProvider>{children}</ConfirmProvider>
    <Toaster richColors closeButton position="top-right" />
  </FontFamilyProvider>
</FontScaleProvider>
```

- [ ] **Step 5: Build, then commit**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal build`
Expected: succeeds.
```bash
cd /Users/sidx/workspace/docu-store
git add web/apps/portal/src
git commit -m "feat(portal): IBM Plex + Inter with data-font preference"
```

---

## Task 7: docu-store — font switcher UI

**Files:**
- Create: `docu-store/web/apps/portal/src/components/settings/FontToggle.tsx`
- Modify: the settings / user-menu component where theme controls already live (locate with the grep below)

- [ ] **Step 1: Create the toggle**

Create `FontToggle.tsx`:
```tsx
"use client";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";
import { Button } from "@/components/ui/button";

export function FontToggle() {
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  return (
    <div className="flex gap-1">
      <Button size="sm" variant={font === "plex" ? "default" : "outline"} onClick={() => setFont("plex")}>IBM Plex</Button>
      <Button size="sm" variant={font === "inter" ? "default" : "outline"} onClick={() => setFont("inter")}>Inter</Button>
    </div>
  );
}
```

- [ ] **Step 2: Place it beside the existing theme/font-scale controls**

Run: `grep -rl "useFontScaleStore\|useThemeStore" docu-store/web/apps/portal/src/components | grep -iv provider`
Add `<FontToggle />` into that settings panel next to the scale/theme controls.

- [ ] **Step 3: Build and commit**

Run: `pnpm --filter portal build` (from `docu-store/web`). Expected: succeeds.
```bash
cd /Users/sidx/workspace/docu-store && git add web/apps/portal/src && git commit -m "feat(portal): font family switcher"
```

---

## Task 8: Verify docu-store end-to-end

- [ ] **Step 1: Run the app and check all four states**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal dev`
In the browser, toggle and confirm:
- `data-theme=light` + `data-font=plex` → white bg, blue accents, IBM Plex body
- `data-theme=dark` → slate `#0f172a` bg, lighter blue accents
- `data-font=inter` → body switches to Inter, **code/mono stays IBM Plex Mono**
- No FOUC on hard reload in any combination (anti-flash script works)
- `document.documentElement` shows both `data-theme` and `data-font` attributes

- [ ] **Step 2: Confirm no orphaned utilities**

Run: `pnpm --filter portal build` and confirm no CSS warnings about unknown utilities. Done — docu-store is the reference.

---

## Task 9: chem-cellar — colors, dark selector, fonts, preference

**Files:**
- Modify: `chem-vault2/frontend/package.json` (add dep)
- Modify: `chem-vault2/frontend/src/app/globals.css:1-128` (replace token blocks with import; keep `auth-enter`)
- Modify: `chem-vault2/frontend/src/shared/providers/theme-provider.tsx:8` (`attribute`)
- Modify: `chem-vault2/frontend/src/app/layout.tsx` (add Inter + rename font vars + anti-flash + FontProvider)
- Create: `chem-vault2/frontend/src/shared/stores/font-family-store.ts`
- Create: `chem-vault2/frontend/src/shared/providers/font-family-provider.tsx`
- Create: `chem-vault2/frontend/src/shared/components/font-toggle.tsx`

- [ ] **Step 1: Install the package**

```bash
cd /Users/sidx/workspace/chem-vault2/frontend && pnpm add @daikon/design-tokens
```

- [ ] **Step 2: Replace globals.css token blocks with the import**

Replace `chem-vault2/frontend/src/app/globals.css` lines 1–128 with:
```css
@import "tailwindcss";
@import "@daikon/design-tokens/tokens.css";
```
Delete the local `@custom-variant dark`, `:root`, `.dark`, `@theme`, and `@theme inline` blocks (all now from the package). **Keep** the `@keyframes auth-enter` block (lines 142–153) and the `@layer base` body/border block only if you want app-local overrides — otherwise delete it too (the package provides border/body). Keep `auth-enter`.

- [ ] **Step 3: Flip the theme provider to data-theme**

In `theme-provider.tsx` line 8: change `attribute="class"` → `attribute="data-theme"`. Leave `defaultTheme="dark" enableSystem disableTransitionOnChange` unchanged.

- [ ] **Step 4: Check for stray `.dark` / classList usages**

Run: `grep -rn "classList\|\"dark\"\|'dark'\|\.dark\b" chem-vault2/frontend/src --include=*.tsx --include=*.ts | grep -iv "dark:" | grep -iv node_modules`
Expected: no code that manually toggles a `.dark` class or reads it. `dark:` Tailwind variants are fine (driven by the package's `@custom-variant`). Fix any manual `.dark` logic to use `data-theme`.

- [ ] **Step 5: Fonts — add Inter, expose the three vars, extend anti-flash, add FontProvider**

In `layout.tsx`:
```tsx
import { IBM_Plex_Mono, IBM_Plex_Sans, Inter } from "next/font/google";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"] });
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
```
Update `<html>` to add a `<head>` anti-flash script, and body className to include all three vars:
```tsx
<html lang="en" suppressHydrationWarning>
  <head>
    <script dangerouslySetInnerHTML={{ __html: `(function(){try{var g=JSON.parse(localStorage.getItem('ds-font')||'{}');document.documentElement.setAttribute('data-font',(g.state&&g.state.font)||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}})()` }} />
  </head>
  <body className={`${plexSans.variable} ${plexMono.variable} ${inter.variable} font-sans antialiased`}>
    <ThemeProvider>
      <FontFamilyProvider>
        {/* …existing provider tree… */}
      </FontFamilyProvider>
    </ThemeProvider>
  </body>
</html>
```
Add import: `import { FontFamilyProvider } from "@/shared/providers/font-family-provider";`

Create `src/shared/stores/font-family-store.ts` (identical to docu-store's, Task 6 Step 2 — repeated here):
```ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "ds-font";
export type FontFamily = "plex" | "inter";

interface FontFamilyState {
  font: FontFamily;
  setFont: (font: FontFamily) => void;
  toggle: () => void;
}

export const useFontFamilyStore = create<FontFamilyState>()(
  persist(
    (set, get) => ({
      font: "plex",
      setFont: (font) => set({ font }),
      toggle: () => set({ font: get().font === "plex" ? "inter" : "plex" }),
    }),
    { name: STORAGE_KEY },
  ),
);
```
Create `src/shared/providers/font-family-provider.tsx`:
```tsx
"use client";
import { useEffect, type ReactNode } from "react";
import { useFontFamilyStore } from "@/shared/stores/font-family-store";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  return <>{children}</>;
}
```
Create `src/shared/components/font-toggle.tsx`:
```tsx
"use client";
import { Button } from "@/shared/components/ui/button";
import { useFontFamilyStore } from "@/shared/stores/font-family-store";

export function FontToggle() {
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  return (
    <div className="flex gap-1">
      <Button size="sm" variant={font === "plex" ? "default" : "outline"} onClick={() => setFont("plex")}>IBM Plex</Button>
      <Button size="sm" variant={font === "inter" ? "default" : "outline"} onClick={() => setFont("inter")}>Inter</Button>
    </div>
  );
}
```
Place `<FontToggle />` next to the theme control (find it: `grep -rln "useTheme\|next-themes" chem-vault2/frontend/src/shared/components`).

- [ ] **Step 6: Build**

Run: `cd /Users/sidx/workspace/chem-vault2/frontend && pnpm build`
Expected: succeeds, no unknown-utility warnings (the union bridge covers `sidebar-primary`, `success-foreground`, etc.).

- [ ] **Step 7: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src
git commit -m "feat(frontend): adopt @daikon/design-tokens + font preference"
```

---

## Task 10: Verify chem-cellar

- [ ] **Step 1: Run and check**

Run: `cd /Users/sidx/workspace/chem-vault2/frontend && pnpm dev`
Confirm: blue accents (was already blue — subtle shift to `#3b82f6`), slate dark mode, IBM Plex default, Inter toggle works, mono unchanged, AG Grid + Ketcher panels still legible in both themes, no FOUC. Check a sidebar (uses `sidebar-*` tokens) renders with slate panel.

---

## Task 11: prot-cellar — same as chem-cellar (note: teal → blue)

**Files:** same set as Task 9, under `prot-cellar/frontend/…`. prot-cellar's globals.css and theme-provider are structurally identical to chem-cellar (verified: same `@import "tailwindcss"`, `@custom-variant dark (&:is(.dark *))`, `attribute="class"`).

- [ ] **Step 1: Install package**

```bash
cd /Users/sidx/workspace/prot-cellar/frontend && pnpm add @daikon/design-tokens
```

- [ ] **Step 2: Replace globals.css top with the import** (drop the teal OKLCH block)

Replace `prot-cellar/frontend/src/app/globals.css` lines 1–2 + the `:root`/`.dark`/`@theme`/`@theme inline` blocks with:
```css
@import "tailwindcss";
@import "@daikon/design-tokens/tokens.css";
```
Keep any app-local `@keyframes`. **This is where prot-cellar's teal accent disappears — the package's blue takes over. Expected and intended.**

- [ ] **Step 3: Flip provider**

In `prot-cellar/frontend/src/shared/providers/theme-provider.tsx`: `attribute="class"` → `attribute="data-theme"`.

- [ ] **Step 4: Stray `.dark` check**

Run: `grep -rn "classList\|'dark'\|\"dark\"\|\.dark\b" prot-cellar/frontend/src --include=*.tsx --include=*.ts | grep -iv "dark:" | grep -iv node_modules`
Fix any manual `.dark` logic.

- [ ] **Step 5: Fonts + preference**

Repeat Task 9 Step 5 verbatim, under `prot-cellar/frontend/src/…` (same three font consts + `<head>` anti-flash script + body className `${plexSans.variable} ${plexMono.variable} ${inter.variable} font-sans antialiased`; same `font-family-store.ts`, `font-family-provider.tsx`, `font-toggle.tsx`; wrap tree in `<FontFamilyProvider>`).

- [ ] **Step 6: Build + commit**

```bash
cd /Users/sidx/workspace/prot-cellar/frontend && pnpm build   # expect success
cd /Users/sidx/workspace/prot-cellar
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src
git commit -m "feat(frontend): adopt @daikon/design-tokens + font preference (teal→blue)"
```

- [ ] **Step 7: Verify**

`pnpm dev` → confirm it now renders **blue** (not teal), slate dark mode, Plex default + Inter toggle, no FOUC.

---

## Task 12: daikon-gen3 — colors + fonts + base-ui→radix

**Files:**
- Modify: `daikon-gen3/frontend/package.json` (remove `@base-ui/react` + `shadcn`; add `@daikon/design-tokens`, `@radix-ui/react-slot`)
- Modify: `daikon-gen3/frontend/src/app/globals.css` (replace all tokens + drop `@import "shadcn/tailwind.css"`)
- Modify: `daikon-gen3/frontend/components.json` (`style: base-nova` → `new-york`; drop base-ui fields)
- Modify: `daikon-gen3/frontend/src/components/ui/button.tsx` (base-ui → radix)
- Modify: `daikon-gen3/frontend/src/app/layout.tsx` (Geist → Plex+Inter + anti-flash)
- Modify: `daikon-gen3/frontend/src/app/providers.tsx` (add theme + font providers)
- Create: `daikon-gen3/frontend/src/lib/use-font-family.ts` (no zustand dep — tiny hook)
- Create: `daikon-gen3/frontend/src/components/theme-provider.tsx`
- Create: `daikon-gen3/frontend/src/components/font-toggle.tsx`

- [ ] **Step 1: Swap dependencies**

```bash
cd /Users/sidx/workspace/daikon-gen3/frontend
pnpm remove @base-ui/react shadcn
pnpm add @daikon/design-tokens @radix-ui/react-slot
```

- [ ] **Step 2: Rewrite globals.css to consume the package**

Replace `daikon-gen3/frontend/src/app/globals.css` entirely with:
```css
@import "tailwindcss";
@import "tw-animate-css";
@import "@daikon/design-tokens/tokens.css";

@layer base {
  html { font-family: var(--font-sans); }
}
```
(Removes `@import "shadcn/tailwind.css"`, the base-nova `@custom-variant dark (&:is(.dark *))`, the gray `:root`/`.dark`, and the local `@theme inline` — all superseded by the package. The `outline-ring/50` base rule is dropped; the package sets a focus-visible outline.)

- [ ] **Step 3: Point components.json at the radix (new-york) style**

Edit `components.json`: set `"style": "new-york"`, `"baseColor": "neutral"` (unused now — tokens win), and **remove** `"menuColor"`, `"menuAccent"`, `"registries"` (base-ui-only fields). Leave aliases (`@/components`, `@/lib/utils`, …) as-is.

- [ ] **Step 4: Migrate button.tsx to Radix**

Replace `daikon-gen3/frontend/src/components/ui/button.tsx` with the standard shadcn new-york Radix button (keep gen3's existing `buttonVariants` cva string so sizes/variants are unchanged):
```tsx
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/80",
        outline: "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary: "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost: "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs": "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

function Button({
  className, variant = "default", size = "default", asChild = false, ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
```

- [ ] **Step 5: Grep for other base-ui imports (should be none but verify)**

Run: `grep -rn "@base-ui" daikon-gen3/frontend/src`
Expected: no results. If any surface, re-add the corresponding radix shadcn component (`pnpm dlx shadcn@latest add <name>`).

- [ ] **Step 6: Build and commit**

Run: `cd /Users/sidx/workspace/daikon-gen3/frontend && pnpm build`
Expected: succeeds.
```bash
cd /Users/sidx/workspace/daikon-gen3
git add frontend/package.json frontend/pnpm-lock.yaml frontend/components.json frontend/src/components/ui/button.tsx frontend/src/app/globals.css
git commit -m "refactor(frontend): migrate base-ui→radix + adopt @daikon/design-tokens"
```

---

## Task 13: daikon-gen3 — fonts, theme + font providers

**Files:** (from Task 12 list) layout.tsx, providers.tsx, use-font-family.ts, theme-provider.tsx, font-toggle.tsx

- [ ] **Step 1: Swap Geist → IBM Plex + Inter in layout.tsx**

Replace `daikon-gen3/frontend/src/app/layout.tsx`:
```tsx
import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/app/providers";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"] });
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "daikon-gen3",
  description: "Discovery pipeline & project-management hub",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${plexSans.variable} ${plexMono.variable} ${inter.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var v=localStorage.getItem('ds-font');document.documentElement.setAttribute('data-font',v||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}})()` }} />
      </head>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```
(Note gen3 uses a **raw** localStorage string for `ds-font`, not zustand — its anti-flash script matches.)

- [ ] **Step 2: Tiny font hook (no new dep)**

Create `src/lib/use-font-family.ts`:
```ts
"use client";
import { useCallback, useEffect, useState } from "react";

export type FontFamily = "plex" | "inter";
const KEY = "ds-font";

export function useFontFamily() {
  const [font, setFontState] = useState<FontFamily>("plex");
  useEffect(() => {
    const stored = (localStorage.getItem(KEY) as FontFamily | null) ?? "plex";
    setFontState(stored);
    document.documentElement.setAttribute("data-font", stored);
  }, []);
  const setFont = useCallback((f: FontFamily) => {
    localStorage.setItem(KEY, f);
    document.documentElement.setAttribute("data-font", f);
    setFontState(f);
  }, []);
  return { font, setFont };
}
```

- [ ] **Step 3: Theme provider (gen3 has none today)**

Create `src/components/theme-provider.tsx`:
```tsx
"use client";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="data-theme" defaultTheme="dark" enableSystem disableTransitionOnChange>
      {children}
    </NextThemesProvider>
  );
}
```
Wrap the tree in `providers.tsx` — add the import and wrap the returned JSX:
```tsx
import { ThemeProvider } from "@/components/theme-provider";
// …in the final return, wrap the AuthzProvider tree:
<ThemeProvider>
  <AuthzProvider client={initAuth(config)} autoReauth={shouldAutoReauth(pathname)}>
    {/* …unchanged… */}
  </AuthzProvider>
</ThemeProvider>
```

- [ ] **Step 4: Font toggle**

Create `src/components/font-toggle.tsx`:
```tsx
"use client";
import { Button } from "@/components/ui/button";
import { useFontFamily } from "@/lib/use-font-family";

export function FontToggle() {
  const { font, setFont } = useFontFamily();
  return (
    <div className="flex gap-1">
      <Button size="sm" variant={font === "plex" ? "default" : "outline"} onClick={() => setFont("plex")}>IBM Plex</Button>
      <Button size="sm" variant={font === "inter" ? "default" : "outline"} onClick={() => setFont("inter")}>Inter</Button>
    </div>
  );
}
```
Place `<FontToggle />` wherever gen3 exposes user/settings controls (add a theme toggle there too using `useTheme` from `next-themes`).

- [ ] **Step 5: Build and commit**

Run: `cd /Users/sidx/workspace/daikon-gen3/frontend && pnpm build`
Expected: succeeds.
```bash
cd /Users/sidx/workspace/daikon-gen3
git add frontend/src
git commit -m "feat(frontend): IBM Plex+Inter fonts, data-theme/data-font, theme provider"
```

---

## Task 14: Verify daikon-gen3

- [ ] **Step 1: Run and check**

Run: `cd /Users/sidx/workspace/daikon-gen3/frontend && pnpm dev`
Confirm: was gray → **now blue/slate**; light + dark via the theme toggle set `data-theme`; IBM Plex default, Inter toggle; the migrated `<Button>` renders all variants (default blue, outline, secondary, ghost, destructive, link) and `asChild` works; Sonner toasts styled; no FOUC; no console errors about base-ui.

---

## Task 15: Suite-wide consistency pass

- [ ] **Step 1: Side-by-side check**

Run all four `pnpm dev` (different ports). Put them side by side in light+plex, then dark+inter. Confirm identical accent blue, identical slate neutrals, identical body font, consistent radius/borders. Note any drift (usually an app-local override still present) and remove it.

- [ ] **Step 2: Update each repo's CLAUDE.md / stack docs**

Where a repo documents its frontend stack (e.g., chem-vault2 `CLAUDE.md` "Frontend" line), add a note that colors/fonts come from `@daikon/design-tokens` and fonts are a `data-font` user preference. Commit per repo.

- [ ] **Step 3: Move this spec + plan into the tokens repo (optional)**

Once `daikon-design-tokens` is the accepted hub, move `2026-07-10-design-system-harmonization-{design,plan}.md` there under `docs/` and commit.

---

## Self-Review

**Spec coverage:**
- Public npm package → Tasks 1–4. ✓
- Full `--ds-*` port into all apps → Tasks 5, 9, 11, 12. ✓
- Fonts as user preference (Plex default + Inter, mono=Plex) → Tasks 6–7, 9, 11, 13. ✓
- `data-theme` unification → Tasks 5 (docu no-op), 9/11 (provider flip), 13 (gen3 new). ✓
- gen3 base-ui→radix → Task 12. ✓
- Token-name union superset → Task 2 (found during planning; not explicit in spec, folded into package). ✓
- Verify each app + suite → Tasks 8, 10, 11.7, 14, 15. ✓
- Out of scope (shared component lib) → untouched. ✓

**Placeholder scan:** none — every CSS/TS deliverable is spelled out; the only "locate with grep" steps are for UI placement, with the grep command given.

**Type consistency:** `useFontFamilyStore` (`font`/`setFont`/`toggle`) in docu-store + cellars; `useFontFamily` (`font`/`setFont`) hook in gen3 — intentionally different (gen3 has no zustand). Storage key `ds-font` and attribute `data-font` are identical everywhere. Anti-flash script format matches each app's storage (zustand `{state:{font}}` for 3 apps; raw string for gen3).

**Risks carried from spec:** Tailwind-v4-`@theme`-from-node_modules (Task 0 spike gates everything, with a documented fallback). docu-store's layered `@import` ordering — validate in Task 5 build; if `@theme` from the package doesn't register under its `@layer` setup, apply the Task 0 fallback for docu-store specifically.
