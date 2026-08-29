"use client";

import { Search } from "lucide-react";

export function ResearchStatus({
  status,
}: {
  status: "searching" | "done" | null | undefined;
  providers?: string[];
}) {
  if (status !== "searching") {
    return null;
  }

  const label = "Consultando fontes…";

  return (
    <div className="mb-3 flex items-center gap-2 text-xs text-foreground-muted" role="status">
      <Search size={13} aria-hidden className="animate-pulse" />
      <span>{label}</span>
    </div>
  );
}
