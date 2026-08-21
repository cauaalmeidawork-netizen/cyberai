import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProductApp } from "./product-app";

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
    permissions: [
      "project.read",
      "project.write",
      "conversation.read",
      "conversation.write",
      "document.read",
      "document.write",
      "billing.read",
    ],
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
    document.cookie = "cyberai_csrf=csrf-token";
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads the authenticated shell from the backend session", async () => {
    vi.stubGlobal("fetch", vi.fn(workspaceFetch));

    render(<ProductApp />);

    await waitFor(() => {
      expect(screen.getAllByText("IR Triage").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Plan pro")).toBeInTheDocument();
    expect(screen.getByText("Test Org")).toBeInTheDocument();
  });

  it("redirects unauthenticated users to backend OIDC login", async () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign: assignMock, href: "" },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/api/v1/auth/me")
          ? jsonResponse(
              { detail: "Authentication is required.", code: "authentication_required" },
              401,
            )
          : jsonResponse({}),
      ),
    );

    render(<ProductApp />);

    await userEvent.click(await screen.findByRole("button", { name: /Sign in with SSO/i }));

    expect(assignMock).toHaveBeenCalledWith("http://localhost:3000/api/v1/auth/login?return_to=%2F");
  });

  it("clears tenant scoped UI state when the session expires", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/api/v1/auth/me")
          ? jsonResponse({ detail: "Session expired", code: "invalid_session" }, 401)
          : jsonResponse({}),
      ),
    );

    render(<ProductApp />);

    expect(await screen.findByRole("button", { name: /Sign in with SSO/i })).toBeInTheDocument();
    expect(screen.queryByText("IR Triage")).not.toBeInTheDocument();
  });

  it("creates a conversation and renders streamed assistant content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = await workspaceFetch(input, init);
        if (base.status !== 404) {
          return base;
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method === "POST") {
          expect(init.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
          return jsonResponse({
            id: "conversation-1",
            project_id: "project-1",
            title: "Threat review",
          });
        }
        if (url.endsWith("/api/v1/projects/project-1/conversations/conversation-1/messages")) {
          expect(init?.credentials).toBe("include");
          return streamResponse("Use least privilege and review detections.");
        }
        return jsonResponse({}, 404);
      }),
    );

    render(<ProductApp />);

    await waitFor(() => {
      expect(screen.getAllByText("IR Triage").length).toBeGreaterThan(0);
    });
    await userEvent.type(screen.getByPlaceholderText("Conversation title"), "Threat review");
    await userEvent.click(screen.getByRole("button", { name: /New conversation/i }));
    await userEvent.type(
      await screen.findByPlaceholderText(/Ask about detection/i),
      "How should we triage this?",
    );
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    expect(await screen.findByText("Use least privilege and review detections.")).toBeInTheDocument();
  });

  it("ingests and deletes text documents through the existing JSON document API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = await workspaceFetch(input, init);
        if (base.status !== 404) {
          return base;
        }
        if (url.endsWith("/api/v1/projects/project-1/documents") && init?.method === "POST") {
          expect(init.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
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
          expect(init?.method).toBe("DELETE");
          return new Response(null, { status: 204 });
        }
        return jsonResponse({}, 404);
      }),
    );

    render(<ProductApp />);

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

  it("starts checkout and customer portal from backend-provided sessions", async () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign: assignMock },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const base = await workspaceFetch(input, init);
        if (base.status !== 404) {
          return base;
        }
        if (url.endsWith("/api/v1/billing/checkout")) {
          expect(init?.method).toBe("POST");
          const body = init?.body;
          expect(body).toBeDefined();
          expect(JSON.parse(String(body))).toEqual({ plan: "pro" });
          return jsonResponse({ url: "https://checkout.test" });
        }
        if (url.endsWith("/api/v1/billing/portal")) {
          expect(init?.method).toBe("POST");
          return jsonResponse({ url: "https://portal.test" });
        }
        return jsonResponse({}, 404);
      }),
    );

    render(<ProductApp />);

    await waitFor(() => {
      expect(screen.getByText("Plan pro")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("button", { name: /Upgrade plan/i }));
    await userEvent.click(screen.getByRole("button", { name: /Manage subscription/i }));

    expect(assignMock).toHaveBeenCalledWith("https://checkout.test");
    expect(assignMock).toHaveBeenCalledWith("https://portal.test");
  });
});

async function workspaceFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url.endsWith("/api/v1/auth/me")) {
    return authMeResponse();
  }
  if (url.endsWith("/api/v1/projects")) {
    return jsonResponse([{ id: "project-1", name: "IR Triage", description: null }]);
  }
  if (url.endsWith("/api/v1/models")) {
    return jsonResponse({ data: [] });
  }
  if (url.endsWith("/api/v1/billing/limits")) {
    return jsonResponse({
      plan: "pro",
      subscription_status: "active",
      quotas: [],
      rag_allowed: true,
      document_limit: 25,
      allowed_models: null,
      checkout_available: true,
      portal_available: true,
    });
  }
  if (url.endsWith("/api/v1/billing/usage")) {
    return jsonResponse({ plan: "pro", subscription_status: "active", usage: [] });
  }
  if (url.endsWith("/api/v1/projects/project-1/conversations") && init?.method !== "POST") {
    return jsonResponse([]);
  }
  if (url.endsWith("/api/v1/projects/project-1/documents") && init?.method !== "POST") {
    return jsonResponse([]);
  }
  return jsonResponse({}, 404);
}
