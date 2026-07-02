"use client";

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

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="hidden items-center gap-1.5 px-1 lg:flex">
          {/* Small A — click to reset to default */}
          <button
            type="button"
            onClick={reset}
            aria-label="Reset text size"
            className="text-xs font-semibold text-text-muted transition-colors hover:text-text-secondary"
          >
            A
          </button>
          <Slider
            value={[scale]}
            min={FONT_SCALE_MIN}
            max={FONT_SCALE_MAX}
            step={FONT_SCALE_STEP}
            onValueChange={([v]) => setScale(v)}
            aria-label="Text size"
            className="w-16"
          />
          {/* Large A */}
          <span aria-hidden className="text-base font-semibold text-text-muted">A</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        Text size: {scale}%{scale !== FONT_SCALE_DEFAULT ? " · click small A to reset" : ""}
      </TooltipContent>
    </Tooltip>
  );
}
