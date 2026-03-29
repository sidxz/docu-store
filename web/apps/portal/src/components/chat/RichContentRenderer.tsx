"use client";

import type { ContentBlock } from "@docu-store/types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { DataTableBlock } from "./DataTableBlock";
import { MoleculeBlock } from "./MoleculeBlock";

interface RichContentRendererProps {
  blocks: ContentBlock[];
  workspace: string;
}

type BlockGroup =
  | { type: "molecule-group"; blocks: ContentBlock[] }
  | { type: "single"; blocks: [ContentBlock] };

function groupBlocks(blocks: ContentBlock[]): BlockGroup[] {
  const groups: BlockGroup[] = [];
  let moleculeRun: ContentBlock[] = [];

  const flushMolecules = () => {
    if (moleculeRun.length > 1) {
      groups.push({ type: "molecule-group", blocks: moleculeRun });
    } else if (moleculeRun.length === 1) {
      groups.push({ type: "single", blocks: [moleculeRun[0]] });
    }
    moleculeRun = [];
  };

  for (const block of blocks) {
    if (block.type === "molecule" && block.smiles) {
      moleculeRun.push(block);
    } else {
      flushMolecules();
      groups.push({ type: "single", blocks: [block] });
    }
  }
  flushMolecules();
  return groups;
}

export function RichContentRenderer({ blocks, workspace }: RichContentRendererProps) {
  const groups = groupBlocks(blocks);

  return (
    <div className="space-y-4">
      {groups.map((group, gi) => {
        if (group.type === "molecule-group") {
          return (
            <div
              key={gi}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
            >
              {group.blocks.map((block, bi) => (
                <RenderBlock key={bi} block={block} workspace={workspace} />
              ))}
            </div>
          );
        }
        return (
          <RenderBlock key={gi} block={group.blocks[0]} workspace={workspace} />
        );
      })}
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
        return (
          <MoleculeBlock
            smiles={block.smiles}
            label={block.label ?? undefined}
            pageId={block.page_id ?? undefined}
            artifactId={block.artifact_id ?? undefined}
            workspace={workspace}
          />
        );
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
