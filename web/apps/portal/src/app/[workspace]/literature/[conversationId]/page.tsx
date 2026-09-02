"use client";

import { use } from "react";
import { LiteratureLayout } from "@/components/literature/LiteratureLayout";

export default function LiteratureConversationPage({
  params,
}: {
  params: Promise<{ workspace: string; conversationId: string }>;
}) {
  const { workspace, conversationId } = use(params);

  return (
    <div className="-m-6 h-[calc(100%+3rem)]">
      <LiteratureLayout workspace={workspace} conversationId={conversationId} />
    </div>
  );
}
