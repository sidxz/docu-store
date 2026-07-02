"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SIZES = { sm: "size-4", md: "size-6", lg: "size-8" } as const;

interface LoadingSpinnerProps {
  size?: keyof typeof SIZES;
  className?: string;
}

export function LoadingSpinner({ size = "md", className }: LoadingSpinnerProps) {
  return (
    <div className={className ?? "flex items-center justify-center py-20"}>
      <Loader2
        className={cn("animate-spin text-text-muted", SIZES[size], className)}
        aria-label="Loading"
      />
    </div>
  );
}
