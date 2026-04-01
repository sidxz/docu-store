# Changelog

## [0.2.0] - 2026-03-31

### Added
- `docu chat` — interactive RAG chat with document corpus (one-shot and REPL mode)
- `docu chat list/show/delete` — manage conversations
- `docu compounds search` — SMILES-based compound similarity search
- `docu dashboard` — workspace statistics overview
- `docu tags popular/suggest/categories` — browse tags and categories
- `docu admin workflows/pipeline/vectors/tokens` — admin-only statistics
- `docu reprocess` — re-trigger summarization and metadata extraction workflows
- NPM publishing setup with `@docu-store/cli` public package

### Changed
- Version is now single-sourced from package.json (injected at build time via tsup)
- Extracted shared `findArtifactByFilename` utility (was duplicated in 4 commands)
- Extracted shared `extractApiError` utility

## [0.1.0] - 2026-03-28

### Added
- Initial release
- `docu login/logout/whoami` — OAuth authentication (GitHub, Google) via Sentinel
- `docu config` — CLI configuration management
- `docu upload` — file and directory upload with resume, dry-run, glob support
- `docu list` — list workspace documents
- `docu search` — hierarchical semantic search
- `docu status` — document processing workflow status
- `docu summary` — AI-generated document summaries
- `docu export` — download original documents
- `docu delete` — delete documents with confirmation
