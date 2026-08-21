import { expect, test } from "@playwright/test";

test("beta product flow persists chat history across reload", async ({ page }) => {
  let projectCreated = false;
  let conversationCreated = false;
  let documentCreated = false;
  let persistedMessages: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/auth/me") {
      await route.fulfill({
        json: {
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
        },
      });
      return;
    }
    if (path === "/api/v1/auth/logout") {
      expect(request.headers()["x-csrf-token"]).toBe("csrf-token");
      await route.fulfill({ status: 204 });
      return;
    }
    if (path === "/api/v1/projects" && request.method() === "GET") {
      await route.fulfill({
        json: projectCreated
          ? [{ id: "project-1", name: "IR Triage", description: "Beta smoke" }]
          : [],
      });
      return;
    }
    if (path === "/api/v1/projects" && request.method() === "POST") {
      projectCreated = true;
      await route.fulfill({
        json: { id: "project-1", name: "IR Triage", description: "Beta smoke" },
      });
      return;
    }
    if (path === "/api/v1/models") {
      await route.fulfill({ json: { data: [] } });
      return;
    }
    if (path === "/api/v1/billing/limits") {
      await route.fulfill({
        json: {
          plan: "pro",
          quotas: [],
          rag_allowed: true,
          document_limit: 25,
          allowed_models: null,
        },
      });
      return;
    }
    if (path === "/api/v1/billing/usage") {
      await route.fulfill({ json: { plan: "pro", usage: [] } });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations" && request.method() === "GET") {
      await route.fulfill({
        json: conversationCreated
          ? [{ id: "conversation-1", project_id: "project-1", title: "Threat review" }]
          : [],
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations" && request.method() === "POST") {
      conversationCreated = true;
      await route.fulfill({
        json: { id: "conversation-1", project_id: "project-1", title: "Threat review" },
      });
      return;
    }
    if (
      path === "/api/v1/projects/project-1/conversations/conversation-1/messages" &&
      request.method() === "GET"
    ) {
      await route.fulfill({
        json: {
          messages: persistedMessages,
          pagination: { limit: 100, offset: 0, next_offset: null },
        },
      });
      return;
    }
    if (
      path === "/api/v1/projects/project-1/conversations/conversation-1/messages" &&
      request.method() === "POST"
    ) {
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      persistedMessages = [
        {
          id: "message-1",
          conversation_id: "conversation-1",
          role: "user",
          content: "How should we triage this alert?",
          tokens_used: null,
          created_at: "2026-08-20T00:00:00Z",
        },
        {
          id: "message-2",
          conversation_id: "conversation-1",
          role: "assistant",
          content: "Start with scope, impact, containment, and detections.",
          tokens_used: 8,
          created_at: "2026-08-20T00:00:01Z",
        },
      ];
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"event":"started","model":"mock-chat","is_fallback":false}\n\n',
          'data: {"event":"delta","text":"Start with scope, impact, containment, and detections."}\n\n',
          'data: {"event":"completed","finish_reason":"stop","usage":{"input_tokens":9,"output_tokens":8}}\n\n',
          "data: [DONE]\n\n",
        ].join(""),
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/documents" && request.method() === "GET") {
      await route.fulfill({
        json: documentCreated
          ? [
              {
                id: "document-1",
                project_id: "project-1",
                title: "Runbook",
                source_type: "text",
                status: "completed",
                content_hash: "hash",
              },
            ]
          : [],
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/documents" && request.method() === "POST") {
      documentCreated = true;
      await route.fulfill({
        json: {
          id: "document-1",
          project_id: "project-1",
          title: "Runbook",
          source_type: "text",
          status: "completed",
          content_hash: "hash",
        },
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/documents/document-1") {
      documentCreated = false;
      await route.fulfill({ status: 204 });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  await page.context().addCookies([
    {
      name: "cyberai_csrf",
      value: "csrf-token",
      url: "http://127.0.0.1:3000",
    },
  ]);
  await page.goto("/");
  await page.getByPlaceholder("Project name").fill("IR Triage");
  await page.getByPlaceholder("Description").fill("Beta smoke");
  await page.getByRole("button", { name: /Create project/i }).click();
  await expect(page.getByText("Plan pro")).toBeVisible();

  await page.getByPlaceholder("Conversation title").fill("Threat review");
  await page.getByRole("button", { name: /New conversation/i }).click();
  await page.getByPlaceholder(/Ask about detection/i).fill("How should we triage this alert?");
  await page.getByRole("button", { name: /^Send$/ }).click();
  await expect(page.getByText("Start with scope, impact, containment, and detections.")).toBeVisible();

  await page.reload();
  await expect(page.getByText("How should we triage this alert?")).toBeVisible();
  await expect(page.getByText("Start with scope, impact, containment, and detections.")).toBeVisible();

  await page.getByPlaceholder("Document title").fill("Runbook");
  await page.getByPlaceholder("Controlled document text").fill("Escalate P1.");
  await page.getByRole("button", { name: /Ingest document/i }).click();
  await expect(page.getByText("Runbook")).toBeVisible();
  await page.getByRole("button", { name: /Delete Runbook/i }).click();
  await expect(page.getByText("Runbook")).toBeHidden();

  await page.getByRole("button", { name: /Logout/i }).click();
  await expect(page.getByRole("button", { name: /Sign in with SSO/i })).toBeVisible();
});
