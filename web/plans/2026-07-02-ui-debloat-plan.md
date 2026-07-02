# UI De-bloat: make components fit shadcn/AI Elements defaults

Continuation of the chat-page pass (commit `8b6d44f`). Sweep the remaining
portal UI so vendored shadcn/ui + AI Elements components render with their
intended defaults instead of being fought with overrides.

## Global Constraints

- **Deletion over addition.** The shortest diff that lets the component's own
  defaults render. If an override merely re-states the default in `--ds-*`
  vocabulary, delete it.
- **Known dead weight:** `@tailwindcss/typography` is NOT installed — every
  `prose*` class in the app is a no-op; delete on sight. Streamdown's dist IS
  now `@source`d in globals.css, so its built-in markdown styling (headings,
  tables, code blocks, links) works — hand-rolled markdown element renderers
  are redundant.
- **Reuse before rebuild:** hand-rolled spinners/skeletons/badges/empty
  states/buttons must use the existing components in `src/components/ui/`
  (Skeleton, Badge, Button, EmptyState, Tooltip, …) or AI Elements
  equivalents already vendored in `src/components/ai-elements/`.
- **Do NOT touch** vendored files in `src/components/ai-elements/` or
  lowercase shadcn primitives in `src/components/ui/` (they are registry
  code). PascalCase app components anywhere are fair game.
- **Do NOT change** data fetching, stores, hooks, SSE transport, or any
  behavior — this is presentation-layer only. Keep accessibility attributes
  (aria-*, sr-only, roles) intact or improved, never removed.
- **Keep** the `--ds-*` token system and app chrome (top bars, panel borders,
  feature accent colors). Overrides justified by an existing code comment
  stay unless the justification is now false.
- Verify with `cd web/apps/portal && pnpm lint` (tsc --noEmit). No tests
  exist for these components; do not add a test framework (YAGNI) — the
  typecheck plus a careful read is the gate.
- Commit per task on branch `ai-elements`, message style
  `refactor(web): <area> fits component defaults`.

## Tasks

### Task 1: Chat page leftovers

Files: `src/components/chat/{SourcesPanel,ConversationSidebar,CitationList,ReasoningSettings,DataTableBlock,MoleculeBlock,RichContentRenderer,ChatLayout}.tsx`

Audit each against the Global Constraints. Known suspects: hand-rolled
hover/active row styling duplicating Button/ghost variants, custom badges,
dead prose classes, spacing overrides. SourcesPanel uses a drag-dialog
(`usePointerDrag`) — that mechanism stays.

### Task 2: Search

Files: `src/app/[workspace]/search/**`, `src/components/search/**`

Same audit. Search result cards, score meters, filter chips — check for
re-implementations of Badge/Progress/Card/Skeleton and dead classes.

### Task 3: Documents

Files: `src/app/[workspace]/documents/**`, `src/components/documents/**`,
`src/components/{PdfEmbed,WorkflowList,WorkflowStatusBadge}.tsx`

Same audit. DataTable-based lists should lean on the shared
`ui/data-table.tsx` defaults; upload flow Progress/EmptyState usage.

### Task 4: Compounds + browse

Files: `src/app/[workspace]/compounds/**`, `src/components/browse/**`,
`src/components/EntityTagPanel.tsx`

Same audit.

### Task 5: Layout + settings/status/stats + sharing

Files: `src/components/layout/**`, `src/components/sharing/**`,
`src/app/[workspace]/{settings,status,stats}/**`

Same audit. Sidebar/Topbar keep the `--ds-sidebar-*` token look; the check
here is for duplicated primitives (tooltips, buttons, separators) and dead
classes, not a redesign.

### Task 6: ui/ wrapper dedupe

Files: PascalCase wrappers in `src/components/ui/` (Card, EmptyState,
LoadingSpinner, StatCard, PageHeader, LinkButton, ViewToggle, ScoreBadge,
EntityTypeBadge, CopySmiles, TableThumbnail) and `src/components/backgrounds/**`

For each wrapper: if it merely re-implements a lowercase shadcn primitive
(e.g. hand-rolled card chrome vs `card.tsx` patterns, custom spinner vs
`Loader`), migrate it onto the primitive or delete it and update call sites.
If it adds real app semantics, keep it. This task may touch call sites
across the app — run it LAST.
