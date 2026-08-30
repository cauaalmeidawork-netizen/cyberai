"use client";

import { NomercyMark } from "./mark";

const SUGGESTIONS = [
  "Analise este CVE",
  "Explique este log",
  "Compare estas abordagens",
];

export function EmptyState({
  onNewConversation,
  onSuggestion,
}: {
  onNewConversation: () => void;
  onSuggestion: (text: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-[560px] flex-col items-center px-5 py-6">
      <div className="grid size-11 place-items-center rounded-[14px] bg-surface-1">
        <NomercyMark className="size-[22px] text-foreground-strong" />
      </div>
      <h1 className="mt-5 text-balance text-center text-[25px] font-medium leading-[1.2] tracking-[-0.02em] text-foreground-strong">
        Como posso ajudar?
      </h1>
      <p className="mt-2 max-w-sm text-balance text-center text-[14px] leading-relaxed text-foreground-muted">
        Pergunte. Eu pesquiso quando necessário.
      </p>

      <div className="mt-8 flex max-w-full flex-wrap items-center justify-center gap-x-1.5 gap-y-1">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="rounded-full px-3 py-1.5 text-[13px] text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
