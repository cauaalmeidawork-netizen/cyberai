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
      <p className="mt-3 max-w-md text-balance text-center text-[14px] leading-relaxed text-foreground-muted">
        Pesquisa profunda, precisão técnica e respostas com fontes. Especialidade
        em cybersecurity.
      </p>

      <div className="mt-9 flex max-w-xl flex-wrap items-center justify-center gap-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestion(suggestion)}
            className="rounded-full border border-subtle px-3.5 py-1.5 text-[13px] text-foreground-muted transition-all duration-fast hover:border-foreground-faint hover:text-foreground"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
