"use client";

import { MessageSquare } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

export default function ChatPage() {
  return (
    <div>
      <PageHeader
        icon={MessageSquare}
        title="Chat"
        subtitle="Conversational interface for document intelligence"
      />
      <EmptyState
        icon={MessageSquare}
        title="Chat with your documents"
        description="Ask questions about your uploaded documents using RAG-powered conversational AI. This feature is coming soon."
      />
    </div>
  );
}
