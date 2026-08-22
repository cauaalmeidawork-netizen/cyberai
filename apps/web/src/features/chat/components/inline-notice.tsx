"use client";

import { AlertTriangle, X } from "lucide-react";

export function InlineNotice({
  message,
  displayName,
  onDismiss,
}: {
  message: string;
  displayName: string;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="flex shrink-0 items-center gap-2.5 border-b border-warning/20 bg-warning/10 px-4 py-2 text-xs text-foreground"
    >
      <AlertTriangle size={14} aria-hidden className="shrink-0 text-warning" />
      <span className="truncate">{message}</span>
      <span className="hidden truncate text-foreground-faint sm:inline">{displayName}</span>
      <button
        type="button"
        onClick={onDismiss}
        title="Fechar"
        aria-label="Fechar aviso"
        className="ml-auto grid size-6 place-items-center rounded text-foreground-faint transition-colors duration-fast hover:text-foreground"
      >
        <X size={13} aria-hidden />
      </button>
    </div>
  );
}
