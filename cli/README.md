# docu-store CLI

Command-line client for docu-store. Upload, search, chat, and manage documents — no service keys required.

## Quick Start

```bash
# Install from npm
npm install -g @docu-store/cli

# Or install from source
cd cli && npm install && npm run build && npm link

# Configure
docu config set sentinel-url https://sentinel.example.com
docu config set api-url https://api.example.com

# Login
docu login --provider github

# Upload & explore
docu upload ./papers --recursive
docu status
docu search "kinase inhibitor"
docu chat "What compounds target EGFR?"
docu summary paper.pdf
docu dashboard
```

## Installation

Requires **Node.js 18+**.

```bash
# From npm (recommended)
npm install -g @docu-store/cli

# From source
cd cli
npm install
npm run build
npm link
```

After install, the `docu` command is available globally. To uninstall: `npm uninstall -g @docu-store/cli`.

## Commands

### `docu login`

Authenticate via browser-based OAuth. Opens your browser, you log in with your identity provider, and the CLI captures the token automatically.

```bash
docu login                              # GitHub (default)
docu login --provider google            # Google (requires client ID + secret)
docu login --workspace my-lab           # Pre-select workspace
docu login --token <paste> --workspace my-lab  # Headless fallback (no auto-refresh)
```

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --provider` | Identity provider (`github`, `google`) | `github` |
| `-w, --workspace` | Workspace slug or ID (skips selection prompt) | — |
| `-t, --token` | Paste an authz token directly (for headless/SSH) | — |
| `--sentinel-url` | Override Sentinel URL for this command | — |

**Google login** requires OAuth credentials from your Google Cloud Console:

```bash
docu config set google-client-id YOUR_CLIENT_ID
docu config set google-client-secret YOUR_CLIENT_SECRET
docu login --provider google
```

Use the same credentials as the web app. Google sessions persist indefinitely via refresh tokens.

### `docu upload`

Upload a single file or an entire directory.

```bash
docu upload paper.pdf                   # Single file
docu upload ./papers                    # All PDFs in directory
docu upload ./papers --recursive        # Include subdirectories
docu upload ./papers -r --resume        # Skip already-uploaded files
docu upload ./papers --dry-run          # List files without uploading
docu upload ./data --glob "*.docx"      # Custom file pattern
```

| Flag | Description | Default |
|------|-------------|---------|
| `-r, --recursive` | Scan subdirectories | off |
| `--resume` | Skip files already uploaded (by filename) | off |
| `--dry-run` | List files without uploading | off |
| `--type` | Artifact type | `RESEARCH_ARTICLE` |
| `--visibility` | `workspace` or `private` | `workspace` |
| `--delay` | Seconds between uploads (rate limiting) | `2` |
| `--glob` | File pattern | `*.pdf` |
| `--api-url` | Override API URL | — |

**Output:**
```
Found 47 files in ./papers
  [1/47] OK intro.pdf -> a1b2c3d4 (12 pages, 2.3s)
  [2/47] OK methods.pdf -> e5f6g7h8 (8 pages, 1.8s)
  [3/47] SKIP results.pdf (already uploaded)
  ...
