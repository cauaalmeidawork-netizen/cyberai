"use client";

import { useState } from "react";
import { Check, Copy, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";

import type { ChatMessage } from "@/types/api";
import { StreamingMarkdown } from "./streaming-markdown";
import { ResearchStatus } from "./research-status";
import { Sources } from "./sources";
import { cn } from "@/lib/utils";

export function AssistantMessage({
  message,
  isStreaming,
  onRegenerate,
}: {
  message: ChatMessage;
  isStreaming: boolean;
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard unavailable
    }
  };

  const pending = Boolean(message.isPending) && !message.content;

  return (
    <div className="group relative">
      <div className="max-w-[840px]">
        <ResearchStatus status={message.researchStatus} providers={message.researchProviders} />
        {pending ? (
          <PendingIndicator />
        ) : (
          <div className="markdown-body">
            <StreamingMarkdown
              content={message.content}
              streaming={isStreaming}
              sources={message.sources ?? []}
            />
          </div>
        )}
        <Sources sources={message.sources ?? []} />
      </div>

      {!pending && !isStreaming ? (
        <div
          className="mt-2.5 flex items-center gap-0.5 opacity-0 transition-opacity duration-fast group-hover:opacity-100 focus-within:opacity-100"
          aria-label="Ações da resposta"
        >
          <MessageAction label="Copiar" onClick={() => void copy()} active={copied}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </MessageAction>
          {onRegenerate ? (
            <MessageAction label="Gerar novamente" onClick={onRegenerate}>
              <RefreshCw size={14} />
            </MessageAction>
          ) : null}
          <MessageAction
            label="Boa resposta"
            onClick={() => setFeedback((current) => (current === "up" ? null : "up"))}
            active={feedback === "up"}
            pressed={feedback === "up"}
          >
            <ThumbsUp size={14} />
          </MessageAction>
          <MessageAction
            label="Resposta ruim"
            onClick={() => setFeedback((current) => (current === "down" ? null : "down"))}
            active={feedback === "down"}
            pressed={feedback === "down"}
          >
            <ThumbsDown size={14} />
          </MessageAction>
        </div>
      ) : null}
    </div>
  );
}

function PendingIndicator() {
  return (
    <div className="flex items-center gap-2 py-2" aria-label="Gerando resposta">
      <span className="text-[14px] italic text-foreground-faint">Pensando</span>
      <div className="flex items-center gap-1">
        <span className="dot animate-bounce [animation-delay:0ms] bg-accent/60" />
        <span className="dot animate-bounce [animation-delay:120ms] bg-accent/60" />
        <span className="dot animate-bounce [animation-delay:240ms] bg-accent/60" />
      </div>
    </div>
  );
}

function MessageAction({
  label,
  onClick,
  active,
  pressed,
  children,
}: {
  label: string;
  onClick?: () => void;
  active?: boolean;
  pressed?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={pressed ?? undefined}
      className={cn(
        "grid size-7 place-items-center rounded-md text-foreground-faint transition-colors duration-fast hover:bg-surface-hover hover:text-foreground",
        active && "text-accent",
      )}
    >
      {children}
    </button>
  );
}
