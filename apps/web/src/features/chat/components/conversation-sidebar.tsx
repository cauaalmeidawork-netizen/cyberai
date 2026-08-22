"use client";

import { useState } from "react";
import { MoreHorizontal, Plus, Search, Trash2, X } from "lucide-react";

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
  onClose,
  open,
}: {
  conversations: Conversation[];
  selectedConversationId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
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
        "z-[var(--z-sidebar)] flex h-[100dvh] w-[var(--sidebar-width)] shrink-0 flex-col bg-background-deep/50 backdrop-blur-sm",
        "max-sm:fixed max-sm:left-0 max-sm:top-0 max-sm:shadow-2xl max-sm:transition-transform max-sm:duration-base max-sm:ease-out",
        open ? "max-sm:translate-x-0" : "max-sm:-translate-x-full sm:hidden",
      )}
    >
      {/* Brand header — only visible on mobile where rail is hidden */}
      <div className="flex items-center gap-2.5 px-4 pb-2 pt-5 sm:hidden">
        <NomercyMark className="size-5 text-accent" />
        <span className="text-[13px] font-semibold tracking-tight text-foreground">Nomercy AI</span>
        <button
          type="button"
          onClick={onClose}
          title="Fechar"
          aria-label="Fechar histórico"
          className="ml-auto grid size-7 place-items-center rounded-md text-foreground-faint transition-colors duration-fast hover:text-foreground"
        >
          <X size={15} aria-hidden />
        </button>
      </div>

      {/* New conversation — simple row, mobile only or minimal */}
      <button
        type="button"
        onClick={onNew}
        className="mx-3 mt-3 mb-2 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground sm:hidden"
      >
        <Plus size={15} aria-hidden className="text-foreground-faint" />
        Nova conversa
      </button>

      {/* Search — transparent, subtle */}
      <div className="mx-3 mt-2 mb-3 flex items-center gap-2 rounded-[10px] bg-surface-hover/30 px-2.5 py-0.5 border border-transparent focus-within:border-subtle focus-within:bg-surface-2 transition-colors">
        <Search size={13} aria-hidden className="shrink-0 text-foreground-faint" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar conversas..."
          className="h-8 w-full bg-transparent text-[13px] text-foreground placeholder:text-foreground-faint focus:outline-none"
        />
      </div>

      {/* Conversation list — no cards, clean rows */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {groups.length === 0 ? (
          <p className="px-3 py-8 text-center text-[12.5px] text-foreground-faint">
            Nenhuma conversa ainda.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-2">
              <p className="px-3 pb-1.5 pt-3 text-[10.5px] font-medium uppercase tracking-widest text-foreground-faint/70">
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
                            ? "bg-surface-hover text-foreground"
                            : "text-foreground-muted hover:bg-surface-hover/50 hover:text-foreground",
                        )}
                      >
                        {conversation.title}
                      </button>
                      <button
                        type="button"
                        title="Mais opções"
                        aria-label="Mais opções"
                        onClick={() => setMenuFor(menuFor === conversation.id ? null : conversation.id)}
                        className="absolute right-1 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-foreground-faint transition-colors duration-fast hover:text-foreground group-hover:block"
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
    </aside>
  );
}