Done. 45 succeeded, 1 failed, 1 skipped.
```

### `docu list`

List documents in the workspace.

```bash
docu list                               # Recent 20 documents
docu ls --limit 50                      # Show more
docu ls --sort name                     # Sort by filename
docu ls --json                          # JSON output for scripting
```

| Flag | Description | Default |
|------|-------------|---------|
| `-l, --limit` | Number of documents | `20` |
| `-s, --sort` | Sort by (`date`, `name`) | `date` |
| `--json` | Output as JSON | off |

### `docu search`

Search documents by text or semantic similarity.

```bash
docu search "EGFR inhibitor"            # Semantic search
docu search "tuberculosis" --limit 10   # More results
docu search "kinase" --type summary     # Summary matches only
docu search "apoptosis" --json          # JSON output
```

| Flag | Description | Default |
|------|-------------|---------|
| `-l, --limit` | Max results | `5` |
| `-t, --type` | Result type (`all`, `summary`) | `all` |
| `--json` | Output as JSON | off |

### `docu status`

Show processing status of documents (workflow pipelines).

```bash
docu status                             # Recent 10 documents
docu status paper.pdf                   # Specific file by name
docu status --id abc-123-def            # Specific file by artifact ID
docu status --limit 20                  # Show more
```

| Flag | Description | Default |
|------|-------------|---------|
| `--id` | Look up by artifact ID | — |
| `-l, --limit` | Number of recent documents | `10` |
| `--json` | Output as JSON | off |

### `docu summary`

Show the AI-generated summary of a document.

```bash
docu summary paper.pdf                  # By filename
docu summary --id abc-123-def           # By artifact ID
docu summary paper.pdf --json           # JSON output
```

### `docu export`

Download the original document file.

```bash
docu export paper.pdf                   # Download to current directory
docu export paper.pdf --out ./downloads # Download to specific directory
docu export --id abc-123-def            # By artifact ID
```

### `docu delete`

Delete a document (with confirmation prompt).

```bash
docu delete paper.pdf                   # Prompts for confirmation
docu rm paper.pdf -f                    # Skip confirmation
docu delete --id abc-123-def            # By artifact ID
```

### `docu chat`

Chat with your documents using RAG (Retrieval-Augmented Generation).

```bash
docu chat "What is the mechanism of action of aspirin?"  # One-shot question
docu chat -i                               # Interactive REPL mode
docu chat -i --mode thinking               # Use thinking pipeline mode
docu chat "kinase inhibitors" --json       # JSON output
```

| Flag | Description | Default |
|------|-------------|---------|
| `-i, --interactive` | Interactive REPL mode | off |
| `--mode` | Pipeline mode (`quick`, `thinking`, `deep_thinking`) | server default |
| `--json` | Output as JSON | off |

**Subcommands:**

```bash
docu chat list                              # List past conversations
docu chat show <conversation-id>            # Show conversation with messages
docu chat delete <conversation-id>          # Delete conversation
```

In interactive mode, type `/quit` or `/exit` to end the session, or press Ctrl+C.

### `docu compounds search`

Search by chemical structure similarity using SMILES strings.

```bash
docu compounds search "CC(=O)Oc1ccccc1C(=O)O"          # Aspirin
docu compounds search "c1ccc2[nH]ccc2c1" --limit 20    # Indole
docu compounds search "CCO" --threshold 0.5             # Ethanol, lower threshold
```

| Flag | Description | Default |
|------|-------------|---------|
| `-l, --limit` | Max results | `10` |
| `--threshold` | Min similarity score (0-1) | `0.7` |
| `--json` | Output as JSON | off |

### `docu dashboard`

Show workspace statistics at a glance.

```bash
docu dashboard
docu dashboard --json
```

### `docu tags`

Browse tags and categories in the document corpus.

```bash
docu tags popular                           # Most popular tags
docu tags popular --limit 20               # Show more
docu tags suggest "kinase"                  # Autocomplete suggestions
docu tags categories                        # Tag categories with counts
```

### `docu reprocess`

Re-trigger document processing workflows (summarization, metadata extraction).

```bash
docu reprocess paper.pdf                    # Trigger all workflows
docu reprocess paper.pdf --summarize        # Summarization only
docu reprocess paper.pdf --metadata         # Metadata extraction only
docu reprocess --id abc-123-def --all       # By artifact ID
```

### `docu admin`

Admin-only statistics (requires admin access).

```bash
docu admin workflows                        # Temporal workflow stats
docu admin pipeline                         # Document pipeline stats
docu admin vectors                          # Vector store stats
docu admin tokens                           # Token usage
docu admin tokens --period month            # Monthly token usage
docu admin tokens --json                    # JSON output
```

### `docu whoami`

Show current login status.

```bash
docu whoami
```

### `docu logout`

Clear stored credentials.

```bash
docu logout
```

### `docu config`

Manage CLI configuration. Settings are stored in `~/.config/docu-store/config.json`.

```bash
docu config show
docu config set sentinel-url https://sentinel.example.com
docu config set api-url https://api.example.com
docu config set google-client-id YOUR_CLIENT_ID
docu config set google-client-secret YOUR_CLIENT_SECRET
```

**Config priority:** CLI flags > environment variables > config file > defaults.

| Setting | Env Variable | Default |
|---------|-------------|---------|
| `sentinel-url` | `DOCU_SENTINEL_URL` | `http://localhost:9003` |
| `api-url` | `DOCU_API_URL` | `http://localhost:8000` |
| `google-client-id` | `DOCU_GOOGLE_CLIENT_ID` | — |
| `google-client-secret` | `DOCU_GOOGLE_CLIENT_SECRET` | — |

## Filename vs Artifact ID

All commands that reference a document default to **filename** lookup. Use `--id` to specify an artifact ID directly:

```bash
docu summary paper.pdf              # by filename (default)
docu summary --id abc-123-def       # by artifact ID
```

## How Authentication Works

The CLI authenticates the same way as the web frontend — no service keys are distributed to end users.

1. `docu login` opens your browser to the identity provider (GitHub or Google)
2. After login, the token is captured via a local callback server (port 18549)
3. The CLI exchanges this for an authorization token via Sentinel
4. Credentials are stored in `~/.config/docu-store/credentials.json` (mode `0600`)
5. Tokens auto-refresh transparently on each API call

**GitHub** — tokens don't expire (only revocable), so you stay logged in indefinitely.

**Google** — uses OAuth authorization code flow with PKCE. A refresh token is stored so sessions persist indefinitely without re-login. The Google client ID and secret are the same ones used by the web app (configured via `docu config set`).

## Admin Setup (one-time)

An admin must add the CLI origin to the existing docu-store service app in Sentinel:

```bash
curl -X PATCH \
  https://sentinel.example.com/admin/service-apps/<APP_ID> \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"allowed_origins": ["http://localhost:15000", "docu-cli://localhost"]}'
```

This is a one-time setup. End users never see or need service keys.
