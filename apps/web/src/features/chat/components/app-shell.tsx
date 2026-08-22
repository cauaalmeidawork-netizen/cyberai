"use client";

import { useEffect } from "react";

import { useChat } from "../hooks/use-chat";
import { NavigationRail } from "./navigation-rail";
import { ConversationSidebar } from "./conversation-sidebar";
import { ConversationView } from "./conversation-view";
import { SettingsSheet } from "./settings-sheet";
import { InlineNotice } from "./inline-notice";
import { NomercyMark } from "./mark";
import { cn } from "@/lib/utils";

export function AppShell() {
  const chat = useChat();

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth < 640) {
        chat.closeSidebar();
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [chat]);

  if (chat.authState === "loading") {
    return (
      <div className="flex h-dvh w-full items-center justify-center bg-background">
        <NomercyMark className="size-8 animate-pulse text-accent" />
      </div>
    );
  }

  if (chat.authState === "unauthenticated") {
    return (
      <div className="flex h-dvh w-full items-center justify-center bg-background px-6">
        <div className="w-full max-w-sm">
          <NomercyMark className="mb-8 size-10 text-accent" />
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Nomercy AI</h1>
          <p className="mt-2 text-sm leading-relaxed text-foreground-muted">
            Entre para começar. O navegador recebe apenas um cookie de sessão da
            aplicação.
          </p>
          <button
            type="button"
            onClick={chat.handleLogin}
            className="mt-8 w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition-colors duration-fast hover:bg-accent-hover"
          >
            Entrar
          </button>
        </div>
      </div>
    );
  }

  const authInfo = chat.authInfo;
  const displayName =
    authInfo?.organizations.find((org) => org.org_id === authInfo.active_org_id)?.org_display_name ??
    "Nomercy AI";

  return (
    <div className="relative flex h-dvh w-full overflow-hidden bg-background">
      <div className="ambience" aria-hidden="true" />

      <NavigationRail
        sidebarOpen={chat.sidebarOpen}
        onToggleSidebar={chat.toggleSidebar}
        onNewConversation={() => void chat.newConversation()}
        onOpenSettings={chat.openSettings}
      />

      <ConversationSidebar
        open={chat.sidebarOpen}
        conversations={chat.conversations}
        selectedConversationId={chat.selectedConversationId}
        onSelect={(id) => void chat.selectConversation(id)}
        onNew={() => void chat.newConversation()}
        onRename={(id, title) => void chat.renameConversation(id, title)}
        onDelete={(id) => void chat.deleteConversation(id)}
        onClose={chat.closeSidebar}
      />

      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        {chat.notice ? (
          <InlineNotice
            message={chat.notice}
            displayName={displayName}
            onDismiss={() => chat.setNotice(null)}
          />
        ) : null}
        <ConversationView
          conversations={chat.conversations}
          selectedConversationId={chat.selectedConversationId}
          messages={chat.messages}
          draft={chat.draft}
          isSending={chat.isSending}
          models={chat.models}
          selectedModel={chat.selectedModel}
          attachments={chat.attachments}
          onDraftChange={chat.setDraft}
          onSelectModel={chat.setSelectedModel}
          onSend={() => void chat.send()}
          onStop={chat.stop}
          onRegenerate={() => void chat.regenerate()}
          onNewConversation={() => void chat.newConversation()}
          onAttach={(files) => void chat.attachFiles(files)}
          onRemoveAttachment={chat.removeAttachment}
          onOpenMobileMenu={chat.toggleSidebar}
        />
      </div>

      <SettingsSheet
        open={chat.settingsOpen}
        onClose={chat.closeSettings}
        authInfo={chat.authInfo}
        onLogout={() => void chat.handleLogout()}
      />

      <div
        className={cn(
          "fixed inset-0 z-[calc(var(--z-sidebar)-1)] bg-black/50 backdrop-blur-sm transition-opacity duration-base sm:hidden",
          chat.sidebarOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={chat.closeSidebar}
        aria-hidden="true"
      />
    </div>
  );
}
