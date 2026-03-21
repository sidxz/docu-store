"use client";

import { useState, useRef, useCallback } from "react";
import { Send, Zap, Brain } from "lucide-react";
import { InputTextarea } from "primereact/inputtextarea";
import { Button } from "primereact/button";
import { Tooltip } from "primereact/tooltip";
import { useChatStore, type ChatMode } from "@/lib/stores/chat-store";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Ask a question about your documents...",
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatMode = useChatStore((s) => s.chatMode);
  const setChatMode = useChatStore((s) => s.setChatMode);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    // Refocus after send
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [value, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleMode = useCallback(() => {
    setChatMode(chatMode === "thinking" ? "quick" : "thinking");
  }, [chatMode, setChatMode]);

  return (
    <div className="border-t border-border-default p-4 bg-surface">
      <div className="flex gap-3 items-end max-w-4xl mx-auto">
        <ModeToggle mode={chatMode} onToggle={toggleMode} disabled={disabled} />
        <InputTextarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoResize
          rows={1}
          className="flex-1 !max-h-40"
        />
        <Button
          icon={<Send className="w-4 h-4" />}
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="p-button-rounded flex-shrink-0"
          aria-label="Send message"
        />
      </div>
      <p className="text-xs text-text-muted text-center mt-2">
        Docu Store AI can make mistakes. Always verify the information it provides with the original documents.
      </p>
    </div>
  );
}

function ModeToggle({
  mode,
  onToggle,
  disabled,
}: {
  mode: ChatMode;
  onToggle: () => void;
  disabled: boolean;
}) {
  const isThinking = mode === "thinking";

  return (
    <>
      <Tooltip target=".chat-mode-toggle" position="top" />
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        className={`chat-mode-toggle flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
          transition-all flex-shrink-0 border
          ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          ${
            isThinking
              ? "bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20"
              : "bg-surface-elevated border-border-subtle text-text-muted hover:bg-surface-hover hover:text-text-secondary"
          }`}
        data-pr-tooltip={
          isThinking
            ? "Thinking: deeper analysis, multi-query search, NER filtering"
            : "Quick: fast 4-step pipeline"
        }
        aria-label={`Mode: ${isThinking ? "Thinking" : "Quick"}. Click to switch.`}
      >
        {isThinking ? (
          <Brain className="w-3.5 h-3.5" />
        ) : (
          <Zap className="w-3.5 h-3.5" />
        )}
        <span>{isThinking ? "Thinking" : "Quick"}</span>
      </button>
    </>
  );
}
