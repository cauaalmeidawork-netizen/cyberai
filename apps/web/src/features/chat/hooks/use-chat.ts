"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, createApiClient } from "@/lib/api/client";
import { streamConversationMessage } from "@/lib/api/stream";
import { API_BASE_URL } from "@/lib/config";
import { buildHistoryMessages } from "../lib/message-parts";
import { attachmentBlock, attachmentError, readAttachment } from "../lib/attachments";
import type { Attachment } from "../types";
import type {
  AuthMe,
  ChatMessage,
  Conversation,
  ModelInfo,
  ModelListResponse,
  SourceCitation,
} from "@/types/api";

type AuthState = "loading" | "authenticated" | "unauthenticated";

interface ProjectRef {
  id: string;
}

function createIdempotencyKey(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function messageForApiError(error: ApiError): string {
  if (error.status === 400 || error.status === 422) {
    return "A solicitação não é válida. Revise e tente novamente.";
  }
  if (error.status === 401) {
    return "Sua sessão expirou. Entre novamente.";
  }
  if (error.status === 403) {
    return "Seu acesso atual não permite esta ação.";
  }
  if (error.status === 404) {
    return "O recurso não foi encontrado. Atualize a página.";
  }
  if (error.status === 409) {
    return "Esta ação conflita com o estado atual.";
  }
  if (error.status === 413) {
    return "A solicitação é grande demais.";
  }
  if (error.status === 429) {
    return "Muitas solicitações. Tente novamente em instantes.";
  }
  if (error.status === 503 || error.status === 504) {
    return "O provedor do modelo ou um serviço está indisponível.";
  }
  return "Não foi possível concluir. Tente novamente.";
}

export function useChat() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [authInfo, setAuthInfo] = useState<AuthMe | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(
    () => typeof window === "undefined" || window.innerWidth >= 1024,
  );

  const projectIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const clearTenantState = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setConversations([]);
    setModels([]);
    setSelectedModel("");
    setSelectedConversationId(null);
    setMessages([]);
    setDraft("");
    setIsSending(false);
    setNotice(null);
    setAttachments([]);
    setSettingsOpen(false);
    projectIdRef.current = null;
  }, []);

  const invalidateSession = useCallback(() => {
    setAuthInfo(null);
    setAuthState("unauthenticated");
    clearTenantState();
    setNotice("Sua sessão expirou. Entre novamente.");
  }, [clearTenantState]);

  const makeClient = useCallback(
    () => createApiClient({ baseUrl: API_BASE_URL, onUnauthorized: invalidateSession }),
    [invalidateSession],
  );

  const handleApiError = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      setNotice(messageForApiError(error));
      return;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    setNotice("Não foi possível conectar ao serviço.");
  }, []);

  useEffect(() => {
    let cancelled = false;
    const client = makeClient();
    void client
      .get<AuthMe>("/api/v1/auth/me")
      .then((me) => {
        if (cancelled) return;
        setAuthInfo(me);
        setAuthState("authenticated");
        setNotice(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setAuthState("unauthenticated");
        handleApiError(error);
      });
    return () => {
      cancelled = true;
    };
  }, [handleApiError, makeClient]);

  const loadMessages = useCallback(
    async (conversationId: string) => {
      const projectId = projectIdRef.current;
      if (!projectId) return;
      const client = makeClient();
      const history = await client.get<{ messages: ChatMessage[] }>(
        `/api/v1/projects/${projectId}/conversations/${conversationId}/messages?limit=100&offset=0`,
      );
      setMessages(history.messages);
    },
    [makeClient],
  );

  const loadWorkspace = useCallback(async () => {
    if (authState !== "authenticated") return;
    try {
      const client = makeClient();
      const projects = await client.get<ProjectRef[]>("/api/v1/projects");
      const projectId = projects[0]?.id ?? null;
      projectIdRef.current = projectId;
      if (!projectId) {
        setModels([]);
        setConversations([]);
        setMessages([]);
        return;
      }
      const [modelsResponse, conversationList] = await Promise.all([
        client.get<ModelListResponse>("/api/v1/models"),
        client.get<Conversation[]>(`/api/v1/projects/${projectId}/conversations`),
      ]);
      setModels(modelsResponse.data);
      setSelectedModel((current) =>
        current && modelsResponse.data.some((model) => model.key === current)
          ? current
          : modelsResponse.default_model,
      );
      setConversations(conversationList);
      // Start in empty state — user picks a conversation from the sidebar,
      // or creates a new one.  This prevents stale / test-polluted messages
      // from appearing on boot.
      setSelectedConversationId(null);
      setMessages([]);
    } catch (error) {
      handleApiError(error);
    }
  }, [authState, handleApiError, makeClient]);

  useEffect(() => {
    if (authState !== "authenticated") return;
    const id = window.setTimeout(() => void loadWorkspace(), 0);
    return () => window.clearTimeout(id);
  }, [authState, loadWorkspace]);

  const handleLogin = useCallback(() => {
    const loginUrl = new URL("/api/v1/auth/login", API_BASE_URL || window.location.origin);
    loginUrl.searchParams.set("return_to", "/");
    window.location.assign(loginUrl.toString());
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      const client = makeClient();
      await client.post<void>("/api/v1/auth/logout", {});
    } catch {
      // ignore; clear local state regardless
    } finally {
      setAuthInfo(null);
      setAuthState("unauthenticated");
      clearTenantState();
      setNotice(null);
    }
  }, [clearTenantState, makeClient]);

  const selectConversation = useCallback(
    async (conversationId: string) => {
      setSelectedConversationId(conversationId);
      try {
        await loadMessages(conversationId);
      } catch (error) {
        handleApiError(error);
      }
    },
    [handleApiError, loadMessages],
  );

  const createConversation = useCallback(
    async (title: string): Promise<string | null> => {
      const projectId = projectIdRef.current;
      if (!projectId) return null;
      try {
        const client = makeClient();
        const conversation = await client.post<Conversation>(
          `/api/v1/projects/${projectId}/conversations`,
          { title },
        );
        setConversations((current) => [conversation, ...current]);
        setSelectedConversationId(conversation.id);
        setMessages([]);
        return conversation.id;
      } catch (error) {
        handleApiError(error);
        return null;
      }
    },
    [handleApiError, makeClient],
  );

  const newConversation = useCallback(async () => {
    await createConversation("Nova conversa");
  }, [createConversation]);

  const runCompletion = useCallback(
    async (options: {
      conversationId: string;
      projectId: string;
      payloadMessages: ChatMessage[];
      assistantId: string;
      idempotencyKey: string;
    }) => {
      const controller = new AbortController();
      abortRef.current = controller;

      let assistantContent = "";
      let sources: SourceCitation[] = [];
      let researchStatus: ChatMessage["researchStatus"] = null;

      const updateAssistant = (patch: Partial<ChatMessage>) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === options.assistantId ? { ...message, ...patch } : message,
          ),
        );
      };

      try {
        for await (const event of streamConversationMessage({
          baseUrl: API_BASE_URL,
          projectId: options.projectId,
          conversationId: options.conversationId,
          idempotencyKey: options.idempotencyKey,
          signal: controller.signal,
          payload: {
            messages: options.payloadMessages,
            model: selectedModel || null,
            max_tokens: 1024,
            temperature: 0.2,
            rag_enabled: false,
          },
        })) {
          if (event.event === "delta") {
            assistantContent += event.text;
            updateAssistant({ content: assistantContent, isPending: false });
          } else if (event.event === "research_started") {
            researchStatus = "searching";
            updateAssistant({
              researchStatus: "searching",
              researchProviders: event.providers ?? [],
            });
          } else if (event.event === "source") {
            sources.push({
              citation_index: event.citation_index,
              url: event.url,
              title: event.title,
              domain: event.domain,
              source_type: event.source_type,
              published_at: event.published_at,
            });
            updateAssistant({ sources: [...sources] });
          } else if (event.event === "research_completed") {
            researchStatus = "done";
            updateAssistant({ researchStatus: "done", sources: [...sources] });
          } else if (event.event === "completed") {
            updateAssistant({ isPending: false, content: assistantContent, sources });
          }
        }
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === "AbortError";
        updateAssistant({ isPending: false, researchStatus: null });
        if (!aborted) {
          handleApiError(error);
        }
      } finally {
        abortRef.current = null;
        setIsSending(false);
      }
    },
    [handleApiError, selectedModel],
  );

  const send = useCallback(async () => {
    const projectId = projectIdRef.current;
    const content = draft.trim();
    if (!projectId || (!content && attachments.length === 0) || isSending) return;

    let conversationId = selectedConversationId;
    if (!conversationId) {
      conversationId = await createConversation(
        autoTitle(content || attachments[0]?.name || "Nova conversa"),
      );
      if (!conversationId) return;
    }

    const idempotencyKey = createIdempotencyKey();
    const userMessage: ChatMessage = {
      id: `local-user-${idempotencyKey}`,
      role: "user",
      content,
      attachments: attachments.map(({ name, size }) => ({ name, size })),
    };
    const assistantMessage: ChatMessage = {
      id: `local-assistant-${idempotencyKey}`,
      role: "assistant",
      content: "",
      isPending: true,
    };

    const contextWindow = models.find((model) => model.key === selectedModel)?.context_window;
    const historyMessages = buildHistoryMessages(
      messagesRef.current.filter((message) => !message.isPending),
      contextWindow,
    );
    const payloadMessages: ChatMessage[] = [
      ...historyMessages,
      ...attachments.map((attachment) => ({
        role: "user" as const,
        content: attachmentBlock(attachment),
      })),
      { role: "user" as const, content },
    ];

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setDraft("");
    setAttachments([]);
    setIsSending(true);
    setNotice(null);

    await runCompletion({
      conversationId,
      projectId,
      payloadMessages,
      assistantId: assistantMessage.id as string,
      idempotencyKey,
    });
  }, [
    draft,
    attachments,
    isSending,
    createConversation,
    selectedConversationId,
    selectedModel,
    models,
    runCompletion,
  ]);

  const regenerate = useCallback(async () => {
    const projectId = projectIdRef.current;
    const conversationId = selectedConversationId;
    if (!projectId || !conversationId || isSending) return;

    const history = messagesRef.current.filter((message) => !message.isPending);
    const lastUser = [...history].reverse().find((message) => message.role === "user");
    if (!lastUser?.content.trim()) return;

    const idempotencyKey = createIdempotencyKey();
    const assistantMessage: ChatMessage = {
      id: `local-assistant-${idempotencyKey}`,
      role: "assistant",
      content: "",
      isPending: true,
    };

    const contextWindow = models.find((model) => model.key === selectedModel)?.context_window;
    const payloadMessages = buildHistoryMessages(history, contextWindow);

    setMessages((current) => [...current, assistantMessage]);
    setIsSending(true);
    setNotice(null);

    await runCompletion({
      conversationId,
      projectId,
      payloadMessages,
      assistantId: assistantMessage.id as string,
      idempotencyKey,
    });
  }, [isSending, selectedConversationId, selectedModel, models, runCompletion]);

  const attachFiles = useCallback(async (files: FileList | File[]) => {
    setNotice(null);
    for (const file of Array.from(files)) {
      const error = attachmentError(file, attachments.length);
      if (error) {
        setNotice(error);
        continue;
      }
      try {
        const attachment = await readAttachment(file);
        setAttachments((current) => [...current, attachment]);
      } catch {
        setNotice("Não foi possível ler o arquivo.");
      }
    }
  }, [attachments.length]);

  const removeAttachment = useCallback((id: string) => {
    setAttachments((current) => current.filter((attachment) => attachment.id !== id));
  }, []);

  const openSettings = useCallback(() => setSettingsOpen(true), []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const renameConversation = useCallback(
    async (conversationId: string, title: string) => {
      const projectId = projectIdRef.current;
      if (!projectId) return;
      try {
        const client = makeClient();
        await client.patch<void>(
          `/api/v1/projects/${projectId}/conversations/${conversationId}`,
          { title },
        );
        setConversations((current) =>
          current.map((conversation) =>
            conversation.id === conversationId ? { ...conversation, title } : conversation,
          ),
        );
      } catch (error) {
        handleApiError(error);
      }
    },
    [handleApiError, makeClient],
  );

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      const projectId = projectIdRef.current;
      if (!projectId) return;
      try {
        const client = makeClient();
        await client.delete<void>(`/api/v1/projects/${projectId}/conversations/${conversationId}`);
        setConversations((current) =>
          current.filter((conversation) => conversation.id !== conversationId),
        );
        if (selectedConversationId === conversationId) {
          setSelectedConversationId(null);
          setMessages([]);
        }
      } catch (error) {
        handleApiError(error);
      }
    },
    [handleApiError, makeClient, selectedConversationId],
  );

  const toggleSidebar = useCallback(() => setSidebarOpen((open) => !open), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  return useMemo(
    () => ({
      authState,
      authInfo,
      conversations,
      models,
      selectedModel,
      selectedConversationId,
      messages,
      draft,
      isSending,
      notice,
      sidebarOpen,
      attachments,
      settingsOpen,
      setDraft,
      setSelectedModel,
      setNotice,
      handleLogin,
      handleLogout,
      selectConversation,
      newConversation,
      send,
      regenerate,
      stop,
      renameConversation,
      deleteConversation,
      toggleSidebar,
      closeSidebar,
      attachFiles,
      removeAttachment,
      openSettings,
      closeSettings,
    }),
    [
      authState,
      authInfo,
      conversations,
      models,
      selectedModel,
      selectedConversationId,
      messages,
      draft,
      isSending,
      notice,
      sidebarOpen,
      attachments,
      settingsOpen,
      handleLogin,
      handleLogout,
      selectConversation,
      newConversation,
      send,
      regenerate,
      stop,
      renameConversation,
      deleteConversation,
      toggleSidebar,
      closeSidebar,
      attachFiles,
      removeAttachment,
      openSettings,
      closeSettings,
    ],
  );
}

function autoTitle(content: string): string {
  const singleLine = content.replace(/\s+/g, " ").trim();
  return singleLine.length > 48 ? `${singleLine.slice(0, 48).trimEnd()}…` : singleLine;
}
