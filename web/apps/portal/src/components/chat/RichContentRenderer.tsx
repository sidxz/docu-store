"use client";

import type { ContentBlock } from "@docu-store/types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { DataTableBlock } from "./DataTableBlock";
import { MoleculeBlock } from "./MoleculeBlock";

interface RichContentRendererProps {
  blocks: ContentBlock[];
  workspace: string;
}

export function RichContentRenderer({ blocks, workspace }: RichContentRendererProps) {
  return (
    <div className="space-y-4">
      {blocks.map((block, i) => (
        <RenderBlock key={i} block={block} workspace={workspace} />
      ))}
    </div>
  );
}

function RenderBlock({ block, workspace }: { block: ContentBlock; workspace: string }) {
  switch (block.type) {
    case "text":
      return <MarkdownRenderer content={block.content ?? ""} />;

    case "table":
      if (block.headers && block.rows) {
        return <DataTableBlock headers={block.headers} rows={block.rows} />;
      }
      return null;

    case "molecule":
      if (block.smiles) {
        return <MoleculeBlock smiles={block.smiles} label={block.label ?? undefined} />;
      }
      return null;

    case "citation_list":
    case "source_card":
      // These are handled by CitationList in ChatMessage
      return null;

    default:
      return null;
  }
}
