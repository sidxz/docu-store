# docu-store frontend — Next.js standalone
#
# Build args (NEXT_PUBLIC_* are baked into client JS at build time):
#   NEXT_PUBLIC_API_URL, NEXT_PUBLIC_APP_URL, NEXT_PUBLIC_SENTINEL_URL,
#   NEXT_PUBLIC_GOOGLE_CLIENT_ID, NEXT_PUBLIC_GITHUB_CLIENT_ID,
#   NEXT_PUBLIC_UMAMI_URL, NEXT_PUBLIC_UMAMI_WEBSITE_ID

# ── Stage 1: Install + Build ──────────────────────────────────
FROM node:22-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Workspace manifests — dependency resolution layer (cached aggressively)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc ./
COPY apps/portal/package.json apps/portal/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/types/package.json packages/types/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/tsconfig/package.json packages/tsconfig/package.json

RUN pnpm install --frozen-lockfile

# Source code (postinstall already copied RDKit WASM + PrimeReact themes)
COPY . .

# Build-time env vars
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_SENTINEL_URL
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ARG NEXT_PUBLIC_GITHUB_CLIENT_ID
ARG NEXT_PUBLIC_UMAMI_URL
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID

RUN pnpm --filter portal build

# ── Stage 2: Runtime ──────────────────────────────────────────
FROM node:22-alpine

RUN adduser -D -u 1000 nextjs

WORKDIR /app

# Copy standalone server + static assets + public dir
COPY --from=builder --chown=nextjs:nextjs /app/apps/portal/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/apps/portal/.next/static ./apps/portal/.next/static
COPY --from=builder --chown=nextjs:nextjs /app/apps/portal/public ./apps/portal/public

USER nextjs

EXPOSE 15000

ENV PORT=15000
ENV HOSTNAME=0.0.0.0

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:15000/api/health || exit 1

CMD ["node", "apps/portal/server.js"]
