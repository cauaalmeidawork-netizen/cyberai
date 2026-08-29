"use client";

import { useState } from "react";
import { MoreHorizontal, Plus, Search, Settings, Trash2, X } from "lucide-react";

import type { Conversation } from "@/types/api";
import { groupConversations } from "../types";
import { NomercyMark } from "./mark";
import { cn } from "@/lib/utils";

export function ConversationSidebar({
  conversations,
  selectedConversationId,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onOpenSettings,
  onClose,
  open,
}: {
  conversations: Conversation[];
  selectedConversationId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
  onClose: () => void;
  open: boolean;
}) {
  const [query, setQuery] = useState("");
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const filtered = query.trim()
    ? conversations.filter((conversation) =>
        conversation.title.toLowerCase().includes(query.trim().toLowerCase()),
      )
    : conversations;
  const groups = groupConversations(filtered);

  const startRename = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
    setMenuFor(null);
  };

  const commitRename = () => {
    if (editingId && editingTitle.trim()) {
      onRename(editingId, editingTitle.trim());
    }
    setEditingId(null);
  };

  return (
    <aside
      aria-label="Histórico de conversas"
      inert={!open}
      className={cn(
        "z-[var(--z-sidebar)] flex h-[100dvh] w-[var(--sidebar-width)] shrink-0 flex-col bg-background-deep/60 backdrop-blur-sm",
        "max-lg:fixed max-lg:left-0 max-lg:top-0 max-lg:shadow-2xl max-lg:transition-transform max-lg:duration-base max-lg:ease-out",
        open ? "max-lg:translate-x-0" : "max-lg:-translate-x-full lg:hidden",
      )}
    >
      {/* Brand header — only visible on mobile where rail is hidden */}
      <div className="flex items-center gap-2.5 px-4 pb-1 pt-4 lg:hidden">
        <NomercyMark className="size-5 text-accent" />
        <span className="text-[13px] font-semibold tracking-tight text-foreground">Nomercy AI</span>
        <button
          type="button"
          onClick={onClose}
          title="Fechar"
          aria-label="Fechar histórico"
          className="ml-auto grid size-8 place-items-center rounded-md text-foreground-faint transition-colors duration-fast hover:text-foreground"
        >
          <X size={15} aria-hidden />
        </button>
      </div>

      {/* New conversation — clear primary action, never disabled-looking */}
      <button
        type="button"
        onClick={onNew}
        className="mx-3 mb-1 mt-3 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium text-foreground transition-colors duration-fast hover:bg-surface-hover"
      >
        <Plus size={15} aria-hidden className="text-foreground-muted" />
        Nova conversa
      </button>

      {/* Search — quiet field; placeholder must never clip */}
      <div className="mx-3 mb-2 mt-1 flex items-center gap-2 rounded-[10px] border border-transparent px-2.5 transition-colors duration-fast focus-within:border-hairline focus-within:bg-surface-1 hover:bg-surface-hover/40">
        <Search size={13} aria-hidden className="shrink-0 text-foreground-faint" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Buscar conversas"
          placeholder="Buscar conversas…"
          className="h-8 min-w-0 flex-1 bg-transparent text-[13px] text-foreground placeholder:text-foreground-faint focus:outline-none"
        />
      </div>

      {/* Conversation list — clean rows, no cards */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {groups.length === 0 ? (
          <p className="px-3 py-5 text-left text-[12.5px] text-foreground-faint">
            {query.trim() ? "Nenhuma conversa encontrada." : "Nenhuma conversa ainda."}
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-2">
              <p className="px-3 pb-1 pt-3 text-[10px] font-medium uppercase tracking-[0.14em] text-foreground-faint/60">
                {group.label}
              </p>
              <ul className="grid gap-px">
                {group.conversations.map((conversation) => {
                  const isSelected = conversation.id === selectedConversationId;
                  if (editingId === conversation.id) {
                    return (
                      <li key={conversation.id}>
                        <input
                          autoFocus
                          value={editingTitle}
                          onChange={(event) => setEditingTitle(event.target.value)}
                          onBlur={commitRename}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") commitRename();
                            if (event.key === "Escape") setEditingId(null);
                          }}
                          className="w-full rounded-md bg-surface-1 px-2.5 py-1.5 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
                        />
                      </li>
                    );
                  }
                  return (
                    <li key={conversation.id} className="group relative">
                      <button
                        type="button"
                        onClick={() => onSelect(conversation.id)}
                        className={cn(
                          "w-full truncate rounded-lg px-2.5 py-1.5 pr-8 text-left text-[13px] transition-colors duration-fast",
                          isSelected
                            ? "bg-surface-hover/70 text-foreground"
                            : "text-foreground-muted hover:bg-surface-hover/40 hover:text-foreground",
                        )}
                      >
                        {conversation.title}
                      </button>
                      <button
                        type="button"
                        title="Mais opções"
                        aria-label={`Mais opções para ${conversation.title}`}
                        onClick={() => setMenuFor(menuFor === conversation.id ? null : conversation.id)}
                        className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1 text-foreground-faint opacity-0 transition-[color,opacity] duration-fast hover:text-foreground focus-visible:pointer-events-auto focus-visible:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100"
                      >
                        <MoreHorizontal size={13} aria-hidden />
                      </button>
                      {menuFor === conversation.id ? (
                        <div className="absolute right-1 top-full z-20 mt-0.5 w-36 overflow-hidden rounded-lg border border-subtle bg-surface-2 p-1 shadow-lg">
                          <button
                            type="button"
                            onClick={() => startRename(conversation)}
                            className="w-full rounded-md px-2.5 py-1.5 text-left text-[13px] text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
                          >
                            Renomear
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              onDelete(conversation.id);
                              setMenuFor(null);
                            }}
                            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] text-danger transition-colors duration-fast hover:bg-surface-hover"
                          >
                            <Trash2 size={13} aria-hidden />
                            Excluir
                          </button>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>

      <div className="border-t border-hairline p-2 lg:hidden">
        <button
          type="button"
          onClick={() => {
            onClose();
            onOpenSettings();
          }}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
        >
          <Settings size={15} aria-hidden />
          Configurações
        </button>
      </div>
    </aside>
  );
}
