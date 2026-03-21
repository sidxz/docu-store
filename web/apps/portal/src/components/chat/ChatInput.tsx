"use client";

import { useState, useRef, useCallback } from "react";
import { Send } from "lucide-react";
import { InputTextarea } from "primereact/inputtextarea";
import { Button } from "primereact/button";

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

  return (
    <div className="border-t border-surface-200 dark:border-surface-700 p-4 bg-surface-0 dark:bg-surface-900">
      <div className="flex gap-3 items-end max-w-4xl mx-auto">
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
      <p className="text-xs text-surface-400 text-center mt-2">
        Answers are grounded in your uploaded documents. Press Enter to send, Shift+Enter for new line.
      </p>
    </div>
  );
}
