# Docu-Store Frontend Plan

> Living document — update as decisions are made or requirements change.
> Backend lives in `services/`. Frontend lives in `web/`.

---

## 1. Goals

- Production-grade document intelligence UI for drug discovery scientists
- Clean, minimal, information-dense interface
- Workspace-aware from day one (multi-tenancy stubs in place)
- Shared component library exportable to DAIKON and other projects
- Future-proof for: Auth (OAuth2/SSO), workspace isolation, RAG chatbots

---

## 2. Technology Stack

### Core

| Concern            | Choice                        | Version   |
|--------------------|-------------------------------|-----------|
| Framework          | Next.js (App Router)          | 16.x (Turbopack default) |
| Language           | TypeScript (strict mode)      | 5.9.x (6.0 is beta — avoid in prod) |
| Package manager    | pnpm (workspaces)             | 10.x      |
| React              | React                         | 19.x      |

> **Note:** Next.js 16 makes all request APIs (`cookies()`, `headers()`, `params`) async-only.
> Turbopack is the default bundler in dev and production. Custom webpack configs work with explicit opt-in.

### UI & Styling

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| Component library  | PrimeReact                    | 10.x, Styled mode, Lara Light Blue theme (v11 is alpha — avoid) |
| CSS utilities      | Tailwind CSS                  | 4.x — CSS-first config (`@theme`), no `tailwind.config.ts` |
| Icons              | PrimeIcons + Lucide React     | PrimeIcons for PrimeReact, Lucide for custom |

> **Critical: PrimeReact + Tailwind CSS layer ordering.**
> Tailwind's preflight will break PrimeReact styled components unless CSS layers are configured correctly.
> In global CSS, import PrimeReact theme with a layer and define ordering:
> ```css
> @layer theme, base, primereact, components, utilities;
> @import 'primereact/resources/themes/lara-light-blue/theme.css' layer(primereact);
> ```
> This ensures Tailwind utilities can override PrimeReact styles without `!important`.

### State & Data

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| Server state       | TanStack Query                | 5.x — caching, polling, mutations          |
| Local/UI state     | Zustand                       | 5.x — minimal boilerplate                  |
| Forms              | React Hook Form + Zod         | 7.x / 3.x — type-safe, low re-renders      |

### API

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| API types          | openapi-typescript            | 7.x — auto-generated from FastAPI schema   |
| API client         | openapi-fetch                 | 0.17.x — typed fetch using generated schema (pre-1.0, pin version) |

### Auth (stubs now, decide library later)

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| Auth               | **TBD: Better Auth or Auth.js v5** | See Auth section below for decision rationale |

> **Auth library decision (deferred):**
> Auth.js (NextAuth) v5 is still in beta. The Auth.js maintainers have joined the **Better Auth** project
> (announced Sept 2025). Better Auth is TypeScript-first, has built-in RBAC, rate limiting, and 2FA.
> For now we stub auth entirely. When we implement auth (Phase 6), we evaluate:
> - **Better Auth** — recommended for greenfield, TS-first, framework-agnostic, built-in RBAC
> - **Auth.js v5** — more Next.js-specific, larger existing community, MongoDB adapter available
> The stub layer we build now is library-agnostic so switching costs are zero.

### Domain-Specific

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| PDF viewer         | react-pdf (PDF.js)            | 10.x — artifact page viewing               |
| Molecular / SMILES | @rdkit/rdkit (WASM)           | Compound mention rendering, lazy-loaded (~10MB WASM) |
| Charts             | Chart.js via PrimeReact       | Built into PrimeReact (no extra dep)       |

### Chat / RAG

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| Streaming chat     | Vercel AI SDK (`ai`)          | 6.x — useChat hook, Agent abstraction, SSE streaming |

### Testing

| Concern            | Choice                        | Notes                                      |
|--------------------|-------------------------------|--------------------------------------------|
| Unit / Component   | Vitest + Testing Library      | 2.x                                        |
| E2E                | Playwright                    | Latest stable                              |

---

## 3. Monorepo Structure

