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
      className="z-[var(--z-rail)] hidden h-full w-[56px] shrink-0 flex-col items-center gap-2 border-r border-subtle bg-background-deep/40 py-4 sm:flex"
    >
      <div className="mb-2 grid size-9 place-items-center">
        <NomercyMark className="size-5 text-accent" />
      </div>

      <button
        type="button"
        onClick={onNewConversation}
        title="Nova conversa"
        aria-label="Nova conversa"
        className="group relative grid size-9 place-items-center rounded-lg text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground active:scale-95"
      >
        <Plus size={18} aria-hidden />
      </button>

      <button
        type="button"
        onClick={onToggleSidebar}
        title="Histórico e Busca"
        aria-label={sidebarOpen ? "Fechar histórico" : "Abrir histórico"}
        className="group relative grid size-9 place-items-center rounded-lg text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground active:scale-95"
      >
        <PanelLeft size={18} aria-hidden />
        {sidebarOpen && (
          <span className="absolute -left-3 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-md bg-accent" />
        )}
      </button>

      <div className="mt-auto flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={onOpenSettings}
          title="Configurações"
          aria-label="Configurações"
          className="grid size-9 place-items-center rounded-lg text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground active:scale-95"
        >
          <Settings size={18} aria-hidden />
        </button>
      </div>
    </nav>
  );
}
