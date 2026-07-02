# PrimeReact → shadcn/ui + AI Elements Migration — Design

**Date:** 2026-07-01 · **Branch:** `ai-elements` · **Status:** awaiting user review

## Goal

Completely replace PrimeReact (26 components across 38 files in `apps/portal`) with
shadcn/ui + AI Elements, with **zero feature loss**, and land a visual refresh that reads
as modern and scientific. The FastAPI backend, chat SSE protocol, RDKit/Ketcher molecule
stack, and all app behavior are unchanged.

## Non-goals

- No backend changes (chat protocol stays custom SSE; see Chat section).
- No route or state-management changes (Next 16 app router, zustand, TanStack Query stay).
- No rewrite of already-Tailwind components (Sidebar, SearchResultCard, EntityTagPanel, …)
  beyond token/polish alignment.

## Decisions (defaults chosen while user AFK — flag any to change)

| # | Decision | Choice |
|---|---|---|
| 1 | Chat wiring | **Keep `use-chat.ts` + `chat-store.ts` + FastAPI SSE unchanged.** AI Elements components are vendored source; feed them from the existing store as controlled/presentational components. No AI SDK `useChat`, no backend work. |
| 2 | Component stack | shadcn/ui (Radix + cva + tailwind-merge), AI Elements (chat), TanStack Table v8 (tables), sonner (toasts), cmdk via shadcn Command (palette + comboboxes), react-dropzone (upload). Icons: lucide-react only — primeicons removed. recharts stays for stats. |
| 3 | Theming | Keep `data-theme` attribute + zustand theme store + anti-flash script. Define shadcn semantic tokens as CSS variables in `globals.css` for light and `[data-theme="dark"]`, layered onto the existing `--ds-*` token system. Existing `@custom-variant dark` already binds `dark:` to the attribute — shadcn components work unmodified. |
| 4 | Migration strategy | Phased strangler on this branch: 6 phases, app builds and works after each. PrimeReact coexists (CSS layers already isolate it) until Phase 5 removes it. |
| 5 | Visual direction | "Precision scientific": near-monochrome neutral base, one sharp blue/cyan accent, 1px hairline borders, minimal shadow, monospace accents (IDs, SMILES, token counts, metrics), dense-but-airy data layouts, restrained motion. Implemented with the frontend-design skill in the polish pass (Phase 5). |
| 6 | Modernization latitude | User (2026-07-01): "feel free to modernize portions of ui if required" — functional parity is the floor; visual/UX upgrades are allowed where they improve the app (e.g. ⌘K palette, sonner toasts, dropzone). |

### Approaches considered

- **A. Phased strangler (chosen):** shadcn installed alongside PrimeReact; swap feature-by-feature; delete PrimeReact last. Working app at every commit; reviewable phases.
- **B. Big-bang:** rewrite everything then delete. One giant unreviewable diff, long broken window, no benefit — rejected.
- **C. Chat-only AI Elements, keep PrimeReact elsewhere:** smallest effort but fails the explicit "completely replace" requirement — rejected.

## New dependencies (apps/portal)

- Added by `npx shadcn@latest init` / component adds: `class-variance-authority`, `tailwind-merge`, `tw-animate-css`, `@radix-ui/*` (per component), `cmdk`, `sonner`.
- Added by `npx ai-elements@latest`: `streamdown` (streaming-safe markdown), `use-stick-to-bottom`, `ai` (type imports only — **not** used as transport).
- Added manually: `@tanstack/react-table`, `react-dropzone`.
- Removed at Phase 5: `primereact`, `primeicons` (portal deps + `packages/ui` peer/devDeps, which are already unused in source).

## Component mapping (zero-loss)

