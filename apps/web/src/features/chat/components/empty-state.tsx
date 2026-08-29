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
    <div className="mx-auto flex w-full max-w-[640px] flex-col items-center px-6 py-10">
      <NomercyMark className="mb-5 size-8 text-accent/90" />
      <h1 className="text-balance text-center text-[26px] font-medium leading-[1.25] tracking-[-0.02em] text-foreground">
        Como posso ajudar?
      </h1>
      <p className="mt-2.5 max-w-md text-balance text-center text-[15px] leading-relaxed text-foreground-muted">
        Pergunte. Eu pesquiso quando necessário.
      </p>

      <div className="mt-9 flex flex-col items-center gap-2.5 sm:flex-row sm:gap-7">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="rounded-md px-1 py-1 text-[13.5px] text-foreground-muted transition-colors duration-fast hover:text-foreground"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
