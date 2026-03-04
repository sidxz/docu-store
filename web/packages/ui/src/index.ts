/**
 * @docu-store/ui — Shared component library.
 *
 * Reusable PrimeReact-based components for docu-store and DAIKON.
 */

export {
  MoleculeStructure,
  StructureInput,
  useRDKit,
} from "./molecule";

export type {
  MoleculeStructureProps,
  StructureInputProps,
} from "./molecule";

// StructureEditor is NOT re-exported here because it depends on Ketcher,
// which requires browser globals (canvas, DOM) and breaks SSR.
// Import it directly with next/dynamic:
//
//   const StructureEditor = dynamic(
//     () => import("@docu-store/ui/src/molecule/StructureEditor").then(m => m.StructureEditor),
//     { ssr: false }
//   );
export type { StructureEditorProps } from "./molecule/StructureEditor";
