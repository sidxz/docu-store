// Browser shim for Node.js built-in modules (fs, path, etc.)
// Used by Turbopack resolveAlias to satisfy conditional require() calls
// in WASM loaders like @rdkit/rdkit that check for Node.js at runtime.
export default {};
