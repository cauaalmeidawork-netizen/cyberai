import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./app-shell";

vi.mock("./markdown-renderer", () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div>{content}</div>,
}));

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "x-request-id": "req-test" },
  });
}

function authMeResponse(): Response {
  return jsonResponse({
    user_id: "user-1",
    active_org_id: "org-1",
    membership_id: "membership-1",
    role: "admin",
    permissions: ["project.read", "project.write", "conversation.read", "conversation.write"],
    organizations: [
      {
        id: "membership-1",
        org_id: "org-1",
        org_slug: "test-org",
        org_display_name: "Test Org",
        role: "admin",
        status: "active",
      },
    ],
  });
}

function streamResponse(events: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode(events.join("")));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

function delayedStreamResponse(events: string[], gapMs = 20): Response {
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      const encoder = new TextEncoder();
      for (const event of events) {
        controller.enqueue(encoder.encode(event));
        await new Promise((resolve) => window.setTimeout(resolve, gapMs));
      }
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

beforeEach(() => {
  document.cookie = "cyberai_csrf=csrf-token";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Nomercy AppShell", () => {
  it("renders the premium home state with Nomercy branding", async () => {
    vi.stubGlobal("fetch", vi.fn(workspaceFetch));

    render(<AppShell />);

    expect(await screen.findByText("Como posso ajudar?")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Pergunte ao Nomercy")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Nova conversa/i }).length).toBeGreaterThan(0);
  });

  it("creates a conversation and streams assistant content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = await workspaceFetch(input, init);
        if (base.status !== 404) return base;
        if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method === "POST") {
          expect(init.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
          return jsonResponse({
            id: "conversation-1",
            project_id: "project-1",
            title: "Como identificar serviços com nmap",
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations/conversation-1/messages")) {
          return streamResponse([
            sse({ event: "started", model: "openai-compatible-chat", is_fallback: false }),
            sse({ event: "delta", text: "Use " }),
            sse({ event: "delta", text: "nmap -sV" }),
            sse({
              event: "completed",
              finish_reason: "stop",
              usage: { input_tokens: 6, output_tokens: 3 },
            }),
            "data: [DONE]\n\n",
          ]);
        }
        return jsonResponse({}, 404);
      }),
    );

    render(<AppShell />);

    await screen.findByText("Como posso ajudar?");
    const composer = screen.getByPlaceholderText("Pergunte ao Nomercy");
    await userEvent.type(composer, "Como identificar serviços com nmap?");
    await userEvent.click(screen.getByRole("button", { name: /Enviar mensagem/i }));

    expect(await screen.findByText("Como identificar serviços com nmap?")).toBeInTheDocument();
    expect(await screen.findByText(/nmap -sV/)).toBeInTheDocument();
  });

  it("shows research status and sources from research events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = await workspaceFetch(input, init);
        if (base.status !== 404) return base;
        if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method === "POST") {
          return jsonResponse({
            id: "conversation-1",
            project_id: "project-1",
            title: "CVE-2024-3094",
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations/conversation-1/messages")) {
          return delayedStreamResponse(
            [
              sse({ event: "research_started", decision: "quick", queries: ["CVE-2024-3094"], providers: ["NVD", "CISA KEV"] }),
              sse({
                event: "source",
                citation_index: 1,
                url: "https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
                title: "CVE-2024-3094",
                domain: "nvd.nist.gov",
                source_type: "authoritative",
                published_at: null,
              }),
              sse({ event: "research_completed", source_count: 1 }),
              sse({ event: "delta", text: "Backdoor em xz-utils." }),
              sse({
                event: "completed",
                finish_reason: "stop",
                usage: { input_tokens: 10, output_tokens: 4 },
              }),
              "data: [DONE]\n\n",
            ],
            25,
          );
        }
        return jsonResponse({}, 404);
      }),
    );

    render(<AppShell />);

    await screen.findByText("Como posso ajudar?");
    await userEvent.type(
      screen.getByPlaceholderText("Pergunte ao Nomercy"),
      "CVE-2024-3094 está sendo explorada?",
    );
    await userEvent.click(screen.getByRole("button", { name: /Enviar mensagem/i }));

    expect(await screen.findByText(/Consultando NVD/)).toBeInTheDocument();
    expect(await screen.findByText(/Backdoor em xz-utils/)).toBeInTheDocument();
    expect(await screen.findByText(/Fontes 1/)).toBeInTheDocument();
  });
});

async function workspaceFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url.endsWith("/api/v1/auth/me")) {
    return authMeResponse();
  }
  if (url.endsWith("/api/v1/projects")) {
    return jsonResponse([{ id: "project-1", name: "Geral", description: null }]);
  }
  if (url.endsWith("/api/v1/models")) {
    return jsonResponse({
      default_model: "openai-compatible-chat",
      data: [
        {
          key: "openai-compatible-chat",
          display_name: "Qwen 2.5 3B Local",
          description: "Local Ollama model",
          context_window: 32768,
          max_output_tokens: 2048,
          tasks: ["chat"],
        },
      ],
    });
  }
  if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method !== "POST") {
    return jsonResponse([]);
  }
  return jsonResponse({}, 404);
}