| PrimeReact (uses) | Replacement |
|---|---|
| `Button` (15) | shadcn `Button` (variants: default/secondary/ghost/destructive/outline) |
| `Skeleton` (9) | shadcn `Skeleton` |
| `SelectButton` (8) | shadcn `ToggleGroup` type="single" with enforced selection (or `Tabs` where it switches panes) |
| `Tag` (7) / `Chip` (2) / `Badge` (1) | shadcn `Badge` (+ severity variant map: success/info/warning/danger) |
| `Message` (6) | shadcn `Alert` (+ destructive/info variants) |
| `InputText` (5) / `IconField`+`InputIcon` | shadcn `Input` (+ icon slot wrapper) |
| `ProgressSpinner` (4) | shadcn `Spinner` (or `Loader2` spin); AI Elements `Loader` in chat |
| `Dropdown` (4) | shadcn `Select` |
| `DataTable`+`Column` (4) | shared `DataTable` wrapper: TanStack Table + shadcn `Table` — sorting, text/select column filters (`FilterMatchMode` parity), pagination |
| `Toast` (3) | `sonner` (`Toaster` mounted once in Providers; `toast.success/error(summary, {description})`) |
| `Dialog` (2) | shadcn `Dialog`; drag/resize parity via small `usePointerDrag` hook + CSS `resize` (see risks) |
| `AutoComplete` (2) | shadcn Combobox pattern (`Command` in `Popover`) with async suggestions, multi-select chips |
| `ConfirmDialog` | shadcn `AlertDialog` |
| `TabView`/`TabPanel` | shadcn `Tabs` |
| `OverlayPanel` | shadcn `Popover`; `SearchCommand` upgraded to `CommandDialog` (cmdk) keeping recent-searches + grouped results |
| `Tooltip` | shadcn `Tooltip` |
| `InputTextarea` (autoResize) | AI Elements `PromptInput` textarea (auto-resizing) in chat; `Textarea` + rows auto logic elsewhere |
| `InputSwitch` | shadcn `Switch` |
| `FileUpload` | `react-dropzone` zone + file list + shadcn `Progress`; existing custom `uploadHandler` logic reused |
| `Breadcrumb` | shadcn `Breadcrumb` |
| `PrimeReactProvider` / `FilterMatchMode` | deleted; filter modes map to TanStack `filterFns` |
| `pi pi-*` icon strings (`LinkButton`, `EntityTypeBadge`) | `LucideIcon` props |

`components/ui/` wrappers keep their public APIs (`LoadingSpinner`, `StatCard`,
`TableThumbnail`, `EntityTypeBadge`, `LinkButton`) — internals swap, call sites mostly untouched.

## Chat: AI Elements integration

Transport unchanged: `use-chat.ts` parses SSE → `chat-store.ts` buffers → components read
the store. AI Elements components are vendored and adapted where their props assume AI SDK types.

| Current component | Becomes |
|---|---|
| `ChatLayout` | kept (custom 3-pane shell) |
| `ChatPanel` | kept orchestration; wraps messages in `Conversation`/`ConversationContent`/`ConversationScrollButton` (stick-to-bottom behavior) |
| `MessageList` / `ChatMessage` | `Message`/`MessageContent`/`MessageAvatar` + `Actions` (copy, thumbs feedback) + kept token-usage/dev-diagnostics blocks; token totals can use AI Elements `Context` |
| `MarkdownRenderer` | AI Elements `Response` (streamdown). **Citation parsing (`[N]` → clickable, `highlightCitation`) is preserved** via streamdown custom components; if streamdown can't support it cleanly, keep react-markdown for assistant text (decided at implementation, parity is the constraint) |
| `ReasoningDisclosure` | `Reasoning`/`ReasoningTrigger`/`ReasoningContent` (auto-open while streaming) |
| `AgentThinkingPanel` + `AgentStepIndicator` | `ChainOfThought` (or `Task`) fed from `streamingSteps`/`ThinkingBlock`s; `QueryPlanCard` kept custom |
| `SourcesPanel` | kept structure (artifact grouping, `AuthThumbnail`, preview dialog) restyled; `Sources`/`InlineCitation` primitives used where they fit |
| `ChatInput` | `PromptInput` + `PromptInputTextarea` + `PromptInputToolbar`/`PromptInputSubmit`; custom `ModeToggle` + `ReasoningToggle` live in the toolbar |
| `DataTableBlock` | shadcn `Table` (compact, striped, scrollable) |
| `MoleculeBlock`, `RichContentRenderer`, `CitationList` | kept custom (domain-specific); restyled |
| `ThinkingDots` | AI Elements `Loader`/`Shimmer` |
| `ReasoningSettings` | `ToggleGroup` swap for its SelectButtons |

