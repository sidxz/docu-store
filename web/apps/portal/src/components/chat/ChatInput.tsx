"use client";

import { useState, useRef, useCallback } from "react";
import { Send, Zap, Brain, Eye, Sparkles } from "lucide-react";
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
  const synthesisOverride = useChatStore((s) => s.synthesisOverride);
  const reasoningDefaults = useChatStore((s) => s.reasoningDefaults);
  const setSynthesisOverride = useChatStore((s) => s.setSynthesisOverride);

  const reasoningOn =
    synthesisOverride === "on" ||
    (synthesisOverride === null && reasoningDefaults.synthesis !== "off" && reasoningDefaults.synthesis !== "inherit");

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

  const modes: ChatMode[] = ["quick", "thinking", "deep_thinking"];
  const toggleMode = useCallback(() => {
    const idx = modes.indexOf(chatMode);
    setChatMode(modes[(idx + 1) % modes.length]);
  }, [chatMode, setChatMode]);

  return (
    <div className="border-t border-border-default p-4 bg-surface">
      <div className="flex gap-3 items-end max-w-4xl mx-auto">
        <ModeToggle mode={chatMode} onToggle={toggleMode} disabled={disabled} />
        <ReasoningToggle
          on={reasoningOn}
          onToggle={() => setSynthesisOverride(reasoningOn ? "off" : "on")}
          disabled={disabled}
        />
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

const MODE_CONFIG: Record<ChatMode, {
  icon: typeof Zap;
  label: string;
  tooltip: string;
  style: string;
}> = {
  quick: {
    icon: Zap,
    label: "Quick",
    tooltip: "Quick: fast 4-step pipeline",
    style: "bg-surface-elevated border-border-subtle text-text-muted hover:bg-surface-hover hover:text-text-secondary",
  },
  thinking: {
    icon: Brain,
    label: "Thinking",
    tooltip: "Thinking: deeper analysis, multi-query search, NER filtering",
    style: "bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20",
  },
  deep_thinking: {
    icon: Eye,
    label: "Deep",
    tooltip: "Deep Thinking: visual analysis with page images",
    style: "bg-violet-500/10 border-violet-500/30 text-violet-400 hover:bg-violet-500/20",
  },
};

function ReasoningToggle({
  on,
  onToggle,
  disabled,
}: {
  on: boolean;
  onToggle: () => void;
  disabled: boolean;
}) {
  const style = on
    ? "bg-amber-500/10 border-amber-500/30 text-amber-400 hover:bg-amber-500/20"
    : "bg-surface-elevated border-border-subtle text-text-muted hover:bg-surface-hover hover:text-text-secondary";

  return (
    <>
      <Tooltip target=".chat-reasoning-toggle" position="top" />
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        className={`chat-reasoning-toggle flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
          transition-all flex-shrink-0 border
          ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          ${style}`}
        data-pr-tooltip={on ? "Reasoning: on — inline chain-of-thought" : "Reasoning: off"}
        aria-label={`Reasoning ${on ? "on" : "off"}. Click to toggle.`}
      >
        <Sparkles className="w-3.5 h-3.5" />
        <span>Reasoning</span>
      </button>
    </>
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
  const config = MODE_CONFIG[mode];
  const Icon = config.icon;

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
          ${config.style}`}
        data-pr-tooltip={config.tooltip}
        aria-label={`Mode: ${config.label}. Click to switch.`}
      >
        <Icon className="w-3.5 h-3.5" />
        <span>{config.label}</span>
      </button>
    </>
  );
}
