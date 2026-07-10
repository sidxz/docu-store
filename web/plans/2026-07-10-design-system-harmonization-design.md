# Design System Harmonization — 4 Frontend Apps

**Date:** 2026-07-10
**Status:** Approved design → pending spec review → implementation plan
**Scope:** cross-repo (chem-cellar / chem-vault2, prot-cellar, docu-store, daikon-gen3)
**Permanent home:** this spec should move into the new `daikon-design-tokens` repo (created in Phase 1). It lives here for now because docu-store is the color source of truth and the established home for frontend design docs.

---

## 1. Goal

Make four independently-built Next.js apps read as one product suite by unifying:

- **Colors** — docu-store's blue + slate `--ds-*` token system, everywhere.
- **Fonts** — IBM Plex Sans/Mono (from chem-cellar) *and* Inter (from docu-store), offered as a **user preference**, default IBM Plex.
- **Component primitive** — Radix UI + shadcn/ui across all four (daikon-gen3 migrates off base-ui).
- **Distribution** — a single published package, `@daikon/design-tokens` (public npm), consumed by all four.

Non-goal: a shared component library. Flagged as the natural next step, explicitly out of scope here (§9).

---

## 2. Current State

| App | Fonts | Primitive | Dark mode | Palette |
|-----|-------|-----------|-----------|---------|
| **chem-cellar** (chem-vault2) | IBM Plex Sans + Mono | radix-ui + shadcn | `.dark` class (next-themes) | OKLCH, blue accent |
| **prot-cellar** | IBM Plex Sans + Mono | radix-ui + shadcn | `.dark` class (next-themes) | OKLCH, **teal** accent |
| **docu-store** ⭐ color source | Inter (no mono) | radix-ui + shadcn | `[data-theme="dark"]` (custom provider) | hex `--ds-*` layered, **blue `#3b82f6`** |
| **daikon-gen3** | Geist + Geist Mono | **@base-ui/react** + shadcn v4 | `.dark` class | OKLCH default **gray** (no brand) |

Notes established during exploration:
- `@sentinel-auth/*` (used by all four) resolves from **public npm** — the Docker build is a plain `pnpm install --frozen-lockfile` with no `.npmrc`, no token. This is the template for `@daikon/design-tokens`.
- daikon-gen3's `ui/` folder holds only `button.tsx` (sole base-ui importer) and `sonner.tsx`. The "radix migration" is ~1 component, not a rewrite.
- All three cellar-style apps import Tailwind identically (`@import "tailwindcss"`), so a package `@import` slots in cleanly.
- Design tokens are not secret — they ship in every app's CSS and are readable in any browser's devtools. Hence public npm, not a private registry.

---

## 3. Target Architecture

### 3.1 Shared package — `@daikon/design-tokens`

