"use client";

import { NomercyMark } from "./mark";

const SUGGESTIONS = [
  "Analise este CVE",
  "Explique este log",
  "Compare estas abordagens",
  "Pesquise esta vulnerabilidade",
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
      <NomercyMark className="mb-8 size-10 text-accent/80" />
      <h1 className="text-balance text-center text-2xl font-semibold tracking-tight text-foreground sm:text-[28px]">
        Como posso ajudar?
      </h1>
      <p className="mt-3 max-w-md text-balance text-center text-[15px] leading-relaxed text-foreground-muted">
        Pergunte. Eu pesquiso quando necessário.
      </p>

      <div className="mt-10 flex max-w-lg flex-wrap items-center justify-center gap-x-4 gap-y-3">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="group flex items-center gap-2 rounded-md px-2 py-1 text-[13.5px] text-foreground-muted transition-colors duration-fast hover:text-foreground"
          >
            {suggestion}
            <span className="font-mono text-[10px] text-foreground-faint transition-transform duration-fast group-hover:translate-x-0.5 group-hover:text-accent">
              →
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
