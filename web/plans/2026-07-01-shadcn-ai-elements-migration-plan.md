# PrimeReact → shadcn/ui + AI Elements Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all PrimeReact usage (26 components, 38 files) in `apps/portal` with shadcn/ui + AI Elements with zero functional loss, then remove PrimeReact entirely and apply a "precision scientific" visual polish.

**Architecture:** Phased strangler on branch `ai-elements`: shadcn tokens bridge onto the existing `--ds-*` system (which already flips under `[data-theme="dark"]`), components are swapped feature-by-feature while PrimeReact keeps rendering untouched screens, and PrimeReact is deleted in the final phase. Chat keeps its SSE transport (`use-chat.ts` + `chat-store.ts` unchanged); AI Elements components are vendored source fed from the store.

**Tech Stack:** Next.js 16, React 19, Tailwind v4 (CSS-first, no config file), shadcn/ui (new-york), AI Elements, TanStack Table v8, sonner, cmdk, react-dropzone, lucide-react, zustand, TanStack Query.

**Spec:** `web/plans/2026-07-01-shadcn-ai-elements-migration-design.md` (approved).

## Global Constraints

- All commands run from `/Users/sidx/workspace/docu-store/web` unless stated. Package manager is **pnpm** (`pnpm dlx` not `npx`).
- **VERIFY** (referenced by tasks) = `pnpm --filter portal lint && pnpm --filter portal build` — lint is `tsc --noEmit`. Both must pass before every commit.
- Zero functional loss. Visual modernization is allowed and encouraged (user: "feel free to modernize portions of ui if required") — behavior/feature parity is the floor, looks may improve.
- Dark mode = `[data-theme="dark"]` attribute. NEVER introduce a `.dark` class. `@custom-variant dark` in globals.css already binds Tailwind's `dark:` to the attribute.
- Icons in new/changed code: **lucide-react only**. Never add `pi pi-*` classes.
- Do NOT remove any PrimeReact import, dependency, CSS override, or provider until Task 23. Coexistence is by design.
- New-code idioms: shadcn `cn()` from `@/lib/utils` for class merging; existing token utilities (`text-text-secondary`, `bg-surface-elevated`, `border-border-default`, …) remain valid everywhere.
- Commit after every task: conventional commits, message given per task, ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Before editing any file, read the whole file first. PrimeReact swap rules in tasks are transformation rules — apply them to what the file actually contains.
- Manual visual checks are batched in Task 25 (final walkthrough); per-task verification is VERIFY unless a task says otherwise.

### Shared swap rules (used by many tasks)

**R1 — Button:** `<Button label="X" icon="pi pi-foo" …>` → `<Button …><FooIcon className="size-4" />X</Button>` (shadcn `@/components/ui/button`). Prop map: `outlined`→`variant="outline"`, `text`→`variant="ghost"`, `severity="danger"`→`variant="destructive"`, `severity="secondary"`→`variant="secondary"`, no styling props→default variant, icon-only→`variant="ghost" size="icon"` + `aria-label`, `loading`→`disabled` + `<Loader2 className="size-4 animate-spin" />`, `rounded` (icon buttons)→`size="icon"` + `rounded-full` class, `size="small"`→`size="sm"`. Pick the closest lucide icon for each `pi pi-*` name.
**R2 — Tag/Chip:** `<Tag value={v} severity={s} />` → `<Badge variant={severityToVariant[s]}>{v}</Badge>`; `<Chip label={v} />` → `<Badge variant="secondary">{v}</Badge>` (removable chips: append `<button>` with `<X className="size-3" />`).
**R3 — Message:** `<Message severity="error" text={t} />` → `<Alert variant="destructive"><AlertCircle className="size-4" /><AlertDescription>{t}</AlertDescription></Alert>`. severity map: error→destructive, warn→warning, info→info, success→success (variants added in Task 3).
**R4 — Skeleton:** `<Skeleton width="Wrem" height="Hrem" />` → `<Skeleton className="h-[Hrem] w-[Wrem]" />` (use standard spacing utilities where they match, e.g. `h-4 w-16`); `shape="circle"`→ add `rounded-full`.
**R5 — SelectButton:** `<SelectButton value={v} options={opts} onChange={(e)=>set(e.value)} />` →
```tsx
<ToggleGroup type="single" variant="outline" size="sm" value={v} onValueChange={(nv) => nv && set(nv as T)}>
  {opts.map((o) => <ToggleGroupItem key={o.value} value={o.value}>{o.label}</ToggleGroupItem>)}
</ToggleGroup>
```
The `nv &&` guard preserves SelectButton's "always one selected" behavior.
**R6 — Toast:** delete `<Toast ref={toast} />` + the ref; `toast.current?.show({ severity, summary, detail })` → `toast.success|error|info|warning(summary, { description: detail })` with `import { toast } from "sonner"` (Toaster mounted globally in Task 1).
**R7 — ProgressSpinner:** → existing `<LoadingSpinner size=… />` wrapper (rebuilt in Task 4) or `<Loader2 className="size-5 animate-spin text-text-muted" />` inline.
**R8 — Dropdown:** `<Dropdown value={v} options={opts} onChange={(e)=>set(e.value)} placeholder="P" showClear />` →
```tsx
<Select value={v ?? ""} onValueChange={set}>
  <SelectTrigger className="w-[…]"><SelectValue placeholder="P" /></SelectTrigger>
  <SelectContent>{opts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
</Select>
```
`showClear` parity: where clearing matters (filters), add an "All" item mapped to clearing the state (Radix Select forbids empty-string item values — use a sentinel like `"__all__"` and translate in the handler).
**R9 — InputText:** `<InputText …>` → `<Input …>` (`@/components/ui/input`). IconField/InputIcon → `<div className="relative"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-muted" /><Input className="pl-9" … /></div>`.
**R10 — Tooltip:** PrimeReact `<Tooltip target=…>` or `tooltip` props → wrap trigger in `<Tooltip><TooltipTrigger asChild>…</TooltipTrigger><TooltipContent>text</TooltipContent></Tooltip>` (TooltipProvider mounted globally in Task 1).

---

## Phase 0 — Foundation

### Task 1: shadcn init, token bridge, base components, global providers