- **Repo:** new, dedicated `sidxz/daikon-design-tokens` (~4 files). Independent version lifecycle; not nested in an app repo.
- **Registry:** **public npm**, published `--access public`, scope `@daikon`. Installs via the existing `pnpm install --frozen-lockfile` — no Dockerfile, CI, or dev-auth changes (mirrors `@sentinel-auth`).
- **Content:** CSS-only. Its content *is* docu-store's current token system, lifted verbatim — docu-store becomes the first consumer of its own extracted tokens (dogfood).
- **Prod impact:** none at runtime (build-time CSS dep; Tailwind inlines it into each app's `.next/static`; the running container never touches a registry).

**`tokens.css` ships:**

- `:root` — the `--ds-*` primitives: surfaces, borders, text, **blue accent (`#3b82f6` light / `#60a5fa` dark)**, sidebar, semantic (success/warning/error/info), score-severity, shadows, `--radius` — plus the shadcn bridge (`--background` … `--ring` → `var(--ds-*)`).
- `[data-theme="dark"]` — docu-store's exact dark values.
- `@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *))`.
- `@theme inline` — the Tailwind color/radius map + the `--font-sans` / `--font-mono` indirection (§3.3).
- Base rules: `* { border-color: var(--border) }`, body font-smoothing, scrollbar, selection, focus-ring.

**Stays app-local** (not in the package — app-specific, not "the system"): docu-store's `citation-flash`, page transitions, streamdown `@source`, and `feature-*` colors.

### 3.2 Colors — unified on `data-theme`

All four apps standardize the dark-mode selector on the `data-theme` attribute so one CSS file works everywhere:

- **docu-store** — dark selector unchanged (already `[data-theme="dark"]` + custom provider with theme/font-scale persistence). It still extracts its tokens into the package and adds the font switch — see §4.
- **chem-cellar, prot-cellar, daikon-gen3** — flip next-themes `attribute="class"` → `attribute="data-theme"` (or `["class","data-theme"]`); delete their local token block; `@import "@daikon/design-tokens/tokens.css"`. `@custom-variant dark` now comes from the package.
- Before flipping: grep each app for hardcoded `.dark` selectors / `classList` toggles in component code and update.
- **prot-cellar's teal accent is intentionally dropped** — it becomes blue like the rest.

### 3.3 Fonts — a user preference (`data-font`), default IBM Plex

Two font families are offered suite-wide; the user picks. next/font is build-time per app, so **each app loads both families** and the choice switches which CSS variable `--font-sans` resolves to.

- **Per-app `layout.tsx`** exposes three next/font variables:
  - `IBM_Plex_Sans` (weights 400/500/600/700) → `--font-plex-sans`
  - `IBM_Plex_Mono` (weights 400/500/600) → `--font-plex-mono`
  - `Inter` (latin) → `--font-inter`
- **Package `tokens.css` owns the switch** (the contract each app must satisfy by defining those three variables):
  ```css
  :root { --font-sans: var(--font-plex-sans); --font-mono: var(--font-plex-mono); }   /* default: IBM Plex */
  [data-font="inter"] { --font-sans: var(--font-inter); }                              /* mono stays Plex Mono */
  @theme inline { --font-sans: var(--font-sans); --font-mono: var(--font-mono); }
  ```
- **Mono is always IBM Plex Mono.** The preference toggles the *sans/body* family only (Plex Sans ↔ Inter). Inter ships no mono; code/data stays on Plex Mono. *(Decision — confirm; §10.)*
- **Persistence & no-flash:** `data-font` on `<html>`, persisted to `localStorage['ds-font']` (`plex` | `inter`, default `plex`). A minimal inline script in each layout sets `data-font` before first paint (mirrors docu-store's existing theme/font-scale inline script) to avoid a font flash. A small shared zustand store (all four apps already use zustand) drives the runtime toggle.
- **UI:** a font switcher in each app's settings / user menu. Mechanism is the substance; the control is a trivial two-option select.

Net effect: `data-theme` (light/dark) and `data-font` (plex/inter) are two suite-wide user preferences on the same attribute-based, persisted, no-flash pattern.

### 3.4 Component primitive — Radix everywhere

daikon-gen3 migrates base-ui → radix to match the other three:
- Re-point `components.json` to the radix/shadcn config the other three use.
- Remove `@base-ui/react` and the `@import "shadcn/tailwind.css"` runtime.
- Re-add `button` (and verify `sonner`) from the radix shadcn registry — reuse the generated components, do not hand-roll.

---

## 4. Per-App Change Matrix

| App | Fonts | Colors | Provider | Components |
|-----|-------|--------|----------|------------|
| **docu-store** | +load IBM Plex Sans/Mono alongside Inter; wire `data-font` | extract tokens → package, import back; drop dupes | unchanged (`data-theme`) + add `data-font` | unchanged |
| **chem-cellar** | +load Inter alongside Plex; wire `data-font` | delete OKLCH block → import package | `attribute` class→`data-theme`; add `data-font` | unchanged |
| **prot-cellar** | +load Inter alongside Plex; wire `data-font` | delete OKLCH block (**teal→blue**) → import package | `attribute` class→`data-theme`; add `data-font` | unchanged |
| **daikon-gen3** | Geist→Plex+Inter; wire `data-font` | delete default gray block → import package | flip to `data-theme` (wire provider — none present today); add `data-font` | **base-ui→radix** (button + sonner), drop shadcn-v4 css |

---

## 5. Shared Package Files

```
daikon-design-tokens/
  package.json          # name @daikon/design-tokens, exports ./tokens.css, publishConfig public
  tokens.css            # the canonical system (§3.1)
  no-flash.js           # optional inline snippet apps embed for data-theme/data-font
  README.md             # consumer contract: @import path + required --font-plex-*/--font-inter vars
  .github/workflows/    # publish to public npm on git tag
```

**Consumer contract (documented in README):**
1. `@import "@daikon/design-tokens/tokens.css";` after `@import "tailwindcss";`.
2. Define `--font-plex-sans`, `--font-plex-mono`, `--font-inter` via next/font in `layout.tsx`.
3. Manage `data-theme` and `data-font` on `<html>`; embed the no-flash snippet.

---

## 6. Rollout Plan (ordered)

1. **Spike (~15 min):** confirm Tailwind v4 honors `@theme` from a `node_modules` CSS import. **Fallback if not:** package ships raw `--ds-*` + variant only; each app keeps a thin `@theme` map (still DRY on values).
2. **Build + publish `@daikon/design-tokens` v1** from docu-store's tokens → public npm. Move this spec into that repo.
3. **docu-store:** consume the package (dogfood — should be a visual no-op); add IBM Plex + Inter font switch. Verify.
4. **chem-cellar + prot-cellar:** import package, delete local tokens, flip provider to `data-theme`, add Inter + font switch. Verify (prot-cellar visibly goes blue).
5. **daikon-gen3:** import package, swap Geist→Plex+Inter, base-ui→radix, wire `data-theme`/`data-font` provider. Verify.

Each app is verified visually (light + dark, both fonts) before moving on.

---

## 7. Risks

- **Tailwind v4 `@theme` from node_modules** — main technical unknown; de-risked by the Phase-1 spike + fallback.
- **Provider attribute flip** — residual hardcoded `.dark` selectors or `classList` toggles in the three class-based apps. Mitigation: grep before flipping.
- **Font flash** — mitigated by the inline `data-font` no-flash script in every layout.
- **daikon-gen3 provider** — no theme-provider file found today; may need one wired (next-themes is already a dependency).

---

## 8. "Extra UI frameworks from docu-store" clause

Treated as a **standing principle**, not a bulk import: when an app newly needs a capability docu-store already standardized (recharts for charts, Uppy for uploads, streamdown/AI-elements for chat), reach for docu-store's choice rather than introducing a competing library. No mass installation in this effort.

---

## 9. Out of Scope

- **Shared Radix component library** (`@daikon/ui`) — the logical successor once all four share tokens + radix, but not part of this effort.
- Any backend, layout, or feature changes. This is a theming + primitive-alignment effort only.

---

## 10. Decisions to Confirm

1. **Mono font behavior** — proposed: mono is always IBM Plex Mono; the `data-font` toggle switches only the sans/body family (Plex Sans ↔ Inter). Alternative: pair Inter with a non-Plex mono.
2. **Default font** — proposed: IBM Plex (honors the original "fonts from chem-cellar" directive). Inter is the opt-in alternative.
3. **Spec location** — currently `docu-store/web/plans/`; moves to `daikon-design-tokens` in Phase 1. Confirm or relocate.
