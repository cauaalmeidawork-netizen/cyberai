import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AUTH_SESSION_KEY } from "@/features/auth/session";

import { ProductApp } from "./product-app";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "x-request-id": "req-test" },
  });
}

function streamResponse(text: string): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(
        encoder.encode(
          [
            'data: {"event":"started","model":"mock-chat","is_fallback":false}\n\n',
            `data: ${JSON.stringify({ event: "delta", text })}\n\n`,
            'data: {"event":"completed","finish_reason":"stop","usage":{"input_tokens":6,"output_tokens":3}}\n\n',
            "data: [DONE]\n\n",
          ].join(""),
        ),
      );
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

describe("product app", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("authenticates with an externally supplied token and loads tenant data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/projects")) {
          return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
        }
        if (url.endsWith("/api/v1/models")) {
          return jsonResponse({ data: [] });
        }
        if (url.endsWith("/api/v1/billing/limits")) {
          return jsonResponse({
            plan: "pro",
            quotas: [],
            rag_allowed: true,
            document_limit: 25,
            allowed_models: null,
          });
        }
        if (url.endsWith("/api/v1/billing/usage")) {
          return jsonResponse({ plan: "pro", usage: [] });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations")) {
          return jsonResponse([]);
        }
        if (url.endsWith("/api/v1/projects/project-1/documents")) {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<ProductApp />);

    await userEvent.type(screen.getByLabelText(/Bearer token/i), "external-token");
    await userEvent.click(screen.getByRole("button", { name: /Connect/i }));

    expect(sessionStorage.getItem(AUTH_SESSION_KEY)).toBe("external-token");
    await waitFor(() => {
      expect(screen.getAllByText("IR Triage").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Plan pro")).toBeInTheDocument();
  });

  it("clears tenant scoped UI state when the API returns 401", async () => {
    sessionStorage.setItem(AUTH_SESSION_KEY, "expired-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            type: "https://errors.cyberai.dev/http_401",
            title: "Unauthorized",
            status: 401,
            detail: "Token expired",
            code: "http_401",
            request_id: "req-expired",
          },
          401,
        ),
      ),
    );

    render(<ProductApp />);

    await waitFor(() => {
      expect(sessionStorage.getItem(AUTH_SESSION_KEY)).toBeNull();
    });
    expect(screen.getByLabelText(/Bearer token/i)).toBeInTheDocument();
    expect(screen.queryByText("IR Triage")).not.toBeInTheDocument();
  });

  it("creates a conversation and renders streamed assistant content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/projects")) {
          return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
        }
        if (url.endsWith("/api/v1/models")) {
          return jsonResponse({
            data: [
              {
                key: "mock-chat",
                display_name: "Mock Chat",
                description: "CI model",
                context_window: 8192,
                max_output_tokens: 1024,
                tasks: ["chat"],
              },
            ],
          });
        }
        if (url.endsWith("/api/v1/billing/limits")) {
          return jsonResponse({
            plan: "pro",
            quotas: [],
            rag_allowed: true,
            document_limit: 25,
            allowed_models: null,
          });
        }
        if (url.endsWith("/api/v1/billing/usage")) {
          return jsonResponse({ plan: "pro", usage: [] });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method === "POST") {
          return jsonResponse({
            id: "conversation-1",
            project_id: "project-1",
            title: "Threat review",
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations")) {
          return jsonResponse([]);
        }
        if (url.endsWith("/api/v1/projects/project-1/documents")) {
          return jsonResponse([]);
        }
        if (
          url.endsWith("/api/v1/projects/project-1/conversations/conversation-1/messages")
        ) {
          return streamResponse("Use least privilege and review detections.");
        }
        return jsonResponse({});
      }),
    );

    render(<ProductApp />);

    await userEvent.type(screen.getByLabelText(/Bearer token/i), "external-token");
    await userEvent.click(screen.getByRole("button", { name: /Connect/i }));
    await waitFor(() => {
      expect(screen.getAllByText("IR Triage").length).toBeGreaterThan(0);
    });

    await userEvent.type(screen.getByPlaceholderText("Conversation title"), "Threat review");
    await userEvent.click(screen.getByRole("button", { name: /New conversation/i }));
    await waitFor(() => {
      expect(screen.getAllByText("Threat review").length).toBeGreaterThan(0);
    });

    await userEvent.type(
      screen.getByPlaceholderText(/Ask about detection/i),
      "How should we triage this?",
    );
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    expect(await screen.findByText("Use least privilege and review detections.")).toBeInTheDocument();
  });

  it("loads persisted conversation history when a conversation is selected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/projects")) {
          return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
        }
        if (url.endsWith("/api/v1/models")) {
          return jsonResponse({ data: [] });
        }
        if (url.endsWith("/api/v1/billing/limits")) {
          return jsonResponse({
            plan: "pro",
            quotas: [],
            rag_allowed: true,
            document_limit: 25,
            allowed_models: null,
          });
        }
        if (url.endsWith("/api/v1/billing/usage")) {
          return jsonResponse({ plan: "pro", usage: [] });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations")) {
          return jsonResponse([
            { id: "conversation-1", project_id: "project-1", title: "Recovered thread" },
          ]);
        }
        if (url.includes("/api/v1/projects/project-1/conversations/conversation-1/messages")) {
          return jsonResponse({
            messages: [
              {
                id: "message-1",
                conversation_id: "conversation-1",
                role: "user",
                content: "What happened before reload?",
                tokens_used: null,
                created_at: "2026-08-20T00:00:00Z",
              },
              {
                id: "message-2",
                conversation_id: "conversation-1",
                role: "assistant",
                content: "Recovered persisted answer.",
                tokens_used: 4,
                created_at: "2026-08-20T00:00:01Z",
              },
            ],
            pagination: { limit: 100, offset: 0, next_offset: null },
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/documents")) {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<ProductApp />);

    await userEvent.type(screen.getByLabelText(/Bearer token/i), "external-token");
    await userEvent.click(screen.getByRole("button", { name: /Connect/i }));

    expect(await screen.findByText("Recovered persisted answer.")).toBeInTheDocument();
  });

  it("sends chat turns with an idempotency key and backend-controlled RAG intent", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/projects")) {
        return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
      }
      if (url.endsWith("/api/v1/models")) {
        return jsonResponse({ data: [] });
      }
      if (url.endsWith("/api/v1/billing/limits")) {
        return jsonResponse({
          plan: "pro",
          quotas: [],
          rag_allowed: true,
          document_limit: 25,
          allowed_models: null,
        });
      }
      if (url.endsWith("/api/v1/billing/usage")) {
        return jsonResponse({ plan: "pro", usage: [] });
      }
      if (url.endsWith("/api/v1/projects/project-1/conversations")) {
        return jsonResponse([{ id: "conversation-1", project_id: "project-1", title: "RAG thread" }]);
      }
      if (url.includes("/api/v1/projects/project-1/conversations/conversation-1/messages")) {
        if (init?.method === "POST") {
          expect(init.headers).toMatchObject({ "Idempotency-Key": expect.any(String) });
          expect(JSON.parse(String(init.body))).toMatchObject({ rag_enabled: true });
          return streamResponse("RAG-backed response.");
        }
        return jsonResponse({ messages: [], pagination: { limit: 100, offset: 0, next_offset: null } });
      }
      if (url.endsWith("/api/v1/projects/project-1/documents")) {
        return jsonResponse([]);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProductApp />);

    await userEvent.type(screen.getByLabelText(/Bearer token/i), "external-token");
    await userEvent.click(screen.getByRole("button", { name: /Connect/i }));
    await waitFor(() => {
      expect(screen.getAllByText("RAG thread").length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getByLabelText(/Use RAG/i));
    await userEvent.type(
      screen.getByPlaceholderText(/Ask about detection/i),
      "Use project documents?",
    );
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    expect(await screen.findByText("RAG-backed response.")).toBeInTheDocument();
  });

  it("ingests and deletes text documents through the existing JSON document API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/projects")) {
          return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
        }
        if (url.endsWith("/api/v1/models")) {
          return jsonResponse({ data: [] });
        }
        if (url.endsWith("/api/v1/billing/limits")) {
          return jsonResponse({
            plan: "pro",
            quotas: [],
            rag_allowed: true,
            document_limit: 25,
            allowed_models: null,
          });
        }
        if (url.endsWith("/api/v1/billing/usage")) {
          return jsonResponse({ plan: "pro", usage: [] });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations")) {
          return jsonResponse([]);
        }
        if (url.endsWith("/api/v1/projects/project-1/documents") && init?.method === "POST") {
          return jsonResponse({
            id: "document-1",
            project_id: "project-1",
            title: "Runbook",
            source_type: "text",
            status: "ready",
            content_hash: "hash",
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/documents/document-1")) {
          return new Response(null, { status: 204 });
        }
        if (url.endsWith("/api/v1/projects/project-1/documents")) {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<ProductApp />);

    await userEvent.type(screen.getByLabelText(/Bearer token/i), "external-token");
    await userEvent.click(screen.getByRole("button", { name: /Connect/i }));
    await waitFor(() => {
      expect(screen.getAllByText("IR Triage").length).toBeGreaterThan(0);
    });

    await userEvent.type(screen.getByPlaceholderText("Document title"), "Runbook");
    await userEvent.type(screen.getByPlaceholderText("Controlled document text"), "Escalate P1.");
    await userEvent.click(screen.getByRole("button", { name: /Ingest document/i }));

    expect(await screen.findByText("Runbook")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Delete Runbook/i }));

    await waitFor(() => {
      expect(screen.queryByText("Runbook")).not.toBeInTheDocument();
    });
  });
});
