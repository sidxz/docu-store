import { UserPen } from "lucide-react";

import type { HumanCorrectionInfo } from "@docu-store/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface HumanCorrectedBadgeProps {
  info: HumanCorrectionInfo;
}

/** hiledit: inline marker shown next to a field a human has manually corrected. */
export function HumanCorrectedBadge({ info }: HumanCorrectedBadgeProps) {
  const who = info.corrected_by_name ?? info.corrected_by_id;
  const when = new Date(info.corrected_at).toLocaleDateString();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          aria-label="Human corrected"
          tabIndex={0}
          className="inline-flex items-center rounded-sm text-text-muted outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <UserPen className="size-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        Corrected by {who} · {when}
      </TooltipContent>
    </Tooltip>
  );
}