**Files:**
- Create: `apps/portal/components.json`, `apps/portal/src/lib/utils.ts` (CLI), `apps/portal/src/components/ui/{button,badge,alert,skeleton,input,textarea,select,dialog,alert-dialog,tabs,tooltip,popover,command,switch,toggle,toggle-group,table,breadcrumb,progress,separator,scroll-area,sonner,label}.tsx` (CLI; lowercase files coexist with the existing PascalCase wrappers in the same dir)
- Modify: `apps/portal/src/app/globals.css`, `apps/portal/src/components/providers/Providers.tsx`, ~15 files using bare `-accent` utilities (grep list in Step 4)

**Interfaces:**
- Produces: `cn(...inputs)` at `@/lib/utils`; shadcn primitives importable from `@/components/ui/<name>`; sonner `<Toaster>` and Radix `<TooltipProvider>` mounted globally; shadcn semantic tokens (`bg-background`, `text-foreground`, `bg-primary`, `text-primary`, `bg-muted`, `text-muted-foreground`, `border-border`, `bg-card`, `bg-popover`, `bg-accent` [hover tint], `ring-ring`, `bg-destructive`) live and theme-reactive.

- [ ] **Step 1: Initialize shadcn**

Run in `apps/portal/`: `pnpm dlx shadcn@latest init` — answers: style **new-york**, base color **neutral**, CSS variables **yes**. If it asks for the CSS file: `src/app/globals.css`. Then add components:

```bash
pnpm dlx shadcn@latest add button badge alert skeleton input textarea select dialog alert-dialog tabs tooltip popover command switch toggle toggle-group table breadcrumb progress separator scroll-area sonner label
```

Expected: `components.json` created; components in `src/components/ui/`; deps added (`class-variance-authority`, `tailwind-merge`, `tw-animate-css`, `@radix-ui/*`, `cmdk`, `sonner`, `next-themes` may come with sonner — fine).

- [ ] **Step 2: Rework the generated globals.css edits into the token bridge**

The CLI injects `:root`/`.dark` blocks with oklch values and `@theme inline` mappings. Replace them so shadcn tokens alias `--ds-*` (which already flip under `[data-theme="dark"]` — so NO dark block is needed for shadcn vars except none at all). Final state of the additions:

```css
@import "tw-animate-css";

:root {
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
}
```

and inside the existing `@theme inline` block, append:

```css
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
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
```

