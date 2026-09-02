"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";
import { Zap, Search, Telescope, Brain } from "lucide-react";
import {
  PromptInput,
  PromptInputButton,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChatStore, isReasoningOn, type ChatMode } from "@/lib/stores/chat-store";
import { SURFACES } from "@/lib/surfaces";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onAbort?: () => void;
  /** Hide the pipeline-mode toggle where the surface pins the mode. Showing it
   *  there would let a click change the mode chosen for Deep Research while
   *  changing nothing about the surface the user is looking at. */
  modeLocked?: boolean;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = SURFACES.research.composerPlaceholder,
  onAbort,
  modeLocked = false,
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
              {!modeLocked && (
                <ModeToggle mode={chatMode} onToggle={toggleMode} disabled={disabled} />
              )}
              {/* Shown in every mode, quick included: reasoning now defaults on
                  there too, and hiding the toggle left no way to turn it off. */}
              <ReasoningToggle
                on={reasoningOn}
                onToggle={() => setSynthesisOverride(reasoningOn ? "off" : "on")}
                disabled={disabled}
              />
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
  style?: string;
}> = {
  quick: {
    icon: Zap,
    label: "Quick",
    tooltip: "Quick — fast, direct answer",
  },
  thinking: {
    icon: Search,
    label: "Research",
    tooltip: "Research — plans, searches, and verifies across your documents",
    style: "text-blue-600 dark:text-blue-400 hover:text-blue-600 dark:hover:text-blue-400 bg-blue-500/10 hover:bg-blue-500/20",
  },
  deep_thinking: {
    icon: Telescope,
    label: "Deep Research",
    tooltip: "Deep Research — iterative agentic retrieval with visual page analysis",
    style: "text-violet-600 dark:text-violet-400 hover:text-violet-600 dark:hover:text-violet-400 bg-violet-500/10 hover:bg-violet-500/20",
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
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <PromptInputButton
          onClick={onToggle}
          disabled={disabled}
          className={on ? "text-amber-600 dark:text-amber-400 hover:text-amber-600 dark:hover:text-amber-400 bg-amber-500/10 hover:bg-amber-500/20" : ""}
          aria-label={`Reasoning ${on ? "on" : "off"}. Click to toggle.`}
        >
          <Brain className="size-3.5" />
          <span>Reasoning</span>
        </PromptInputButton>
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
        <PromptInputButton
          onClick={onToggle}
          disabled={disabled}
          className={config.style}
          aria-label={`Mode: ${config.label}. Click to switch.`}
        >
          <Icon className="size-3.5" />
          <span>{config.label}</span>
        </PromptInputButton>
      </TooltipTrigger>
      <TooltipContent>{config.tooltip}</TooltipContent>
    </Tooltip>
  );
}
