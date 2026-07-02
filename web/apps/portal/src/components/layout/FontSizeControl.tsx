"use client";

import { RotateCcw } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useFontScaleStore,
  FONT_SCALE_MIN,
  FONT_SCALE_MAX,
  FONT_SCALE_STEP,
  FONT_SCALE_DEFAULT,
} from "@/lib/stores/font-scale-store";

/** Global text-size slider — sets the root font-size (percent of browser
 *  default); every rem-based utility scales off it. Sits next to the theme
 *  toggle in the top bar. */
export function FontSizeControl() {
  const scale = useFontScaleStore((s) => s.scale);
  const setScale = useFontScaleStore((s) => s.setScale);
  const reset = useFontScaleStore((s) => s.reset);
  const isDefault = scale === FONT_SCALE_DEFAULT;

  return (
    <div className="hidden items-center gap-1.5 px-1 lg:flex">
      <span aria-hidden className="text-xs font-semibold text-text-muted">A</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center">
            <Slider
              value={[scale]}
              min={FONT_SCALE_MIN}
              max={FONT_SCALE_MAX}
              step={FONT_SCALE_STEP}
              onValueChange={([v]) => setScale(v)}
              onDoubleClick={reset}
              aria-label="Text size"
              className="w-16"
            />
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Text size {scale}%{isDefault ? "" : " · double-click to reset"}
        </TooltipContent>
      </Tooltip>
      <span aria-hidden className="text-base font-semibold text-text-muted">A</span>
      {/* Reset — appears only when off the 100% default */}
      {!isDefault && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={reset}
              aria-label="Reset text size to 100%"
              className="rounded p-0.5 text-text-muted transition-colors hover:text-text-secondary"
            >
              <RotateCcw className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Reset to 100%</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
