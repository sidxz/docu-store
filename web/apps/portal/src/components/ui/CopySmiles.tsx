"use client";

import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";

interface CopySmilesProps {
  smiles: string;
  maxWidth?: string;
}

export function CopySmiles({ smiles, maxWidth = "max-w-[180px]" }: CopySmilesProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(smiles);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [smiles]);

  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted">SMILES</span>
      <span className="flex items-center gap-1">
        <span className={`font-mono text-text-secondary ${maxWidth} truncate`}>
          {smiles}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="shrink-0 text-text-muted/40 transition-colors hover:text-text-secondary"
          title="Copy SMILES"
        >
          {copied ? (
            <Check className="h-3 w-3 text-ds-success/60" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </button>
      </span>
    </div>
  );
}
