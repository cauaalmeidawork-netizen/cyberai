"use client";

import { Search } from "lucide-react";

export function ResearchStatus({
  status,
  providers,
}: {
  status: "searching" | "done" | null | undefined;
  providers?: string[];
}) {
  if (status !== "searching") {
    return null;
  }

  const label =
    providers && providers.length > 0
      ? `Consultando ${providers.slice(0, 3).join(", ")}${providers.length > 3 ? "…" : ""}…`
      : "Pesquisando fontes…";

  return (
    <div className="mb-3 flex items-center gap-2 text-xs text-foreground-muted" role="status">
      <Search size={13} aria-hidden className="animate-pulse" />
      <span>{label}</span>
    </div>
  );
}
