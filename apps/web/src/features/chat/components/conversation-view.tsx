"use client";

import { Menu } from "lucide-react";

import type { ChatMessage, Conversation, ModelInfo } from "@/types/api";
import type { Attachment } from "../types";
import { MessageList } from "./message-list";
import { Composer } from "./composer";
import { ModelPicker } from "./model-picker";

export function ConversationView({
  conversations,
  selectedConversationId,
  messages,
  draft,
  isSending,
  models,
  selectedModel,
  attachments,
  onDraftChange,
  onSelectModel,
  onSend,
  onStop,
  onRegenerate,
  onNewConversation,
  onAttach,
  onRemoveAttachment,
  onOpenMobileMenu,
}: {
  conversations: Conversation[];
  selectedConversationId: string | null;
  messages: ChatMessage[];
  draft: string;
  isSending: boolean;
  models: ModelInfo[];
  selectedModel: string;
  attachments: Attachment[];
  onDraftChange: (value: string) => void;
  onSelectModel: (key: string) => void;
  onSend: () => void;
  onStop: () => void;
  onRegenerate: () => void;
  onNewConversation: () => void;
  onAttach: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
  onOpenMobileMenu: () => void;
}) {
  const selected = conversations.find(
    (conversation) => conversation.id === selectedConversationId,
  );

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {/* Minimal header — near-invisible, only mobile menu */}
      <header className="flex h-11 shrink-0 items-center gap-2 px-4">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          title="Menu"
          aria-label="Abrir menu"
          className="grid size-8 place-items-center rounded-lg text-foreground-faint transition-colors duration-fast hover:text-foreground sm:hidden"
        >
          <Menu size={17} aria-hidden />
        </button>

        {selected ? (
          <span className="truncate text-[13px] text-foreground-faint">{selected.title}</span>
        ) : null}
      </header>

      {/* Message scroller + Composer */}
      <div className="flex min-h-0 flex-1 flex-col">
        <MessageList
          messages={messages}
          isSending={isSending}
          hasConversation={Boolean(selectedConversationId)}
          onNewConversation={onNewConversation}
          onSuggestion={onDraftChange}
          onRegenerate={onRegenerate}
        />
        <Composer
          draft={draft}
          onChange={onDraftChange}
          onSend={onSend}
          isSending={isSending}
          onStop={onStop}
          models={models}
          selectedModel={selectedModel}
          onSelectModel={onSelectModel}
          attachments={attachments}
          onAttach={onAttach}
          onRemoveAttachment={onRemoveAttachment}
        />
      </div>
    </main>
  );
}
