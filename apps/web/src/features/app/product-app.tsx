"use client";

import {
  AlertTriangle,
  Bot,
  ChevronRight,
  FileText,
  Folder,
  LogOut,
  MessageSquare,
  Plus,
  Send,
  Square,
  Trash2,
  Upload,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { createApiClient, ApiError } from "@/lib/api/client";
import { streamConversationMessage } from "@/lib/api/stream";
import { API_BASE_URL } from "@/lib/config";
import type {
  AuthMe,
  BillingLimits,
  BillingSession,
  BillingUsage,
  ChatMessage,
  Conversation,
  DocumentRecord,
  MessageHistoryResponse,
  ModelInfo,
  ModelListResponse,
  Project,
  Quota,
} from "@/types/api";

type LoadState = "idle" | "loading" | "ready" | "error";
type AuthState = "loading" | "authenticated" | "unauthenticated";

interface WorkspaceState {
  projects: Project[];
  conversations: Conversation[];
  documents: DocumentRecord[];
  models: ModelInfo[];
  limits: BillingLimits | null;
  usage: BillingUsage | null;
}

const EMPTY_WORKSPACE: WorkspaceState = {
  projects: [],
  conversations: [],
  documents: [],
  models: [],
  limits: null,
  usage: null,
};

export function ProductApp() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [authInfo, setAuthInfo] = useState<AuthMe | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceState>(EMPTY_WORKSPACE);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messagesByConversation, setMessagesByConversation] = useState<
    Record<string, ChatMessage[]>
  >({});
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [lastRequestId, setLastRequestId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(false);
  const [draft, setDraft] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [newConversationTitle, setNewConversationTitle] = useState("");
  const [documentTitle, setDocumentTitle] = useState("");
  const [documentContent, setDocumentContent] = useState("");
  const streamAbortRef = useRef<AbortController | null>(null);

  const clearTenantState = useCallback(() => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setWorkspace(EMPTY_WORKSPACE);
    setSelectedProjectId(null);
    setSelectedConversationId(null);
    setMessagesByConversation({});
    setSelectedModel("");
    setDraft("");
    setNewProjectName("");
    setNewProjectDescription("");
    setNewConversationTitle("");
    setDocumentTitle("");
    setDocumentContent("");
    setIsSending(false);
    setRagEnabled(false);
  }, []);

  const invalidateSession = useCallback(() => {
    setAuthInfo(null);
    setAuthState("unauthenticated");
    clearTenantState();
    setNotice("Session expired. Sign in again.");
  }, [clearTenantState]);

  const makeClient = useCallback(
    () =>
      createApiClient({
        baseUrl: API_BASE_URL,
        onUnauthorized: invalidateSession,
      }),
    [invalidateSession],
  );

  const selectedProject = workspace.projects.find((project) => project.id === selectedProjectId);
  const selectedConversation = workspace.conversations.find(
    (conversation) => conversation.id === selectedConversationId,
  );
  const selectedMessages = selectedConversationId
    ? messagesByConversation[selectedConversationId] ?? []
    : [];

  const handleApiError = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      setLastRequestId(error.requestId);
      setNotice(messageForApiError(error));
      return;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      setNotice("Generation stopped.");
      return;
    }
    setNotice("Network error. Check the API connection and try again.");
  }, []);

  const loadConversationMessages = useCallback(
    async (projectId: string, conversationId: string) => {
      const client = makeClient();
      const history = await client.get<MessageHistoryResponse>(
        `/api/v1/projects/${projectId}/conversations/${conversationId}/messages?limit=100&offset=0`,
      );
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: history.messages,
      }));
    },
    [makeClient],
  );

  const loadProjectDetails = useCallback(
    async (projectId: string, preferredConversationId: string | null = null) => {
      const client = makeClient();
      const [conversations, documents] = await Promise.all([
        client.get<Conversation[]>(`/api/v1/projects/${projectId}/conversations`),
        client.get<DocumentRecord[]>(`/api/v1/projects/${projectId}/documents`),
      ]);
      setWorkspace((current) => ({ ...current, conversations, documents }));
      const nextConversationId =
        conversations.find((conversation) => conversation.id === preferredConversationId)?.id ??
        conversations[0]?.id ??
        null;
      setSelectedConversationId(nextConversationId);
      if (nextConversationId) {
        await loadConversationMessages(projectId, nextConversationId);
      }
    },
    [loadConversationMessages, makeClient],
  );

  const loadWorkspace = useCallback(async () => {
    if (authState !== "authenticated") {
      setLoadState("idle");
      return;
    }
    setLoadState("loading");
    setNotice(null);
    try {
      const client = makeClient();
      const [projects, modelsResponse, limits, usage] = await Promise.all([
        client.get<Project[]>("/api/v1/projects"),
        client.get<ModelListResponse>("/api/v1/models"),
        client.get<BillingLimits>("/api/v1/billing/limits"),
        client.get<BillingUsage>("/api/v1/billing/usage"),
      ]);
      const projectId = projects[0]?.id ?? null;
      setWorkspace((current) => ({
        ...current,
        projects,
        models: modelsResponse.data,
        limits,
        usage,
      }));
      setSelectedModel((current) => {
        if (current && modelsResponse.data.some((model) => model.key === current)) {
          return current;
        }
        return modelsResponse.default_model;
      });
      setSelectedProjectId(projectId);
      if (projectId) {
        await loadProjectDetails(projectId);
      } else {
        setWorkspace((current) => ({ ...current, conversations: [], documents: [] }));
      }
      setLoadState("ready");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        return;
      }
      setLoadState("error");
      handleApiError(error);
    }
  }, [authState, handleApiError, loadProjectDetails, makeClient]);

  useEffect(() => {
    let cancelled = false;
    const client = makeClient();
    void client
      .get<AuthMe>("/api/v1/auth/me")
      .then((me) => {
        if (cancelled) {
          return;
        }
        setAuthInfo(me);
        setAuthState("authenticated");
        setNotice(null);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          setAuthState("unauthenticated");
          return;
        }
        setAuthState("unauthenticated");
        handleApiError(error);
      });
    return () => {
      cancelled = true;
    };
  }, [handleApiError, makeClient]);

  useEffect(() => {
    if (authState !== "authenticated") {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      void loadWorkspace();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [authState, loadWorkspace]);

  function handleLogin() {
    const loginUrl = new URL("/api/v1/auth/login", API_BASE_URL || window.location.origin);
    loginUrl.searchParams.set("return_to", "/");
    window.location.assign(loginUrl.toString());
  }

  async function handleLogout() {
    try {
      const client = makeClient();
      await client.post<void>("/api/v1/auth/logout", {});
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        handleApiError(error);
      }
    } finally {
      setAuthInfo(null);
      setAuthState("unauthenticated");
      clearTenantState();
      setNotice(null);
    }
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newProjectName.trim()) {
      return;
    }
    try {
      const client = makeClient();
      const project = await client.post<Project>("/api/v1/projects", {
        name: newProjectName.trim(),
        description: newProjectDescription.trim() || null,
      });
      setWorkspace((current) => ({ ...current, projects: [project, ...current.projects] }));
      setSelectedProjectId(project.id);
      setSelectedConversationId(null);
      setNewProjectName("");
      setNewProjectDescription("");
      await loadProjectDetails(project.id);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    setSelectedConversationId(null);
    setWorkspace((current) => ({ ...current, conversations: [], documents: [] }));
    try {
      await loadProjectDetails(projectId);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleSelectConversation(conversationId: string) {
    if (!selectedProjectId) {
      return;
    }
    setSelectedConversationId(conversationId);
    try {
      await loadConversationMessages(selectedProjectId, conversationId);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleCreateConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !newConversationTitle.trim()) {
      return;
    }
    try {
      const client = makeClient();
      const conversation = await client.post<Conversation>(
        `/api/v1/projects/${selectedProjectId}/conversations`,
        { title: newConversationTitle.trim() },
      );
      setWorkspace((current) => ({
        ...current,
        conversations: [conversation, ...current.conversations],
      }));
      setSelectedConversationId(conversation.id);
      setMessagesByConversation((current) => ({ ...current, [conversation.id]: [] }));
      setNewConversationTitle("");
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleSendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !selectedConversationId || !draft.trim() || isSending) {
      return;
    }

    const userMessage: ChatMessage = { role: "user", content: draft.trim() };
    const conversationId = selectedConversationId;
    const existingMessages = messagesByConversation[conversationId] ?? [];
    const nextMessages = [...existingMessages, userMessage];
    setMessagesByConversation((current) => ({
      ...current,
      [conversationId]: nextMessages,
    }));
    setDraft("");
    setIsSending(true);
    setNotice(null);

    const controller = new AbortController();
    streamAbortRef.current = controller;
    const idempotencyKey = createIdempotencyKey();

    try {
      let assistantContent = "";
      for await (const event of streamConversationMessage({
        baseUrl: API_BASE_URL,
        projectId: selectedProjectId,
        conversationId,
        idempotencyKey,
        signal: controller.signal,
        payload: {
          messages: nextMessages.map((message) => ({
            role: message.role,
            content: message.content,
          })),
          model: selectedModel || null,
          max_tokens: 1024,
          temperature: 0.2,
          rag_enabled: ragEnabled,
        },
      })) {
        if (event.event === "delta") {
          assistantContent += event.text;
          setMessagesByConversation((current) => ({
            ...current,
            [conversationId]: [
              ...nextMessages,
              { role: "assistant", content: assistantContent },
            ],
          }));
        }
      }
    } catch (error) {
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: existingMessages,
      }));
      handleApiError(error);
    } finally {
      streamAbortRef.current = null;
      setIsSending(false);
    }
  }

  function handleStopGeneration() {
    streamAbortRef.current?.abort();
  }

  async function handleCreateDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !documentTitle.trim() || !documentContent.trim()) {
      return;
    }
    try {
      const client = makeClient();
      const document = await client.post<DocumentRecord>(
        `/api/v1/projects/${selectedProjectId}/documents`,
        {
          title: documentTitle.trim(),
          content: documentContent.trim(),
          source_type: "text",
        },
      );
      setWorkspace((current) => ({
        ...current,
        documents: [document, ...current.documents],
      }));
      setDocumentTitle("");
      setDocumentContent("");
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleDeleteDocument(documentId: string) {
    if (!selectedProjectId) {
      return;
    }
    try {
      const client = makeClient();
      await client.delete<void>(`/api/v1/projects/${selectedProjectId}/documents/${documentId}`);
      setWorkspace((current) => ({
        ...current,
        documents: current.documents.filter((document) => document.id !== documentId),
      }));
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleUpgrade(plan: string) {
    try {
      const client = makeClient();
      const session = await client.post<BillingSession>("/api/v1/billing/checkout", { plan });
      window.location.assign(session.url);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function handleManageSubscription() {
    try {
      const client = makeClient();
      const session = await client.post<BillingSession>("/api/v1/billing/portal", {});
      window.location.assign(session.url);
    } catch (error) {
      handleApiError(error);
    }
  }

  if (authState === "loading") {
    return (
      <main className="min-h-screen bg-background text-foreground">
        <section className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
          <SkeletonLines />
        </section>
      </main>
    );
  }

  if (authState === "unauthenticated") {
    return (
      <main className="min-h-screen bg-background text-foreground">
        <section className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
          <div className="mb-8">
            <p className="mb-3 font-mono text-xs uppercase tracking-[0.24em] text-accent">
              CYBER AI
            </p>
            <h1 className="text-3xl font-semibold">Connect workspace</h1>
            <p className="mt-3 text-sm leading-6 text-muted">
              Sign in through your organization identity provider. The browser only receives an
              application session cookie.
            </p>
          </div>
          {notice && <InlineNotice message={notice} requestId={lastRequestId} />}
          <button className="primary-button w-full" type="button" onClick={handleLogin}>
            <ChevronRight size={16} aria-hidden />
            Sign in with SSO
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="product-shell">
        <aside className="sidebar" aria-label="Workspace navigation">
          <div className="brand-lockup">
            <span className="brand-mark">CA</span>
            <div>
              <p className="font-semibold leading-tight">CYBER AI</p>
              <p className="text-xs text-muted">
                {authInfo?.organizations.find((org) => org.org_id === authInfo.active_org_id)
                  ?.org_display_name ?? "Workspace"}
              </p>
            </div>
          </div>

          <section className="nav-section">
            <SectionHeader icon={<Folder size={15} />} label="Projects" />
            <form className="stack-sm" onSubmit={handleCreateProject}>
              <input
                className="control compact"
                placeholder="Project name"
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
              />
              <input
                className="control compact"
                placeholder="Description"
                value={newProjectDescription}
                onChange={(event) => setNewProjectDescription(event.target.value)}
              />
              <button className="secondary-button w-full" type="submit">
                <Plus size={14} aria-hidden />
                Create project
              </button>
            </form>
            <div className="list-stack">
              {workspace.projects.length === 0 && loadState !== "loading" ? (
                <p className="empty-text">Create a project to start a workspace.</p>
              ) : null}
              {workspace.projects.map((project) => (
                <button
                  className={`list-row ${project.id === selectedProjectId ? "active" : ""}`}
                  key={project.id}
                  type="button"
                  onClick={() => void handleSelectProject(project.id)}
                >
                  <span className="truncate text-left">{project.name}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="nav-section">
            <SectionHeader icon={<MessageSquare size={15} />} label="Conversations" />
            <form className="stack-sm" onSubmit={handleCreateConversation}>
              <input
                className="control compact"
                placeholder="Conversation title"
                value={newConversationTitle}
                onChange={(event) => setNewConversationTitle(event.target.value)}
                disabled={!selectedProjectId}
              />
              <button className="secondary-button w-full" type="submit" disabled={!selectedProjectId}>
                <Plus size={14} aria-hidden />
                New conversation
              </button>
            </form>
            <div className="list-stack">
              {selectedProjectId && workspace.conversations.length === 0 ? (
                <p className="empty-text">No conversations in this project.</p>
              ) : null}
              {workspace.conversations.map((conversation) => (
                <button
                  className={`list-row ${
                    conversation.id === selectedConversationId ? "active" : ""
                  }`}
                  key={conversation.id}
                  type="button"
                  onClick={() => void handleSelectConversation(conversation.id)}
                >
                  <span className="truncate text-left">{conversation.title}</span>
                </button>
              ))}
            </div>
          </section>

          <button className="ghost-button mt-auto" type="button" onClick={handleLogout}>
            <LogOut size={16} aria-hidden />
            Logout
          </button>
        </aside>

        <section className="chat-surface" aria-label="Chat">
          <header className="topbar">
            <div>
              <p className="eyebrow">{selectedProject ? selectedProject.name : "Workspace"}</p>
              <h1 className="text-xl font-semibold">
                {selectedConversation ? selectedConversation.title : "Conversation"}
              </h1>
            </div>
            <label className="model-select">
              <span>Model</span>
              <select
                className="control compact"
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
              >
                <option value="" disabled>
                  Loading models
                </option>
                {workspace.models.map((model) => (
                  <option key={model.key} value={model.key}>
                    {model.display_name}
                  </option>
                ))}
              </select>
            </label>
          </header>

          {notice && <InlineNotice message={notice} requestId={lastRequestId} />}
          {loadState === "loading" ? <SkeletonLines /> : null}

          <div className="message-stream" aria-live="polite">
            {!selectedConversation ? (
              <div className="empty-panel">
                <Bot size={22} aria-hidden />
                <p>Select or create a conversation.</p>
              </div>
            ) : selectedMessages.length === 0 ? (
              <div className="empty-panel">
                <Bot size={22} aria-hidden />
                <p>Ask a defensive security question to start this thread.</p>
              </div>
            ) : (
              selectedMessages.map((message, index) => (
                <article
                  className={`message ${message.role}`}
                  key={message.id ?? `${message.role}-${index}`}
                >
                  <span className="message-role">{message.role}</span>
                  <p>{message.content}</p>
                </article>
              ))
            )}
          </div>

          <form className="composer" onSubmit={handleSendMessage}>
            <textarea
              className="composer-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                selectedConversation
                  ? "Ask about detection, triage, code review, or RAG context"
                  : "Create a conversation first"
              }
              disabled={!selectedConversation || isSending}
              rows={3}
            />
            <div className="composer-actions">
              <label className="rag-toggle">
                <input
                  type="checkbox"
                  checked={ragEnabled}
                  onChange={(event) => setRagEnabled(event.target.checked)}
                  disabled={!workspace.limits?.rag_allowed || isSending}
                />
                <span>Use RAG</span>
              </label>
              {isSending ? (
                <button className="secondary-button" type="button" onClick={handleStopGeneration}>
                  <Square size={14} aria-hidden />
                  Stop
                </button>
              ) : null}
              <button
                className="primary-button"
                type="submit"
                disabled={!selectedConversation || !draft.trim() || isSending}
              >
                <Send size={15} aria-hidden />
                Send
              </button>
            </div>
          </form>
        </section>

        <aside className="context-panel" aria-label="Documents and usage">
          <section className="panel-section">
            <SectionHeader icon={<FileText size={15} />} label="Documents" />
            <form className="stack-sm" onSubmit={handleCreateDocument}>
              <input
                className="control compact"
                placeholder="Document title"
                value={documentTitle}
                onChange={(event) => setDocumentTitle(event.target.value)}
                disabled={!selectedProjectId}
              />
              <textarea
                className="control text-area"
                placeholder="Controlled document text"
                value={documentContent}
                onChange={(event) => setDocumentContent(event.target.value)}
                disabled={!selectedProjectId}
              />
              <button className="secondary-button w-full" type="submit" disabled={!selectedProjectId}>
                <Upload size={14} aria-hidden />
                Ingest document
              </button>
            </form>
            <div className="list-stack">
              {workspace.documents.length === 0 ? (
                <p className="empty-text">No documents indexed for this project.</p>
              ) : null}
              {workspace.documents.map((document) => (
                <div className="document-row" key={document.id}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{document.title}</p>
                    <p className="text-xs text-muted">{document.status}</p>
                  </div>
                  <button
                    className="icon-button"
                    type="button"
                    aria-label={`Delete ${document.title}`}
                    onClick={() => void handleDeleteDocument(document.id)}
                  >
                    <Trash2 size={15} aria-hidden />
                  </button>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-section">
            <SectionHeader icon={<AlertTriangle size={15} />} label="Usage" />
            <p className="mb-3 text-sm font-medium">
              Plan {workspace.limits?.plan ?? workspace.usage?.plan ?? "loading"}
            </p>
            <p className="mb-3 text-xs text-muted">
              Status{" "}
              {workspace.limits?.subscription_status ??
                workspace.usage?.subscription_status ??
                "loading"}
            </p>
            <div className="quota-stack">
              {(workspace.usage?.usage ?? workspace.limits?.quotas ?? []).map((quota) => (
                <QuotaMeter key={quota.resource} quota={quota} />
              ))}
              {workspace.limits ? (
                <>
                  <div className="usage-line">
                    <span>RAG</span>
                    <strong>{workspace.limits.rag_allowed ? "Allowed" : "Blocked"}</strong>
                  </div>
                  <div className="usage-line">
                    <span>Documents</span>
                    <strong>{workspace.limits.document_limit}</strong>
                  </div>
                </>
              ) : null}
            </div>
            <div className="mt-4 grid gap-2">
              {workspace.limits?.checkout_available ? (
                <button
                  className="secondary-button w-full"
                  type="button"
                  onClick={() => void handleUpgrade("pro")}
                >
                  <ChevronRight size={14} aria-hidden />
                  Upgrade plan
                </button>
              ) : null}
              {workspace.limits?.portal_available ? (
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => void handleManageSubscription()}
                >
                  Manage subscription
                </button>
              ) : null}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}

function SectionHeader({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="section-header">
      {icon}
      <h2>{label}</h2>
    </div>
  );
}

function InlineNotice({ message, requestId }: { message: string; requestId: string | null }) {
  return (
    <div className="notice" role="status">
      <AlertTriangle size={16} aria-hidden />
      <span>{message}</span>
      {requestId ? <code>{requestId}</code> : null}
    </div>
  );
}

function SkeletonLines() {
  return (
    <div className="skeleton-stack" aria-label="Loading workspace">
      <span />
      <span />
      <span />
    </div>
  );
}

function QuotaMeter({ quota }: { quota: Quota }) {
  const denominator = quota.limit > 0 ? quota.limit : 1;
  const percentage = Math.min(100, Math.round(((quota.used + quota.reserved) / denominator) * 100));

  return (
    <div className="quota-meter">
      <div className="usage-line">
        <span>{quota.resource.replaceAll("_", " ")}</span>
        <strong>{quota.remaining} left</strong>
      </div>
      <div className="meter-track" aria-hidden>
        <span style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function createIdempotencyKey(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function messageForApiError(error: ApiError): string {
  if (error.status === 400 || error.status === 422) {
    return "The request is invalid. Review the highlighted input and try again.";
  }
  if (error.status === 403) {
    if (error.code === "policy_denied" || error.code === "unsafe_output") {
      return "Blocked by security policy.";
    }
    return "Your current access does not allow this action.";
  }
  if (error.status === 404) {
    return "The selected resource was not found. Refresh the workspace.";
  }
  if (error.status === 409) {
    return "This action conflicts with the current workspace state.";
  }
  if (error.status === 413) {
    return "The request is too large.";
  }
  if (error.status === 429) {
    return error.code === "quota_exceeded"
      ? "Quota exceeded for this billing period."
      : "Too many requests. Try again later.";
  }
  if (error.status === 503 || error.status === 504) {
    return "The model provider or a dependency is unavailable.";
  }
  return "Request failed. Try again.";
}
