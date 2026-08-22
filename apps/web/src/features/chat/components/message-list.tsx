"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";

import type { ChatMessage } from "@/types/api";
import { AssistantMessage } from "./assistant-message";
import { UserMessage } from "./user-message";
import { EmptyState } from "./empty-state";
import { cn } from "@/lib/utils";

export function MessageList({
  messages,
  isSending,
  onRegenerate,
  hasConversation,
  onNewConversation,
  onSuggestion,
}: {
  messages: ChatMessage[];
  isSending: boolean;
  onRegenerate?: () => void;
  hasConversation: boolean;
  onNewConversation: () => void;
  onSuggestion: (text: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [nearBottom, setNearBottom] = useState(true);
  const lastContentLength = useRef(0);

  const handleScroll = useCallback(() => {
    const element = viewportRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    setNearBottom(distance < 96);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const element = viewportRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior });
    setNearBottom(true);
  }, []);

  const currentLength = messages.reduce((total, message) => total + message.content.length, 0);
  const isEmpty = messages.length === 0;

  useEffect(() => {
    if (!nearBottom) return;
    if (currentLength > lastContentLength.current) {
      scrollToBottom("smooth");
    }
    lastContentLength.current = currentLength;
  }, [currentLength, nearBottom, scrollToBottom]);

  useEffect(() => {
    scrollToBottom("auto");
  }, [isEmpty, scrollToBottom]);

  if (!hasConversation || messages.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto">
        <EmptyState onNewConversation={onNewConversation} onSuggestion={onSuggestion} />
      </div>
    );
  }

  return (
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <div
        ref={viewportRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overscroll-contain"
        aria-live="polite"
      >
        <div className="mx-auto flex w-full max-w-[880px] flex-col gap-8 px-4 pb-8 pt-6 sm:px-6">
          {messages.map((message, index) => {
            if (message.role === "user") {
              return <UserMessage key={message.id ?? `user-${index}`} message={message} />;
            }
            const streaming = Boolean(message.isPending) || isSending;
            return (
              <AssistantMessage
                key={message.id ?? `assistant-${index}`}
                message={message}
                isStreaming={streaming && index === messages.length - 1}
                onRegenerate={onRegenerate}
              />
            );
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={() => scrollToBottom("smooth")}
        aria-label="Rolar para o final"
        className={cn(
          "absolute bottom-4 left-1/2 z-10 grid size-9 -translate-x-1/2 place-items-center rounded-full border border-subtle bg-surface-2 text-foreground shadow-lg transition-all duration-base",
          nearBottom ? "pointer-events-none translate-y-2 opacity-0" : "opacity-100",
        )}
      >
        <ArrowDown size={16} aria-hidden />
      </button>
    </div>
  );
}
