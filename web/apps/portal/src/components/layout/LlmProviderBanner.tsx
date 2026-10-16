"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { KeyRound } from "lucide-react";

import { useLlmProvider } from "@/hooks/use-llm-provider";

/** Shown until the workspace has a provider (BYO mode only): admins can connect
 *  one, members can only ask. */
export function LlmProviderBanner() {
  const { workspace } = useParams<{ workspace: string }>();
  const { data } = useLlmProvider();
  if (!data?.enabled || data.configured) return null;
  return (
    <div className="flex items-center gap-3 border-b border-amber-300 bg-amber-50 px-6 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      <KeyRound className="h-4 w-4 shrink-0" />
      {data.can_manage ? (
        <>
          <span>No AI provider connected. Connect one to enable document uploads and chat.</span>
          <Link href={`/${workspace}/settings/llm`} className="ml-auto font-medium underline">
            Connect a provider
          </Link>
        </>
      ) : (
        <span>
          This workspace has no AI provider yet. Ask a workspace admin to connect one to enable
          document uploads and chat.
        </span>
      )}
    </div>
  );
}
