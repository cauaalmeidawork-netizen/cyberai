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
    <div className="relative flex w-full justify-center">
      {active ? (
        <span
          aria-hidden
          className="absolute left-0 top-1/2 h-[18px] w-[2px] -translate-y-1/2 rounded-r-full bg-accent"
        />
      ) : null}
      <button
        type="button"
        onClick={onClick}
        title={title}
        aria-label={label}
        className={cn(
          "grid size-9 place-items-center rounded-lg transition-colors duration-fast active:scale-95",
          active
            ? "text-foreground"
            : "text-foreground-muted hover:bg-surface-hover hover:text-foreground",
        )}
      >
        {children}
      </button>
    </div>
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
      className="z-[var(--z-rail)] hidden h-full w-[56px] shrink-0 flex-col items-center gap-1.5 border-r border-hairline bg-background-deep/60 py-3 backdrop-blur-sm lg:flex"
    >
      <div className="mb-1.5 grid size-9 place-items-center">
        <NomercyMark className="size-[18px] text-accent" />
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

      <div className="mt-auto flex w-full flex-col items-center gap-1.5">
        <RailButton label="Configurações" title="Configurações" onClick={onOpenSettings}>
          <Settings size={18} aria-hidden />
        </RailButton>
      </div>
    </nav>
  );
}
