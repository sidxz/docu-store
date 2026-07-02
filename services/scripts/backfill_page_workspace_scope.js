// Backfill workspace_id/owner_id onto legacy page_read_models from their parent
// artifact. These pages predate workspace_id propagation to pages (ingestion fix
// 88161ba), so they are null and — since 9d84429 scoped by-id reads at the query —
// now 404 for their own workspace. The parent artifact already carries the correct
// scope, so we copy it down.
//
// Idempotent: only touches pages where workspace_id is null AND whose parent
// artifact has a non-null workspace_id. Re-running is a no-op.
//
// ponytail: read-model backfill only. The PageCreated event still has null; a full
// re-projection from EventStoreDB would reintroduce it. Upgrade path if that ever
// matters: fix at ingestion/event level (or the deferred Docling re-parse covers it).
//
// Usage:
//   mongosh "mongodb://localhost:27017/docu_store" scripts/backfill_page_workspace_scope.js
//   DRY_RUN=1 mongosh ... scripts/backfill_page_workspace_scope.js   // report only

const DRY_RUN = (typeof process !== "undefined" && process.env.DRY_RUN === "1");

const artScope = {}; // artifact_id -> {workspace_id, owner_id}
db.artifact_read_models
  .find({ workspace_id: { $ne: null } }, { artifact_id: 1, workspace_id: 1, owner_id: 1, _id: 0 })
  .forEach((a) => { artScope[a.artifact_id] = { workspace_id: a.workspace_id, owner_id: a.owner_id }; });

let updated = 0, skippedNoParent = 0;
db.page_read_models.find({ workspace_id: null }).forEach((p) => {
  const scope = artScope[p.artifact_id];
  if (!scope) { skippedNoParent++; return; }
  if (DRY_RUN) { updated++; return; }
  db.page_read_models.updateOne(
    { page_id: p.page_id },
    { $set: { workspace_id: scope.workspace_id, owner_id: scope.owner_id } },
  );
  updated++;
});

print((DRY_RUN ? "[DRY RUN] would update " : "updated ") + updated + " page(s)");
print("skipped (parent artifact missing/unscoped): " + skippedNoParent);