## Feature-parity risk register

1. **Draggable/resizable preview Dialog** (`SourcesPanel`, `ShareDialog`): Radix doesn't do this. Small `usePointerDrag` hook (~30 lines) on the dialog header + CSS `resize: both` on content. Parity kept.
2. **DataTable column filters**: per-column contains/equals filtering + paging + sorting re-implemented with TanStack row models in ONE shared wrapper. Verify each of the 4 screens against current behavior.
3. **FileUpload**: drag-drop, file list, remove, progress, custom upload handler — rebuilt with react-dropzone + `Progress`. Verify multi-file behavior matches current page.
4. **AutoComplete async suggestions** (tags; ShareDialog users/groups): combobox with debounced async query, free-text entry for tags, chips for selections.
5. **SearchCommand**: recent searches + grouped results + keyboard nav preserved in `CommandDialog`; visual upgrade intended.
6. **Toast severity + summary/detail** → sonner equivalents.
7. **Ripple effect**: intentionally dropped (dated); only deliberate visual regression.
8. **Doc-detail TabView state**: tab index syncs to the `?tab=` query param (verified in `documents/[id]/page.tsx`); shadcn `Tabs` is controlled via `value`/`onValueChange` — keep the URL sync, switch index→name values.
9. **Theme flash**: anti-flash script stays; shadcn tokens are plain CSS vars so no `<link>` swap latency anymore (net improvement).
10. **`packages/ui`**: no source changes (already PrimeReact-free); just drop stale peer/devDeps and the stale "PrimeReact-based" header comment.

## Phases (app green after each)

- **Phase 0 — Foundation:** `shadcn init` (new-york, CSS variables), token mapping onto `--ds-*` for light/dark under `data-theme`, mount `Toaster` + `TooltipProvider`, `npx ai-elements@latest`, add TanStack Table + react-dropzone. PrimeReact untouched and still rendering.
- **Phase 1 — Primitives:** swap `components/ui/` wrapper internals + all trivial usages (Button/Skeleton/Tag/Message/Spinner) across dashboard, status, stats, settings, error/loading routes, WorkflowList/WorkflowStatusBadge, Topbar.
- **Phase 2 — Forms & overlays:** upload page, ShareDialog, TagFilter/PopularTags, search page mode switch, SearchCommand → CommandDialog, document detail (Tabs, AlertDialog, sonner), page viewer SelectButtons.
- **Phase 3 — Tables:** shared TanStack `DataTable` wrapper; migrate DocumentsTableView, FolderArtifactList, PagesTab (chat's DataTableBlock is simpler — plain Table in Phase 4).
- **Phase 4 — Chat:** AI Elements per mapping above, driven by existing store; citation flash + grounding + dev diagnostics verified against live backend.
- **Phase 5 — Removal & polish:** uninstall primereact/primeicons everywhere, delete `copy-primereact-themes.mjs` + postinstall entry + ThemeProvider `<link>` swap + all `.p-*` CSS (~200 lines in globals.css), then frontend-design polish pass (typography incl. mono accents, density, focus states) and full light/dark walkthrough.

## Testing / verification

- Per phase: `pnpm lint` (tsc --noEmit), `pnpm build`, dev-server walkthrough of touched screens in light + dark.
- End gate: `grep -r "primereact" apps packages --include="*.ts*"` → zero hits; feature-parity checklist (risk register above) walked end-to-end including a live chat stream, citation click-through, molecule rendering, upload, share flow, table filter/sort/page on all 4 tables.
- No new test framework; existing lint/build is the harness. (ponytail: UI migration — behavior verified by walkthrough, not snapshot suites.)
