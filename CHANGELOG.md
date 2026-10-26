# Changelog

Changes to the API, workers and web portal. The CLI keeps its own log in [cli/CHANGELOG.md](cli/CHANGELOG.md).

## [Unreleased]

### Added
- Per-workspace storage limits. Workspace admins set one in Settings → Storage, and `MAX_WORKSPACE_STORAGE_MB` caps every workspace on the deployment (unset means no cap). The lower of the two applies, to admins as well. An upload that would go over it is refused with HTTP 413 before anything is stored.
- Settings → Storage for workspace admins: uploaded size against the limit, disk use including page images and parsed text, and a limit editor that stops at the deployment cap.
- `GET /workspace/storage` and `PUT /workspace/storage/limit`, for workspace admins. A limit above the deployment cap returns 422.
- Documents record the size of their uploaded file (`source_size_bytes`).

### Changed
- **Breaking:** blob storage is organized by workspace. All of a document's files live under `workspaces/{workspace_id}/artifacts/{artifact_id}/`. Nothing moves existing files, so on an existing install, documents uploaded before this change lose their page images, thumbnails and other derived files until those are moved to the new paths. Start from an empty blob store, or move the files before upgrading.
- Deleting a document deletes all of its stored files.

### Fixed
- A document's original file is stored with its page images and parsed text.
- Deleting a document removes it from document lists.
