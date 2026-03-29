"use client";

import Link from "next/link";
import { MoleculeStructure } from "@docu-store/ui";

interface MoleculeBlockProps {
  smiles: string;
  label?: string;
  pageId?: string;
  artifactId?: string;
  workspace?: string;
}

export function MoleculeBlock({ smiles, label, pageId, artifactId, workspace }: MoleculeBlockProps) {
  const isExactMatch = Boolean(pageId && artifactId);
  const href =
    workspace && artifactId && pageId
      ? `/${workspace}/documents/${artifactId}/pages/${pageId}`
      : undefined;

  return (
    <div
      className={`my-1 p-3 rounded-lg border bg-surface-elevated ${
        isExactMatch
          ? "border-green-500/50 ring-1 ring-green-500/20"
          : "border-border-default"
      }`}
    >
      <MoleculeStructure smiles={smiles} width={220} height={180} />
      {label && (
        <p className="text-xs text-text-muted mt-1 text-center truncate" title={label}>
          {label}
        </p>
      )}
      <p className="text-xs font-mono text-text-muted mt-1 text-center break-all line-clamp-2">
        {smiles}
      </p>
      {href && (
        <Link
          href={href}
          className="block text-xs text-primary mt-1.5 text-center hover:underline"
        >
          View source page
        </Link>
      )}
    </div>
  );
}