```
docu-store/
├── services/                          # Python backend (existing)
└── web/
    ├── pnpm-workspace.yaml
    ├── package.json                   # Workspace root — shared devDeps, scripts
    ├── .npmrc                         # pnpm config
    ├── plans/                         # This directory — planning docs
    ├── apps/
    │   └── portal/                    # Main Next.js application
    └── packages/
        ├── ui/                        # Shared component library (exportable to DAIKON)
        ├── types/                     # Shared TypeScript domain types
        ├── api-client/                # Generated + configured FastAPI client
        └── tsconfig/                  # Shared TypeScript / ESLint configs
```

### Package responsibilities

#### `packages/tsconfig`
- `base.json` — strict TS config shared across all packages
- `nextjs.json` — Next.js-specific extends
- No runtime code, pure config

#### `packages/types`
- TypeScript interfaces matching backend domain models
- Supplementary to auto-generated API types — for richer client-side domain logic
- Key types: `Artifact`, `ArtifactPage`, `CompoundMention`, `SearchResult`, `WorkflowInfo`, `Workspace`, `User` (stub)
- Exported for use in `portal` and DAIKON

#### `packages/api-client`
- `src/schema.d.ts` — auto-generated by `openapi-typescript` from FastAPI's `/openapi.json`
- `src/client.ts` — configured `openapi-fetch` instance (base URL, auth headers)
- `scripts/generate.ts` — generation script
- `pnpm generate` script hits the running FastAPI server and regenerates types
- Never manually edit `schema.d.ts` — it is always regenerated

#### `packages/ui`
- Reusable, composable components built on PrimeReact
- Examples: `DocumentCard`, `PageViewer`, `MoleculeRenderer`, `SearchResultCard`, `WorkflowStatusBadge`, `ChatWindow`
- These are the components exported to DAIKON
- Has its own Storybook (future) for documentation
- Depends on `packages/types`

#### `apps/portal`
- The full Next.js application
- Depends on all three packages above
- Contains app-specific pages, layouts, hooks
- All routing is workspace-scoped

---

## 4. Routing Architecture

### Structure

```
apps/portal/src/app/
├── layout.tsx                         # Root layout (TanStack Query, PrimeReact, Auth providers)
├── page.tsx                           # Root → redirect to /default or /login
├── (auth)/                            # Auth route group (no workspace prefix)
│   ├── login/
│   │   └── page.tsx                   # Login page — OAuth provider buttons
│   └── error/
│       └── page.tsx                   # Auth error page
└── [workspace]/                       # All app routes are workspace-scoped
    ├── layout.tsx                      # Workspace shell: sidebar + topbar
    ├── page.tsx                        # Workspace dashboard / home
    ├── documents/
    │   ├── page.tsx                    # Artifact list — browse, filter, sort
    │   ├── upload/
    │   │   └── page.tsx               # Upload new artifact (PDF, etc.)
    │   └── [id]/
    │       ├── page.tsx               # Artifact detail + page list
    │       └── pages/
    │           └── [pageId]/
    │               └── page.tsx       # Single page viewer (text, compounds, embeddings)
    ├── search/
    │   └── page.tsx                   # Unified search (semantic + hierarchical)
    ├── compounds/
    │   └── page.tsx                   # Compound mention browser + SMILES viewer
    ├── chat/
    │   └── page.tsx                   # RAG chatbot interface (STUB → real later)
    └── settings/
        └── page.tsx                   # Workspace settings (STUB → real with auth)
```

### Routing principles

- **`[workspace]`** param is always present. Default workspace slug: `default`.
- Root `/` redirects to `/default` (no auth yet) — later will redirect based on session.
- Middleware (`middleware.ts`) is stubbed: logs the workspace param, passes through. Later it enforces auth + workspace membership.
- All navigation is relative to `[workspace]` — no hard-coded workspace names in components.
- The `(auth)` group is intentionally outside `[workspace]` — login must be accessible before workspace context.

---

## 5. Application Layout

```
┌──────────────────────────────────────────────────────┐
│  Topbar: Logo | Workspace selector (stub) | User menu │
├────────────┬─────────────────────────────────────────┤
│            │                                          │
│  Sidebar   │  Main content area                       │
│            │                                          │
│  Documents │                                          │
│  Search    │                                          │
│  Compounds │                                          │
│  Chat      │                                          │
│  ─────     │                                          │
│  Settings  │                                          │
│            │                                          │
└────────────┴─────────────────────────────────────────┘
```

