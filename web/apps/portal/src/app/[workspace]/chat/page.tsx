"use client";

import { use } from "react";
import { ChatLayout } from "@/components/chat/ChatLayout";

export default function ChatPage({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = use(params);

  return (
    <div className="-m-6 h-[calc(100%+3rem)]">
      <ChatLayout workspace={workspace} />
    </div>
  );
}
