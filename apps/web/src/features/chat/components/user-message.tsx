"use client";

import { FileText } from "lucide-react";

import type { ChatMessage } from "@/types/api";

export function UserMessage({ message }: { message: ChatMessage }) {
  const attachments = message.attachments ?? [];
  const isShort = message.content.length < 80 && !message.content.includes("\n");

  return (
    <div className="flex justify-end">
      <div
        className={`rounded-[16px] rounded-br-sm bg-surface-2 px-4 py-3 ${
          isShort ? "min-w-[4rem] max-w-[70%]" : "max-w-[70%]"
        }`}
      >
        {message.content ? (
          <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground">
            {message.content}
          </p>
        ) : null}
        {attachments.length > 0 ? (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {attachments.map((attachment) => (
              <span
                key={attachment.name}
                className="inline-flex items-center gap-1.5 rounded-md bg-surface-2 px-2 py-1 text-xs text-foreground-muted"
              >
                <FileText size={12} aria-hidden className="text-foreground-faint" />
                {attachment.name}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