- PrimeReact `Sidebar` / custom layout — not a drawer, persistent left nav
- Topbar has a workspace selector (stub dropdown — only `default` for now)
- User avatar + menu in topbar (stub — shows placeholder, hooks for Auth.js session later)

---

## 6. State Management Patterns

### Server state (TanStack Query)
- All API calls go through TanStack Query — no bare `fetch` in components
- Query keys are centralized in `src/lib/query-keys.ts`
- Stale time / refetch intervals configured per entity type:
  - Artifacts / Pages: stale after 60s
  - Workflow status: refetch every 3s while `in_progress` (polls Temporal)
  - Search results: stale after 30s

### Local state (Zustand)
- Stores for: active workspace, sidebar collapse state, search filters, chat history
- One store per domain concern — no mega-store

### Forms (React Hook Form + Zod)
- Zod schemas in `packages/types/src/schemas/` — shared between frontend validation and API client types
- Upload form, search form, settings form all use RHF

---

## 7. API Client Usage Pattern

```typescript
// packages/api-client/src/client.ts
import createClient from "openapi-fetch"
import type { paths } from "./schema"  // auto-generated

export const apiClient = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL,
})

// Usage in a query hook (apps/portal)
const { data, error } = await apiClient.GET("/artifacts/{id}", {
  params: { path: { id: artifactId } },
})
// `data` is fully typed as ArtifactReadModel
// `error` is typed as the 422/404 shape
```

### Regenerating types

```bash
# From web/ root — requires FastAPI server running
pnpm --filter api-client generate
```

Add to dev workflow: regenerate when backend models change.

---

## 8. Auth Strategy (Stubs Now, Implement in Phase 6)

### What is stubbed now
- `middleware.ts` — passes all requests through, logs `[workspace]` param
- `(auth)/login/page.tsx` — placeholder page, no real providers
- `src/lib/auth.ts` — exports a stub `useSession()` hook returning a mock user/workspace
- User menu in topbar — shows a static avatar placeholder
- Workspace selector — shows only `default`, non-interactive
- **All stubs are library-agnostic** — no Better Auth or Auth.js dependency until Phase 6

### What the auth layer will provide (future — Phase 6)
- **Library**: Better Auth (preferred) or Auth.js v5 — decision deferred
- Providers: Keycloak (enterprise SSO), Microsoft Entra ID, Google, GitHub
- JWT sessions carrying: `userId`, `workspaceIds[]`, `roles`
- Middleware enforces: authenticated, workspace membership
- FastAPI receives the JWT — validates and scopes all queries to workspace

### Multi-tenancy shape (to be designed separately)
- `Workspace` entity: `{ id, slug, name, ownerId, members[] }`
- Entities (`Artifact`, `Page`) gain `workspaceId` + `ownerId` fields
- Access control: `owner`, `editor`, `viewer` roles per workspace
- Private artifacts: `visibility: private | workspace | public`
- URL shape: `/[workspace]/documents` already supports this with no routing changes

---

## 9. RAG / Chatbot Integration (Stub Now, Implement Later)

### Current stub
- `/[workspace]/chat` page exists with a static chat UI shell
- No backend connection

### Full implementation (future)
- FastAPI exposes a streaming SSE endpoint: `POST /[workspace]/chat`
- Vercel AI SDK `useChat` hook connects to it
- Context: user can attach documents/pages to the chat context
- The `ChatWindow` component lives in `packages/ui` — reusable in DAIKON

### Design notes
- Chat history is workspace-scoped (not global)
- Users can pin specific artifacts/pages as RAG context
- Citations from retrieved chunks are shown inline in responses

---

## 10. Domain-Specific Components

### PDF / Artifact Viewer
- `react-pdf` renders artifact pages
- Split-pane layout: PDF on left, extracted text + compounds on right
- Page thumbnails in a scrollable sidebar panel

