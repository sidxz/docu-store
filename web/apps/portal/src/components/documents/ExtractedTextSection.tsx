"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import type { TextMention } from "@docu-store/types";
import { Card, CardHeader } from "@/components/ui/Card";

interface ExtractedTextSectionProps {
  textMention: TextMention | null | undefined;
}

export function ExtractedTextSection({
  textMention,
}: ExtractedTextSectionProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-6">
      <Card>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <CardHeader title="Extracted Text" />
          <ChevronDown
            className={`h-4 w-4 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </button>
        {expanded && (
          <div className="mt-3">
            {textMention?.text ? (
              <div className="max-h-96 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
                {textMention.text}
              </div>
            ) : (
              <p className="text-text-muted">No text extracted yet.</p>
            )}
            {textMention?.model_name && (
              <div className="mt-3 border-t border-border-subtle pt-2 text-xs text-text-muted">
                Model: {textMention.model_name}
                {textMention.confidence != null &&
                  ` · Confidence: ${(textMention.confidence * 100).toFixed(0)}%`}
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