CRITICAL constraints while merging:
- Keep the `@layer theme, base, primereact, components, utilities;` declaration, the `primeicons` import, the `@custom-variant dark` line, ALL `--ds-*` blocks, ALL `.p-*` overrides, and the unlayered overrides at the bottom — untouched (deleted only in Task 23).
- Delete any `.dark { … }` block and `@custom-variant dark (&:is(.dark *))` the CLI may have added (we keep the data-theme variant).
- **Token collision (`accent`, `border`):** the existing `@theme inline` maps `--color-accent: var(--ds-accent)` (solid blue) and `--color-border-default`. Change `--color-accent: var(--accent);` (shadcn hover tint) and add `--color-accent-foreground: var(--accent-foreground);`. Keep `--color-accent-hover/light/muted/text` and `--color-border-default/subtle` exactly as they are (used by 62+ call sites). Add `--color-border: var(--border);` (new key `border` doesn't clash with `border-default`).

- [ ] **Step 3: Migrate bare `accent` utilities to `primary`**

The solid-blue meaning of bare `accent` moved to `primary`. Update these (verify with `grep -rnE '(bg|text|border|ring)-accent[" /:]' apps/portal/src --include="*.tsx" | grep -vE 'accent-(text|light|muted|hover)'`):
`bg-accent`→`bg-primary`, `text-accent`→`text-primary`, `border-accent`→`border-primary`, `focus:ring-accent`→`focus:ring-primary`, `hover:border-accent/30`→`hover:border-primary/30`, etc. Known sites: `app/[workspace]/page.tsx` (3×), `app/[workspace]/search/page.tsx`, `app/[workspace]/stats/page.tsx` (3×), `components/ui/ViewToggle.tsx`, `components/chat/ChatMessage.tsx`, `components/layout/SearchCommand.tsx` (2×), `components/layout/SidebarNavItem.tsx` (2×), `components/browse/FolderGrid.tsx`, `components/browse/CategoryBar.tsx`. Re-run the grep → zero hits.

Also run `grep -rnE '[" ](bg|text)-muted[" ]' apps/portal/src --include="*.tsx"` — any bare `text-muted`/`bg-muted` hits are pre-existing broken classes (only `text-text-muted` existed); fix them to the intended token.

- [ ] **Step 4: Mount Toaster + TooltipProvider**

In `Providers.tsx`, inside the `QueryClientProvider` (leave `PrimeReactProvider` alone until Task 23):

```tsx
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
// …
<QueryClientProvider client={queryClient}>
  <PrimeReactProvider value={primeReactConfig}>
    <TooltipProvider delayDuration={200}>
      <ThemeProvider>
        {children}
        <Toaster richColors closeButton position="top-right" />
      </ThemeProvider>
    </TooltipProvider>
  </PrimeReactProvider>
</QueryClientProvider>
```

- [ ] **Step 5: VERIFY** — both commands pass; the app still renders PrimeReact screens unchanged (tokens added, nothing consumed yet).

- [ ] **Step 6: Commit** — `feat(web): shadcn/ui foundation — init, ds-token bridge, global Toaster/TooltipProvider`

### Task 2: Install AI Elements

**Files:**
- Create: `apps/portal/src/components/ai-elements/*` (CLI-vendored)
- Modify: `apps/portal/package.json` (CLI adds `streamdown`, `use-stick-to-bottom`, `ai`, possibly `nanoid`/`zod`)

- [ ] **Step 1:** Run in `apps/portal/`: `pnpm dlx ai-elements@latest` (installs all components into `src/components/ai-elements/`). If the interactive CLI misbehaves in this monorepo, fallback: `pnpm dlx shadcn@latest add "https://registry.ai-sdk.dev/all.json"`.
- [ ] **Step 2:** Inspect what landed: `ls apps/portal/src/components/ai-elements/`. Expect at minimum: `conversation`, `message`, `response`, `reasoning`, `sources`, `prompt-input`, `loader`, `chain-of-thought` (or `task`), `actions`, `context`, `inline-citation`, `code-block`, `shimmer`. Note the actual export names — Phase 4 tasks must import what exists, not what the plan guesses.
- [ ] **Step 3:** VERIFY. Vendored-but-unused components must compile; if any pull unavailable deps, add the missing dep rather than deleting the component (unless it's clearly irrelevant, e.g. voice/workflow components — those may be deleted to keep the tree clean; record deletions in the commit message).
- [ ] **Step 4: Commit** — `feat(web): vendor AI Elements components`

### Task 3: Badge/Alert semantic variants + severity map

**Files:**
- Modify: `apps/portal/src/components/ui/badge.tsx`, `apps/portal/src/components/ui/alert.tsx`
- Create: `apps/portal/src/lib/severity.ts`

**Interfaces:**
- Produces: `Badge` variants `success | warning | info` (plus stock `default | secondary | destructive | outline`); `Alert` variants `info | success | warning` (plus stock `default | destructive`); `severityToVariant: Record<PrimeSeverity, BadgeVariant>`.

- [ ] **Step 1:** In `badge.tsx`, add to the cva `variants.variant`:

```tsx
success: "border-transparent bg-ds-success/15 text-ds-success",
warning: "border-transparent bg-ds-warning/15 text-ds-warning",
info: "border-transparent bg-ds-info/15 text-ds-info",
```

- [ ] **Step 2:** In `alert.tsx`, add to the cva `variants.variant`:

```tsx
info: "border-ds-info/30 bg-ds-info/5 text-ds-info [&>svg]:text-ds-info",
success: "border-ds-success/30 bg-ds-success/5 text-ds-success [&>svg]:text-ds-success",
warning: "border-ds-warning/30 bg-ds-warning/5 text-ds-warning [&>svg]:text-ds-warning",
```

- [ ] **Step 3:** Create `src/lib/severity.ts`:

```ts
/** PrimeReact severity → shadcn Badge variant (used during and after migration). */
export const severityToVariant = {
  success: "success",
  info: "info",
  warning: "warning",
  danger: "destructive",
  secondary: "secondary",
} as const;
export type PrimeSeverity = keyof typeof severityToVariant;
```

- [ ] **Step 4:** VERIFY, then commit — `feat(web): semantic Badge/Alert variants + severity map`

---

## Phase 1 — Primitives

### Task 4: Rebuild `components/ui/` wrapper internals

**Files:**
- Modify: `apps/portal/src/components/ui/LoadingSpinner.tsx`, `StatCard.tsx`, `TableThumbnail.tsx`, `EntityTypeBadge.tsx`, `LinkButton.tsx` + every `LinkButton`/`EntityTypeBadge` call site passing `pi pi-*` strings (grep in Step 3)

**Interfaces:**
- Consumes: shadcn `Skeleton`, `Badge` variants (Task 3)
- Produces: same public APIs as today EXCEPT `LinkButton.icon` becomes `icon?: LucideIcon` (was `pi pi-*` string).

- [ ] **Step 1:** Read all five files. Rebuild internals:
  - `LoadingSpinner.tsx`: keep the `size` prop contract; replace `ProgressSpinner` with `<Loader2 className={cn("animate-spin text-text-muted", SIZES[size], className)} aria-label="Loading" />`, `const SIZES = { sm: "size-4", md: "size-6", lg: "size-8" }`.
  - `StatCard.tsx`, `TableThumbnail.tsx`: swap Skeleton import to `@/components/ui/skeleton`, apply R4 to width/height props.
  - `EntityTypeBadge.tsx`: `Tag` → `Badge` via `severityToVariant`; `pi pi-*` icons → lucide (`FileText` document, `StickyNote` page, `FlaskConical` compound — match current icon intent per type).
  - `LinkButton.tsx`: style with shadcn `buttonVariants({ variant, size })`; change `icon` prop to `LucideIcon` and render `<Icon className="size-4" />`.
- [ ] **Step 2:** `grep -rn "LinkButton\|EntityTypeBadge" apps/portal/src --include="*.tsx" -l` — update every call site passing string icons to pass lucide components.
- [ ] **Step 3:** VERIFY, commit — `refactor(web): ui wrappers on shadcn primitives (LoadingSpinner, StatCard, TableThumbnail, EntityTypeBadge, LinkButton)`

### Task 5: Trivial screens A — errors, loading, auth gate, dashboard

**Files:**
- Modify: `apps/portal/src/app/error.tsx`, `src/app/[workspace]/error.tsx`, `src/app/[workspace]/documents/[id]/error.tsx`, `src/app/[workspace]/loading.tsx`, `src/components/providers/AuthGuardWrapper.tsx`, `src/app/[workspace]/page.tsx`

- [ ] **Step 1:** Apply R1 (Buttons in the three error boundaries), R7 (spinners in `loading.tsx`, `AuthGuardWrapper`), R4 + R2 (dashboard Skeletons and Tags — use `severityToVariant` for Tag severities). Remove the now-unused primereact imports from each file.
- [ ] **Step 2:** VERIFY, commit — `refactor(web): error/loading/auth/dashboard screens on shadcn`

### Task 6: Trivial screens B — status, stats, settings (+ReasoningSettings)

**Files:**
- Modify: `src/app/[workspace]/status/page.tsx`, `src/app/[workspace]/stats/page.tsx`, `src/app/[workspace]/settings/page.tsx`, `src/components/chat/ReasoningSettings.tsx`

- [ ] **Step 1:** Apply R5 (all SelectButtons — status view switch, stats time-range, settings toggles, ReasoningSettings level pickers), R4 (Skeletons), R7 (settings spinner). recharts code is untouched.
- [ ] **Step 2:** VERIFY, commit — `refactor(web): status/stats/settings on shadcn ToggleGroup`

### Task 7: Workflow components + Topbar breadcrumb

**Files:**
- Modify: `src/components/WorkflowList.tsx`, `src/components/WorkflowStatusBadge.tsx`, `src/components/layout/Topbar.tsx`

- [ ] **Step 1:** `WorkflowList`: R1 + R6. `WorkflowStatusBadge`: R2 via `severityToVariant` (read its severity mapping first; preserve state→color semantics).
- [ ] **Step 2:** `Topbar`: R1 for buttons (incl. theme toggle). Replace PrimeReact `BreadCrumb model={items} home={home}` with shadcn composition driven by the same `use-breadcrumbs` items:

```tsx
<Breadcrumb>
  <BreadcrumbList>
    <BreadcrumbItem><BreadcrumbLink asChild><Link href={homeHref}><Home className="size-3.5" /></Link></BreadcrumbLink></BreadcrumbItem>
    {items.map((item, i) => (
      <Fragment key={i}>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          {i === items.length - 1 || !item.url
            ? <BreadcrumbPage>{item.label}</BreadcrumbPage>
            : <BreadcrumbLink asChild><Link href={item.url}>{item.label}</Link></BreadcrumbLink>}
        </BreadcrumbItem>
      </Fragment>
    ))}
  </BreadcrumbList>
</Breadcrumb>
```

(Adapt field names to what `use-breadcrumbs` actually returns.)
- [ ] **Step 3:** VERIFY, commit — `refactor(web): workflow list/badge + topbar breadcrumb on shadcn`

---

## Phase 2 — Forms & overlays

### Task 8: Search page, PopularTags, TagFilter combobox

**Files:**
- Modify: `src/app/[workspace]/search/page.tsx`, `src/components/search/PopularTags.tsx`, `src/components/search/TagFilter.tsx`

- [ ] **Step 1:** Search page: R5 (mode switch — modernize labels/spacing freely), R1, R3. PopularTags: R2 (clickable Badges keep their onClick), R4.
- [ ] **Step 2:** Rebuild `TagFilter` on Popover+Command. Read the current file first — preserve: async/local tag suggestions, multi-select, free-text entry, AND/OR mode, removable chips. Shape:

```tsx
<div className="flex flex-wrap items-center gap-1.5">
  {selected.map((tag) => (
    <Badge key={tag} variant="secondary" className="gap-1">
      {tag}
      <button type="button" onClick={() => remove(tag)} aria-label={`Remove ${tag}`}>
        <X className="size-3" />
      </button>
    </Badge>
  ))}
  <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
      <Button variant="outline" size="sm"><Plus className="size-3.5" />Add tag</Button>
    </PopoverTrigger>
    <PopoverContent className="w-64 p-0" align="start">
      <Command shouldFilter={false}>
        <CommandInput placeholder="Filter by tag…" value={query} onValueChange={setQuery}
          onKeyDown={(e) => { if (e.key === "Enter" && query && suggestions.length === 0) { add(query); setQuery(""); } }} />
        <CommandList>
          <CommandEmpty>Press Enter to add “{query}”</CommandEmpty>
          {suggestions.map((s) => (
            <CommandItem key={s} onSelect={() => { add(s); setQuery(""); }}>{s}</CommandItem>
          ))}
        </CommandList>
      </Command>
    </PopoverContent>
  </Popover>
  {/* AND/OR: R5 ToggleGroup */}
</div>
```

Wire `suggestions` to the existing suggestion source (keep whatever hook/endpoint it uses today).
- [ ] **Step 3:** VERIFY, commit — `refactor(web): search page + tag filtering on shadcn command/badges`

### Task 9: SearchCommand → CommandDialog palette

**Files:**
- Modify: `src/components/layout/SearchCommand.tsx`

- [ ] **Step 1:** Read the file fully (keyboard shortcut handling, debounced query hook, recent-searches persistence, result groups, navigation on select). Rebuild on `CommandDialog`:
  - Trigger button in the Topbar keeps its pill look (modernize freely) and opens the dialog; keep the existing ⌘K/CTRL+K binding.
  - `<CommandDialog open={open} onOpenChange={setOpen}><CommandInput value={q} onValueChange={setQ} placeholder="Search documents, pages, compounds…" /><CommandList>` with `<CommandGroup heading="Recent">` (when `q` is empty) and result groups (Documents / Pages / Compounds) using `EntityTypeBadge`; `<CommandEmpty>` for no results; `shouldFilter={false}` (server/debounced results, not cmdk filtering).
  - On select: same router.push + recent-search recording as today.
  - Delete the two `OverlayPanel`s and their positioning logic; the `expand`/`fadeSlideDown` keyframes in globals.css become unused — leave the CSS for Task 23 to delete, but note it.
- [ ] **Step 2:** VERIFY, commit — `feat(web): command palette on cmdk (replaces OverlayPanel search)`

### Task 10: Upload page — dropzone

**Files:**
- Modify: `src/app/[workspace]/documents/upload/page.tsx`, `apps/portal/package.json`

- [ ] **Step 1:** `pnpm --filter portal add react-dropzone`
- [ ] **Step 2:** Read the page; preserve the upload mutation, per-file progress/status handling, workspace/type select, title input, multi-file support. Replace `FileUpload` with:

```tsx
const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: ACCEPT, multiple: true });
// …
<div {...getRootProps()} className={cn(
  "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border-default bg-surface-sunken px-6 py-10 text-center transition-colors cursor-pointer",
  isDragActive && "border-primary bg-accent")}>
  <input {...getInputProps()} />
  <UploadCloud className="size-8 text-text-muted" />
  <p className="text-sm text-text-secondary">Drag & drop files here, or click to browse</p>
</div>
```

plus a file list (name, size, remove `X` button, shadcn `<Progress value={pct} />` per file while uploading) driven by the existing handler state. Apply R8 (type Dropdown), R9 (title), R1 (submit), R3 (errors).
- [ ] **Step 3:** VERIFY, commit — `feat(web): upload page on react-dropzone + shadcn`

### Task 11: usePointerDrag hook + ShareDialog

**Files:**
- Create: `apps/portal/src/hooks/use-pointer-drag.ts`
- Modify: `src/components/sharing/ShareDialog.tsx`

**Interfaces:**
- Produces: `usePointerDrag(): { style: React.CSSProperties; onPointerDown: (e: React.PointerEvent) => void; reset: () => void }` — spread `style` on `DialogContent`, attach `onPointerDown` to the dialog header, call `reset()` when the dialog closes. Task 22 (SourcesPanel) consumes this too.

- [ ] **Step 1:** Create the hook:

```tsx
"use client";

import { useCallback, useRef, useState } from "react";

/** Drag-to-move for dialogs (parity with PrimeReact Dialog `draggable`). */
export function usePointerDrag() {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const origin = useRef({ px: 0, py: 0, ox: 0, oy: 0 });

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      origin.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y };
      const onMove = (ev: PointerEvent) =>
        setOffset({
          x: origin.current.ox + ev.clientX - origin.current.px,
          y: origin.current.oy + ev.clientY - origin.current.py,
        });
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [offset],
  );

  const reset = useCallback(() => setOffset({ x: 0, y: 0 }), []);

  return {
    offset,
    onPointerDown,
    reset,
    style: { transform: `translate(${offset.x}px, ${offset.y}px)` } as React.CSSProperties,
  };
}
```

- [ ] **Step 2:** Rebuild `ShareDialog` (read fully first — heaviest single file, 8 PrimeReact components). Mapping: `Dialog`→shadcn `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle` with `style` from `usePointerDrag` on content and `onPointerDown` on header (`className="cursor-move select-none"`), `reset()` on close; user/group `AutoComplete`→Popover+Command async combobox (same pattern as Task 8 Step 2, single-select: choosing a person adds a grantee row); role `Dropdown`→R8; `InputSwitch`→`<Switch checked onCheckedChange>` + `<Label>`; scope `SelectButton`→R5; grantee `Tag`s→R2; `Toast`→R6. Preserve every behavior: add/remove grantees, role changes, public-link toggle, save/error paths.
- [ ] **Step 3:** VERIFY, commit — `refactor(web): ShareDialog on shadcn (drag parity via usePointerDrag)`

### Task 12: Documents index, document detail, page viewer

**Files:**
- Modify: `src/app/[workspace]/documents/page.tsx`, `src/app/[workspace]/documents/[id]/page.tsx`, `src/app/[workspace]/documents/[id]/pages/[pageId]/page.tsx`

- [ ] **Step 1:** Index page: R9 (IconField search box), R3 (error). Leave `DocumentsTableView` untouched (Phase 3).
- [ ] **Step 2:** Detail page: `TabView activeIndex={activeTab} onTabChange` → controlled `Tabs`. The page already syncs `?tab=` via `URLSearchParams` — switch from numeric index to tab names:

```tsx
<Tabs value={tab} onValueChange={handleTabChange} className="mt-2">
  <TabsList>
    <TabsTrigger value="overview">Overview</TabsTrigger>
    <TabsTrigger value="pages">Pages</TabsTrigger>
    {/* … one per existing TabPanel, same order/labels */}
  </TabsList>
  <TabsContent value="overview">…</TabsContent>
  …
</Tabs>
```

`handleTabChange` keeps writing `sp.set("tab", name)`; map legacy numeric `?tab=` values to names when reading (`const tab = NAMES[Number(param)] ?? param ?? "overview"`) so old links keep working. Also: `confirmDialog(…)` → `AlertDialog` (`AlertDialogTrigger` on the delete button or controlled `open`; `AlertDialogAction` runs the delete mutation; keep title/description text), `Toast`→R6, `Button`→R1, `Message`→R3.
- [ ] **Step 3:** Page viewer (`[pageId]/page.tsx`): R5 (view switch), R3, R1.
- [ ] **Step 4:** VERIFY, commit — `refactor(web): documents index/detail/page-viewer on shadcn tabs+alert-dialog`

### Task 13: Browse + compounds

**Files:**
- Modify: `src/components/browse/CategoryBar.tsx`, `src/components/browse/FolderGrid.tsx`, `src/app/[workspace]/compounds/page.tsx`

- [ ] **Step 1:** R4 on both browse skeletons; compounds page R1 + R3 (StructureInput/MoleculeStructure from `@docu-store/ui` are untouched).
- [ ] **Step 2:** VERIFY, commit — `refactor(web): browse skeletons + compounds page on shadcn`

---

## Phase 3 — Tables

### Task 14: Shared DataTable wrapper (TanStack Table)

**Files:**
- Create: `apps/portal/src/components/ui/data-table.tsx`
- Modify: `apps/portal/package.json`

**Interfaces:**
- Produces:

```tsx
type FilterMeta =
  | { variant: "text"; placeholder?: string }
  | { variant: "select"; options: { label: string; value: string }[]; placeholder?: string };
// columnDef.meta?: { filter?: FilterMeta; headerClassName?: string; cellClassName?: string }

function DataTable<TData>(props: {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  isLoading?: boolean;
  emptyMessage?: string;
  defaultSorting?: SortingState;
  pageSize?: number;              // default 20
  pageSizeOptions?: number[];     // default [10, 20, 50]
}): JSX.Element;
```

Filter fns: text → TanStack `includesString` (CONTAINS parity), select → `equalsString` (EQUALS parity).

- [ ] **Step 1:** `pnpm --filter portal add @tanstack/react-table`
- [ ] **Step 2:** Create `data-table.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  type ColumnDef, type ColumnFiltersState, type RowData, type SortingState,
  flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel,
  getSortedRowModel, useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export type FilterMeta =
  | { variant: "text"; placeholder?: string }
  | { variant: "select"; options: { label: string; value: string }[]; placeholder?: string };

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    filter?: FilterMeta;
    headerClassName?: string;
    cellClassName?: string;
  }
}

const ALL = "__all__";

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  isLoading?: boolean;
  emptyMessage?: string;
  defaultSorting?: SortingState;
  pageSize?: number;
  pageSizeOptions?: number[];
}

export function DataTable<TData>({
  columns, data, isLoading = false, emptyMessage = "No results.",
  defaultSorting = [], pageSize = 20, pageSizeOptions = [10, 20, 50],
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(defaultSorting);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data, columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  const hasFilterRow = table.getAllLeafColumns().some((c) => c.columnDef.meta?.filter);
  const { pageIndex, pageSize: ps } = table.getState().pagination;
  const total = table.getFilteredRowModel().rows.length;

  return (
    <div className="overflow-hidden rounded-xl border border-border-default">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id} className="bg-surface-sunken hover:bg-surface-sunken">
              {hg.headers.map((h) => {
                const canSort = h.column.getCanSort();
                const dir = h.column.getIsSorted();
                return (
                  <TableHead
                    key={h.id}
                    style={{ width: h.column.columnDef.size !== 150 ? h.column.columnDef.size : undefined }}
                    className={cn("text-xs font-semibold uppercase tracking-wider text-text-muted", h.column.columnDef.meta?.headerClassName)}
                  >
                    {h.isPlaceholder ? null : canSort ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 hover:text-text-primary"
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {dir === "asc" ? <ArrowUp className="size-3" /> : dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-40" />}
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
          {hasFilterRow && (
            <TableRow className="bg-surface hover:bg-surface">
              {table.getAllLeafColumns().map((col) => {
                const f = col.columnDef.meta?.filter;
                return (
                  <TableHead key={col.id} className="py-1.5">
                    {f?.variant === "text" && (
                      <Input
                        value={(col.getFilterValue() as string) ?? ""}
                        onChange={(e) => col.setFilterValue(e.target.value || undefined)}
                        placeholder={f.placeholder ?? "Search…"}
                        className="h-8"
                      />
                    )}
                    {f?.variant === "select" && (
                      <Select
                        value={(col.getFilterValue() as string) ?? ALL}
                        onValueChange={(v) => col.setFilterValue(v === ALL ? undefined : v)}
                      >
                        <SelectTrigger className="h-8"><SelectValue placeholder={f.placeholder ?? "All"} /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ALL}>All</SelectItem>
                          {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          )}
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <TableRow key={i}>
                {table.getAllLeafColumns().map((c) => (
                  <TableCell key={c.id}><Skeleton className="h-4 w-full" /></TableCell>
                ))}
              </TableRow>
            ))
          ) : table.getRowModel().rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center text-text-muted">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            table.getRowModel().rows.map((row, i) => (
              <TableRow key={row.id} className={cn(i % 2 === 1 && "bg-surface-sunken/40")}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className={cell.column.columnDef.meta?.cellClassName}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between border-t border-border-default px-3 py-2 text-xs text-text-muted">
        <span className="tabular-nums">
          {total === 0 ? "0" : `${pageIndex * ps + 1}–${Math.min((pageIndex + 1) * ps, total)}`} of {total}
        </span>
        <div className="flex items-center gap-2">
          <Select value={String(ps)} onValueChange={(v) => table.setPageSize(Number(v))}>
            <SelectTrigger className="h-7 w-[70px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {pageSizeOptions.map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="ghost" size="icon" className="size-7" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()} aria-label="Previous page">
            <ChevronLeft className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" className="size-7" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()} aria-label="Next page">
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3:** VERIFY, commit — `feat(web): shared TanStack DataTable with column filters + pagination`

### Task 15: Migrate DocumentsTableView + PagesTab

**Files:**
- Modify: `src/components/documents/DocumentsTableView.tsx`, `src/components/documents/PagesTab.tsx`

**Interfaces:**
- Consumes: `DataTable`, `FilterMeta` from `@/components/ui/data-table` (Task 14).

- [ ] **Step 1:** Rewrite `DocumentsTableView` — keep the `enriched` `_search` composite and all cell templates (they become `cell` renderers verbatim):

```tsx
const columns: ColumnDef<ArtifactWithSearch, unknown>[] = [
  {
    id: "document",
    header: "Document",
    accessorKey: "_search",
    filterFn: "includesString",
    sortingFn: (a, b) => (a.original.source_filename ?? "").localeCompare(b.original.source_filename ?? ""),
    meta: { filter: { variant: "text", placeholder: "Search…" } },
    cell: ({ row }) => documentTemplate(row.original),
  },
  {
    id: "artifact_type",
    header: "Type",
    accessorKey: "artifact_type",
    filterFn: "equalsString",
    size: 160,
    meta: { filter: { variant: "select", options: typeOptions } },
    cell: ({ row }) => typeTemplate(row.original),
  },
  {
    id: "date",
    header: "Date",
    accessorFn: (r) => r.presentation_date?.date ?? "",
    size: 110,
    cell: ({ row }) => dateTemplate(row.original),
  },
  {
    id: "pages",
    header: "Pages",
    accessorFn: (r) => r.pages?.length ?? 0,
    size: 70,
    cell: ({ row }) => pagesTemplate(row.original),
  },
  { id: "tags", header: "Tags", enableSorting: false, size: 180, cell: ({ row }) => tagsTemplate(row.original) },
];

return (
  <DataTable
    columns={columns}
    data={enriched}
    isLoading={isLoading}
    emptyMessage="No documents found."
    defaultSorting={[{ id: "document", desc: false }]}
  />
);
```

`typeTemplate`'s `<Tag severity="info" rounded />` → `<Badge variant="info" className="rounded-full">{label}</Badge>`.
- [ ] **Step 2:** `PagesTab`: same pattern (read file; one text-filtered column, keep templates, drop `FilterMatchMode`).
- [ ] **Step 3:** VERIFY, commit — `refactor(web): documents/pages tables on shared DataTable`

### Task 16: Migrate FolderArtifactList

**Files:**
- Modify: `src/components/browse/FolderArtifactList.tsx`

- [ ] **Step 1:** Same pattern as Task 15 Step 1 (read file; text + select filters, Tag→Badge, keep templates and default sort).
- [ ] **Step 2:** VERIFY, commit — `refactor(web): folder artifact table on shared DataTable`

---

## Phase 4 — Chat (transport unchanged: `use-chat.ts` + `chat-store.ts` are NOT modified in this phase)

### Task 17: Conversation shell — ChatPanel, ConversationSidebar

**Files:**
- Modify: `src/components/chat/ChatPanel.tsx`, `src/components/chat/ConversationSidebar.tsx`, `src/components/chat/MessageList.tsx`

- [ ] **Step 1:** `ChatPanel`: R1 (toggle buttons), `Badge`→shadcn Badge (source count). Wrap the message scroll area with AI Elements `Conversation`/`ConversationContent`/`ConversationScrollButton` (from `@/components/ai-elements/conversation`) — this replaces any hand-rolled scroll-to-bottom logic in `MessageList`/`ChatPanel` (read both; delete the manual scroll effect if present, keep everything else: source-priority logic, queued-message flow, header).
- [ ] **Step 2:** `ConversationSidebar`: R1 (New Chat), restyle list rows with `cn()` + existing tokens; wrap list in `ScrollArea`. Keep create/delete/navigate behavior identical.
- [ ] **Step 3:** VERIFY, commit — `feat(web): chat shell on AI Elements Conversation`

### Task 18: ChatInput → PromptInput

**Files:**
- Modify: `src/components/chat/ChatInput.tsx`

- [ ] **Step 1:** Read the file. Rebuild on AI Elements `PromptInput` (vendored — adapt its props if they assume AI SDK types): keep local `value` state, submit handler, Enter-to-send/Shift+Enter newline, disabled-while-streaming, abort affordance if present. Shape:

```tsx
<PromptInput onSubmit={(e) => { e.preventDefault(); handleSend(); }}>
  <PromptInputTextarea
    value={value}
    onChange={(e) => setValue(e.currentTarget.value)}
    placeholder="Ask about your documents…"
  />
  <PromptInputToolbar>
    <PromptInputTools>
      <ModeToggle … />        {/* keep existing custom component */}
      <ReasoningToggle … />   {/* keep existing custom component */}
    </PromptInputTools>
    <PromptInputSubmit disabled={!value.trim()} status={isStreaming ? "streaming" : undefined} />
  </PromptInputToolbar>
</PromptInput>
```

(Exact subcomponent names per what Task 2 vendored — check `prompt-input.tsx` exports.) PrimeReact `Tooltip` uses → R10.
- [ ] **Step 2:** VERIFY, commit — `feat(web): chat composer on AI Elements PromptInput`

### Task 19: MarkdownRenderer → Streamdown (citations preserved)

**Files:**
- Modify: `src/components/chat/MarkdownRenderer.tsx`

- [ ] **Step 1:** Swap `ReactMarkdown`+`remarkGfm` for `Streamdown` — the rest of the file (CITATION_PATTERN, styleCitations, replaceCitationsInText, all component overrides) stays byte-identical:

```tsx
import { Streamdown } from "streamdown";
// delete: react-markdown + remark-gfm imports
// …
<Streamdown components={{ /* same table/thead/th/td/code/a/p/li overrides */ }}>
  {content}
</Streamdown>
```

Streamdown bundles GFM and hardens incomplete/streaming markdown (unterminated bold/code fences no longer flash raw). It accepts react-markdown-style `components`. **Fallback (only if citation buttons break under Streamdown):** keep react-markdown here exactly as-is and note it in the commit; parity outranks the library swap.
- [ ] **Step 2:** VERIFY. Manual spot-check (needs backend running: `make docker-up` in services/ if not already): stream a chat answer with citations — `[3]` renders as a clickable chip, click flashes the source row (citation-highlight), tables/code render styled.
- [ ] **Step 3:** Commit — `feat(web): streaming-safe chat markdown via Streamdown`

### Task 20: Reasoning + agent-process panels

**Files:**
- Modify: `src/components/chat/ReasoningDisclosure.tsx`, `src/components/chat/AgentThinkingPanel.tsx`, `src/components/chat/AgentStepIndicator.tsx`, `src/components/chat/ChatMessage.tsx` (ThinkingDots)

- [ ] **Step 1:** `ReasoningDisclosure` → AI Elements `Reasoning`/`ReasoningTrigger`/`ReasoningContent`: pass `isStreaming` so it auto-opens while reasoning streams and auto-closes after (preserve current open/close UX; content is `agent_trace.reasoning_content` rendered through MarkdownRenderer as today).
- [ ] **Step 2:** `AgentThinkingPanel` + `AgentStepIndicator` → AI Elements `ChainOfThought` (or `Task` if ChainOfThought wasn't vendored): map `streamingSteps`/`ThinkingBlock[]` to `ChainOfThoughtStep`s (label = step name, status = pending/active/complete from step state, duration badge kept, expandable `thinking_content` kept). `QueryPlanCard` and the dev-mode pipeline summary remain custom children inside the panel. Keep the auto-collapse-when-done behavior.
- [ ] **Step 3:** `ThinkingDots` → AI Elements `Loader` (or `Shimmer` on the "Thinking…" label — pick what reads best).
- [ ] **Step 4:** VERIFY, commit — `feat(web): reasoning + agent steps on AI Elements Reasoning/ChainOfThought`

### Task 21: Message bubbles, actions, token usage

**Files:**
- Modify: `src/components/chat/ChatMessage.tsx`, `src/components/chat/MessageList.tsx`

- [ ] **Step 1:** Rebuild bubble chrome with AI Elements `Message`/`MessageContent` (+ `MessageAvatar` where the current design shows avatars): `from={role}`, assistant content = existing `AgentThinkingPanel` + `ReasoningDisclosure` + `RichContentRenderer`/`MarkdownRenderer` composition (unchanged children), user content = plain. Feedback thumbs + copy → AI Elements `Actions`/`Action` with the existing `useChatFeedback` mutation and clipboard logic. `GroundingBar` stays custom.
- [ ] **Step 2:** Token-usage display → AI Elements `Context` component if its shape fits the existing per-message usage data (input/output/total tokens from the done event); otherwise keep the current custom display restyled with tokens/mono. Dev-mode diagnostics block stays custom.
- [ ] **Step 3:** `MessageList` pending/streaming placeholder bubbles: keep logic, render through the same `Message` primitives.
- [ ] **Step 4:** VERIFY, commit — `feat(web): chat messages on AI Elements Message/Actions/Context`

### Task 22: SourcesPanel + DataTableBlock

**Files:**
- Modify: `src/components/chat/SourcesPanel.tsx`, `src/components/chat/DataTableBlock.tsx`

- [ ] **Step 1:** `SourcesPanel` (read fully): keep artifact grouping, `AuthThumbnail`s, collapsible citation rows, citation-highlight wiring. Swap: R1 buttons, R4 skeletons; page-preview `Dialog` (`draggable resizable` + custom `pt`) → shadcn `Dialog` + `usePointerDrag` (Task 11 — `style` on `DialogContent`, `onPointerDown` on its header, `reset()` on close) and `resize: both; overflow: auto` via className `resize overflow-auto` on the content body for resize parity. Consider AI Elements `Sources`/`InlineCitation` for the row chrome where it drops code; keep custom where the grouped layout doesn't fit.
- [ ] **Step 2:** `DataTableBlock`: PrimeReact `DataTable size="small" stripedRows scrollable` → plain shadcn `Table` in an `overflow-x-auto` wrapper with striped rows (`odd:bg-surface-sunken/40`), compact cells (`py-1.5 px-3 text-sm`). No TanStack needed (static content block).
- [ ] **Step 3:** VERIFY, commit — `refactor(web): chat sources panel + table blocks on shadcn`

---

## Phase 5 — Removal & polish

### Task 23: Remove PrimeReact entirely

**Files:**
- Modify: `apps/portal/package.json`, `packages/ui/package.json`, `packages/ui/src/index.ts` (stale comment), `apps/portal/src/components/providers/Providers.tsx`, `apps/portal/src/components/providers/ThemeProvider.tsx`, `apps/portal/src/app/globals.css`
- Delete: `apps/portal/scripts/copy-primereact-themes.mjs`, `apps/portal/public/primereact-themes/`

- [ ] **Step 1:** Gate: `grep -rn "primereact\|primeicons\|pi pi-" apps/portal/src packages/*/src --include="*.ts" --include="*.tsx" | grep -v node_modules` — the ONLY remaining hits must be `Providers.tsx` (PrimeReactProvider) and `ThemeProvider.tsx` (theme link). Any other hit = a missed migration; fix it first (apply the matching rule R1–R10).
- [ ] **Step 2:** `Providers.tsx`: delete `PrimeReactProvider` import, `primeReactConfig`, and the wrapper element (children move up one level); update the ordering doc-comment.
- [ ] **Step 3:** `ThemeProvider.tsx` becomes attribute-only:

```tsx
"use client";

import { useEffect, type ReactNode } from "react";

import { useThemeStore } from "@/lib/stores/theme-store";

/** Applies the persisted theme as a data-theme attribute (tokens flip via CSS). */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return <>{children}</>;
}
```

(The anti-flash inline script in `app/layout.tsx` stays.)
- [ ] **Step 4:** globals.css: change layer decl to `@layer theme, base, components, utilities;`; delete the `primeicons` import and its comment; delete the "PrimeReact dark overrides" + "App-wide PrimeReact sizing baseline" blocks (lines ~236–408 today: everything matching `.p-*`) and the entire unlayered `.p-selectbutton` section at the bottom; delete the now-unused `expand`/`fadeSlideDown` keyframes (SearchCommand no longer uses them — confirm with grep); update the header comment (PrimeReact coexistence note → gone). KEEP: `--ds-*` blocks, `@theme inline`, `@custom-variant dark`, body/focus/selection/scrollbar styles, `citation-flash`, `fade-in`/`auth-enter`/`page-enter`.
- [ ] **Step 5:** `apps/portal/package.json`: remove `primereact` + `primeicons` deps; `postinstall` → `node scripts/copy-rdkit-wasm.mjs`. Delete `scripts/copy-primereact-themes.mjs` and `public/primereact-themes/`. `packages/ui/package.json`: remove `primereact`/`primeicons` from peer+devDependencies; fix the stale "PrimeReact-based" header comment in `packages/ui/src/index.ts`. If `react-markdown`/`remark-gfm` are no longer imported anywhere (`grep -rn "react-markdown\|remark-gfm" apps/portal/src`), remove those deps too (skip removal if Task 19 used the fallback).
- [ ] **Step 6:** `pnpm install` (regenerates lockfile), then VERIFY, then re-run the Step 1 grep → **zero hits anywhere**.
- [ ] **Step 7:** Commit — `feat(web)!: remove PrimeReact — shadcn/ui + AI Elements only`

### Task 24: "Precision scientific" polish pass

**Files:**
- Modify: visual-only touches across `apps/portal/src` (no behavior changes); `apps/portal/src/app/globals.css` for shared styles

Use the **frontend-design skill** for this task. Direction (from spec): near-monochrome base, existing blue accent as the single accent, hairline borders, minimal shadows, monospace for data, dense-but-airy layouts, restrained motion. Concrete checklist:

- [ ] **Step 1:** Data-mono treatment: `font-mono tabular-nums` (+ smaller size where fitting) on: SMILES strings (`CopySmiles`, compound cells), artifact/page IDs, dates + page counts in tables (already `tabular-nums`, add mono), token counts (ChatMessage usage, stats page metrics), scores (`ScoreBadge` values), version/status strings on the status page.
- [ ] **Step 2:** Density + chrome audit: consistent control heights (`h-8` inputs/buttons in chrome and filter rows, default sizes in forms), consistent `rounded-lg`→`--radius` usage, table header uppercase-tracking treatment everywhere (DataTable already does), replace any leftover heavy shadows with `shadow-ds-sm`/hairlines.
- [ ] **Step 3:** Focus/hover: verify `:focus-visible` ring (kept in globals.css) is visible on shadcn controls in both themes; hover states use `bg-accent` tint not solid blues.
- [ ] **Step 4:** Contrast pass in BOTH themes on the new Badge/Alert tinted variants (`/15`, `/5` alphas) against `--ds-surface*` — bump alphas if AA fails for text sizes used.
- [ ] **Step 5:** VERIFY + dev-server screenshot sweep (light + dark) of: dashboard, documents table, doc detail, upload, search, compounds, chat with sources open, settings, status, stats.
- [ ] **Step 6:** Commit — `style(web): precision-scientific polish pass (mono data, density, focus/contrast)`

### Task 25: Full parity walkthrough (final gate)

Needs the backend up (`make docker-up` in `services/`) and `pnpm --filter portal dev` (port 15000).

- [ ] **Step 1:** Walk the risk-register checklist from the spec, in both themes:
  1. Documents table: text filter, type filter, sort each column, page through, change page size.
  2. Browse folder table: same.
  3. Doc detail: tab switching updates `?tab=` and survives reload + old numeric `?tab=1` links; delete flow shows AlertDialog; toasts fire.
  4. Upload: drag-drop multiple files, progress bars, remove file, submit, error path.
  5. Share dialog: search user, add/remove grantee, change role, toggle public link, save; drag the dialog by its header.
  6. Search page: mode switch, tag filter add/remove/AND-OR, popular tags click.
  7. ⌘K palette: recents, live results, keyboard nav, navigate.
  8. Chat: send message → steps stream in ChainOfThought, reasoning auto-opens/closes, tokens stream, `[N]` citation click flashes source, sources panel preview dialog opens/drags/resizes, molecule blocks render, table blocks render, feedback thumbs + copy, token usage shown, abort mid-stream, new-conversation queue flow.
  9. Theme toggle: instant flip, no flash on reload, no unstyled flash mid-stream.
  10. Compounds: draw structure in Ketcher, search, results render.
- [ ] **Step 2:** Fix anything broken (root cause, matching rule), VERIFY, commit fixes individually.
- [ ] **Step 3:** Final commit if needed — `test(web): parity walkthrough fixes`

---

## Self-review notes

- Spec coverage: Decisions 1–5 → Tasks 17–22 (chat/transport), 1–2 (stack), 1+23 (theming), phase structure (strangler), 24 (visual direction). Risk register items 1–10 → Tasks 11/22 (drag/resize), 14–16 (filters), 10 (upload), 8/11 (comboboxes), 9 (palette), R6 (toasts), ripple intentionally dropped (Task 23 removes provider), 12 (tab sync), 23 (theme flash — link swap deleted), 23 (packages/ui deps).
- AI Elements subcomponent names are verified against the vendored source in Task 2 Step 2 — later tasks say "check exports" where names could drift.
- No test framework exists in web/; VERIFY (tsc + next build) + Task 25 walkthrough is the regression harness per spec.