### SMILES / Molecular Renderer
- `@rdkit/rdkit` (WASM module) renders 2D molecular structures from SMILES strings
- Loaded lazily (WASM is heavy — dynamic import with loading state)
- `MoleculeCard` in `packages/ui`: shows structure + compound name + metadata

### Workflow Status
- `WorkflowStatusBadge` component: polls `GET /artifacts/{id}/workflows` every 3s
- States: `running`, `completed`, `failed`, `pending`
- PrimeReact `Tag` + `ProgressBar` for visual feedback

---

## 11. Implementation Phases

### Phase 0 — Monorepo Foundation
- [ ] `web/` workspace root: `pnpm-workspace.yaml`, root `package.json`, `.npmrc`
- [ ] `packages/tsconfig` — base and nextjs configs
- [ ] `packages/types` — scaffold with core domain types
- [ ] `packages/api-client` — scaffold with generate script (schema empty until backend runs)
- [ ] `packages/ui` — scaffold with package.json, empty component dir

### Phase 1 — Portal Scaffold + Layout
- [ ] `apps/portal` — Next.js 16 app with App Router (Turbopack default)
- [ ] PrimeReact 10.x + Lara Light Blue theme + CSS layer setup
- [ ] Tailwind CSS 4 setup (CSS-first `@theme`, layer ordering with PrimeReact)
- [ ] TanStack Query provider
- [ ] Auth stub — library-agnostic (no real providers, just session context placeholder)
- [ ] Root layout + `[workspace]` layout (sidebar + topbar)
- [ ] Workspace-aware routing — all stubs wired
- [ ] Middleware stub
- [ ] Navigation working end-to-end (all pages render "coming soon" shell)

### Phase 2 — Documents (Artifacts)
- [ ] Generate API client from running FastAPI
- [ ] Artifact list page — TanStack Query, DataTable, filters
- [ ] Upload page — React Hook Form + Zod, file upload to backend
- [ ] Artifact detail page — metadata, workflow status badge, page list
- [ ] Page viewer — react-pdf + extracted text panel
- [ ] Workflow status polling (Temporal proxy endpoints)

### Phase 3 — Search
- [ ] Search page UI — query input, filter panel
- [ ] Semantic search results — `SearchResultCard` in `packages/ui`
- [ ] Hierarchical search results — grouped by artifact/page
- [ ] Result scoring visualization (PrimeReact Chart)

### Phase 4 — Compounds
- [ ] Compound browser — DataTable with SMILES column
- [ ] `MoleculeCard` component with RDKit WASM renderer
- [ ] Filter by artifact, page, compound name

### Phase 5 — Chat / RAG
- [ ] Chat shell UI using Vercel AI SDK `useChat`
- [ ] Connect to FastAPI streaming endpoint
- [ ] Document context attachment
- [ ] Citation rendering

### Phase 6 — Auth + Multi-tenancy (Separate Planning Session)
- [ ] Evaluate and select auth library (Better Auth vs Auth.js v5)
- [ ] OAuth2 providers (Keycloak, Entra ID, Google, GitHub)
- [ ] Middleware enforcement (route protection, workspace membership)
- [ ] Workspace management UI (create, invite, switch)
- [ ] Access control + ownership model (RBAC: owner, editor, viewer)

---

## 12. Developer Workflow

```bash
# From web/ root
pnpm install                          # Install all workspace deps
pnpm dev                              # Start portal dev server
pnpm --filter api-client generate     # Regenerate API types (needs backend running)
pnpm build                            # Build all packages + portal
pnpm test                             # Run all Vitest tests
pnpm e2e                              # Run Playwright E2E tests
```

### Environment variables (apps/portal/.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
# Auth env vars will be added when auth library is selected (Phase 6)
```

---

## 13. Key Conventions

- All pages are in `app/[workspace]/` — no exceptions
- No bare `fetch` in components — always TanStack Query
- No inline styles — Tailwind classes or PrimeReact props only
- All shared reusable components go in `packages/ui` — not in `apps/portal/components`
- `apps/portal/components` is for app-specific, non-shareable components only
- Query keys are never inline strings — always from `src/lib/query-keys.ts`
- Zod schemas are the source of truth for all form validation
- `schema.d.ts` is never manually edited — always regenerated
