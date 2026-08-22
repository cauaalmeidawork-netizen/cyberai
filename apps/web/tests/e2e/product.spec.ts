import { expect, test } from "@playwright/test";

import type { Page } from "@playwright/test";

const sse = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/auth/me") {
      await route.fulfill({
        json: {
          user_id: "user-1",
          active_org_id: "org-1",
          membership_id: "membership-1",
          role: "owner",
          permissions: [
            "project.read",
            "project.write",
            "conversation.read",
            "conversation.write",
            "billing.read",
          ],
          organizations: [
            {
              id: "membership-1",
              org_id: "org-1",
              org_slug: "nomercy",
              org_display_name: "Nomercy",
              role: "owner",
              status: "active",
            },
          ],
        },
      });
      return;
    }
    if (path === "/api/v1/projects" && method === "GET") {
      await route.fulfill({ json: [{ id: "project-1", name: "Geral", description: null }] });
      return;
    }
    if (path === "/api/v1/models") {
      await route.fulfill({
        json: {
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
        },
      });
      return;
    }
    if (path === "/api/v1/billing/usage") {
      await route.fulfill({
        json: {
          plan: "free",
          subscription_status: "active",
          usage: [
            {
              resource: "requests",
              used: 12,
              reserved: 0,
              limit: 100,
              remaining: 88,
              period_start: new Date().toISOString(),
              period_end: new Date().toISOString(),
            },
          ],
        },
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations" && method === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations" && method === "POST") {
      await route.fulfill({
        json: {
          id: "conversation-1",
          project_id: "project-1",
          title: "Nova conversa",
          created_at: new Date().toISOString(),
        },
      });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations/conversation-1/messages") {
      const body = request.postDataJSON() as { messages?: Array<{ content: string }> };
      const content = body?.messages?.at(-1)?.content ?? "";

      if (content.includes("erro")) {
        await route.fulfill({
          status: 503,
          contentType: "application/problem+json",
          json: {
            title: "Service unavailable",
            status: 503,
            detail: "The model provider is unavailable.",
            code: "provider_unavailable",
          },
        });
        return;
      }

      let bodyText = "";
      if (content.includes("CVE-")) {
        bodyText = [
          sse({ event: "research_started", decision: "quick", queries: ["CVE-2024-3094"], providers: ["NVD", "CISA KEV", "OSV", "GitHub Advisory"] }),
          sse({
            event: "source",
            citation_index: 1,
            url: "https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
            title: "CVE-2024-3094 — xz-utils backdoor",
            domain: "nvd.nist.gov",
            source_type: "authoritative",
            published_at: "2024-03-29",
          }),
          sse({ event: "research_completed", source_count: 1 }),
          sse({ event: "delta", text: "A CVE-2024-3094 foi adicionada ao KEV [1]." }),
          sse({
            event: "completed",
            finish_reason: "stop",
            usage: { input_tokens: 12, output_tokens: 9 },
          }),
          "data: [DONE]\n\n",
        ].join("");
      } else if (content.includes("nmap")) {
        bodyText = [
          sse({ event: "started", model: "openai-compatible-chat", is_fallback: false }),
          sse({ event: "delta", text: "Use:\n\n```bash\nnmap -sV <host>\n```\n\n`-sV` detecta versões." }),
          sse({
            event: "completed",
            finish_reason: "stop",
            usage: { input_tokens: 9, output_tokens: 12 },
          }),
          "data: [DONE]\n\n",
        ].join("");
      } else {
        bodyText = [
          sse({ event: "started", model: "openai-compatible-chat", is_fallback: false }),
          sse({ event: "delta", text: "Olá! Como posso ajudar?" }),
          sse({
            event: "completed",
            finish_reason: "stop",
            usage: { input_tokens: 5, output_tokens: 6 },
          }),
          "data: [DONE]\n\n",
        ].join("");
      }

      await route.fulfill({ contentType: "text/event-stream", body: bodyText });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

async function boot(page: Page) {
  await page.context().addCookies([
    { name: "cyberai_csrf", value: "csrf-token", url: "http://127.0.0.1:3000" },
  ]);
  await page.goto("/");
  await expect(page.getByText("Como posso ajudar?")).toBeVisible();
}

async function send(page: Page, text: string) {
  const composer = page.getByPlaceholder("Pergunte ao Nomercy");
  await composer.fill(text);
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
}

test("desktop flow: home, send, stream, sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);
  await page.screenshot({ path: "test-results/screenshots/home-desktop.png" });

  await expect(page.getByPlaceholder("Pergunte ao Nomercy")).toBeVisible();
  await send(page, "Como identificar serviços com nmap?");

  await expect(page.getByText(/nmap -sV/)).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/code-block.png" });

  await page.getByRole("button", { name: "Nova conversa" }).first().click();
  await expect(page.getByText("Como posso ajudar?")).toBeVisible();
});

test("mobile: drawer opens and closes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await boot(page);
  await page.screenshot({ path: "test-results/screenshots/home-mobile.png" });

  await page.getByRole("button", { name: "Abrir menu" }).click();
  await expect(page.getByText("Nomercy AI").first()).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/mobile-drawer.png" });

  const drawer = page.getByRole("complementary", { name: "Histórico de conversas" });
  await page.getByRole("button", { name: "Fechar histórico" }).click();
  await expect(drawer).toHaveClass(/-translate-x-full/);
});

test("research: CVE triggers sources, citations and provider status", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  await send(page, "CVE-2024-3094 está sendo explorada?");

  await expect(page.getByText(/adicionada ao KEV/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Fonte 1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Fontes 1/ })).toBeVisible();

  await page.getByRole("button", { name: /Fontes 1/ }).click();
  await expect(page.getByText(/nvd\.nist\.gov/)).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/sources.png" });
});

test("error maps to a friendly notice", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  await send(page, "force um erro");

  await expect(page.getByText(/indisponível/)).toBeVisible();
});

test("settings sheet opens with account info and closes", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  await page.getByRole("button", { name: "Configurações" }).click();
  await expect(page.getByRole("dialog", { name: "Configurações" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sair" })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/settings.png" });

  await page.getByRole("button", { name: "Fechar configurações" }).click();
  await expect(page.getByRole("dialog", { name: "Configurações" })).toBeHidden();
});
