"use client";

import { PanelLeft, Plus, Settings } from "lucide-react";

import { NomercyMark } from "./mark";
import { cn } from "@/lib/utils";

function RailButton({
  label,
  title,
  onClick,
  active,
  children,
}: {
  label: string;
  title: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={label}
      className={cn(
        "grid size-9 place-items-center rounded-[10px] transition-colors duration-fast active:scale-95",
        active
          ? "bg-surface-hover text-foreground"
          : "text-foreground-muted hover:bg-surface-hover hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

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
      className="z-[var(--z-rail)] hidden h-full w-[var(--rail-width)] shrink-0 flex-col items-center gap-1 bg-surface-1 py-3.5 lg:flex"
    >
      <div className="mb-2 grid size-9 place-items-center">
        <NomercyMark className="size-[19px] text-foreground-strong" />
      </div>

      <RailButton label="Nova conversa" title="Nova conversa" onClick={onNewConversation}>
        <Plus size={18} aria-hidden />
      </RailButton>

      <RailButton
        label={sidebarOpen ? "Fechar histórico" : "Abrir histórico"}
        title="Histórico e busca"
        onClick={onToggleSidebar}
        active={sidebarOpen}
      >
        <PanelLeft size={18} aria-hidden />
      </RailButton>

      <div className="mt-auto flex w-full flex-col items-center gap-1">
        <RailButton label="Configurações" title="Configurações" onClick={onOpenSettings}>
          <Settings size={18} aria-hidden />
        </RailButton>
      </div>
    </nav>
  );
}
