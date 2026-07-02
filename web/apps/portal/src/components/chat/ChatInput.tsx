"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";
import { Zap, Search, Telescope, Brain } from "lucide-react";
import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChatStore, isReasoningOn, type ChatMode } from "@/lib/stores/chat-store";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onAbort?: () => void;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Ask a question about your documents...",
  onAbort,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatMode = useChatStore((s) => s.chatMode);
  const setChatMode = useChatStore((s) => s.setChatMode);
  const synthesisOverride = useChatStore((s) => s.synthesisOverride);
  const setSynthesisOverride = useChatStore((s) => s.setSynthesisOverride);

  const reasoningOn = isReasoningOn(chatMode, synthesisOverride);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    // Refocus after send
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [value, disabled, onSend]);

  // PromptInput's onSubmit hands back { text, files } (AI SDK message shape) plus the
  // originating form event. This composer has no attachments, so we ignore `message`
  // and keep using our own controlled `value` state as the source of truth — same
  // trim/disabled/clear/refocus semantics as before.
  const handleSubmit = useCallback(
    (_message: PromptInputMessage, event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      handleSend();
    },
    [handleSend],
  );

  const modes: ChatMode[] = ["quick", "thinking", "deep_thinking"];
  const toggleMode = useCallback(() => {
    const idx = modes.indexOf(chatMode);
    setChatMode(modes[(idx + 1) % modes.length]);
  }, [chatMode, setChatMode]);

  return (
    <div className="border-t border-border-default p-4 bg-surface">
      <div className="max-w-4xl mx-auto">
        <PromptInput onSubmit={handleSubmit}>
          <PromptInputTextarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.currentTarget.value)}
            placeholder={placeholder}
            disabled={disabled}
          />
          <PromptInputFooter>
            <PromptInputTools>
              <ModeToggle mode={chatMode} onToggle={toggleMode} disabled={disabled} />
              {chatMode !== "quick" && (
                <ReasoningToggle
                  on={reasoningOn}
                  onToggle={() => setSynthesisOverride(reasoningOn ? "off" : "on")}
                  disabled={disabled}
                />
              )}
            </PromptInputTools>
            {disabled ? (
              <PromptInputSubmit
                type="button"
                status="streaming"
                onClick={onAbort}
                aria-label="Stop generating"
              />
            ) : (
              <PromptInputSubmit disabled={!value.trim()} />
            )}
          </PromptInputFooter>
        </PromptInput>
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
    tooltip: "Quick — fast, direct answer",
    style: "bg-surface-elevated border-border-subtle text-text-muted hover:bg-surface-hover hover:text-text-secondary",
  },
  thinking: {
    icon: Search,
    label: "Research",
    tooltip: "Research — plans, searches, and verifies across your documents",
    style: "bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20",
  },
  deep_thinking: {
    icon: Telescope,
    label: "Deep Research",
    tooltip: "Deep Research — iterative agentic retrieval with visual page analysis",
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
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
            transition-all flex-shrink-0 border
            ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            ${style}`}
          aria-label={`Reasoning ${on ? "on" : "off"}. Click to toggle.`}
        >
          <Brain className="w-3.5 h-3.5" />
          <span>Reasoning</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>
        {on ? "Reasoning on — model thinks step by step (slower)" : "Reasoning off — model answers directly"}
      </TooltipContent>
    </Tooltip>
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
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
            transition-all flex-shrink-0 border
            ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            ${config.style}`}
          aria-label={`Mode: ${config.label}. Click to switch.`}
        >
          <Icon className="w-3.5 h-3.5" />
          <span>{config.label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{config.tooltip}</TooltipContent>
    </Tooltip>
  );
}
