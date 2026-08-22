"use client";

import { PanelLeft, Plus, Settings } from "lucide-react";

import { NomercyMark } from "./mark";

export function NavigationRail({
  sidebarOpen,
  onToggleSidebar,
  onNewConversation,
  onOpenSettings,
}: {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onNewConversation: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <nav
      aria-label="Navegação principal"
      className="z-[var(--z-rail)] hidden h-full w-[var(--rail-width)] shrink-0 flex-col items-center gap-1 bg-background-deep/40 py-3 sm:flex"
    >
      <button
        type="button"
        onClick={onNewConversation}
        title="Nova conversa"
        aria-label="Nova conversa"
        className="mb-1 grid size-9 place-items-center rounded-lg text-foreground-faint transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
      >
        <Plus size={18} aria-hidden />
      </button>

      <button
        type="button"
        onClick={onToggleSidebar}
        title="Histórico"
        aria-label={sidebarOpen ? "Fechar histórico" : "Abrir histórico"}
        className="grid size-9 place-items-center rounded-lg text-foreground-faint transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
      >
        <PanelLeft size={18} aria-hidden />
      </button>

      <div className="mt-auto flex flex-col items-center gap-1">
        <button
          type="button"
          onClick={onOpenSettings}
          title="Configurações"
          aria-label="Configurações"
          className="grid size-9 place-items-center rounded-lg text-foreground-faint transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
        >
          <Settings size={18} aria-hidden />
        </button>
        <div className="mt-2 grid size-8 place-items-center">
          <NomercyMark className="size-4.5 text-accent/70" />
        </div>
      </div>
    </nav>
  );
}
