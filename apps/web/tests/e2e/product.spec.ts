import { expect, test } from "@playwright/test";

import type { Page } from "@playwright/test";

const sse = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;

const browserDiagnostics = new WeakMap<
  Page,
  { consoleErrors: string[]; requestFailures: string[]; allowedConsoleErrors: RegExp[] }
>();

test.beforeEach(async ({ page }) => {
  const diagnostics = {
    consoleErrors: [] as string[],
    requestFailures: [] as string[],
    allowedConsoleErrors: [] as RegExp[],
  };
  browserDiagnostics.set(page, diagnostics);
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    diagnostics.requestFailures.push(
      `${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "falha desconhecida"}`,
    );
  });
});

test.afterEach(async ({ page }) => {
  const diagnostics = browserDiagnostics.get(page);
  const unexpectedConsoleErrors = (diagnostics?.consoleErrors ?? []).filter(
    (message) => !diagnostics?.allowedConsoleErrors.some((pattern) => pattern.test(message)),
  );
  expect(unexpectedConsoleErrors).toEqual([]);
  expect(diagnostics?.requestFailures ?? []).toEqual([]);
});

async function mockApi(
  page: Page,
  options: { conversations?: Array<Record<string, unknown>> } = {},
) {
  let conversationSequence = 0;

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
      await route.fulfill({ json: options.conversations ?? [] });
      return;
    }
    if (path === "/api/v1/projects/project-1/conversations" && method === "POST") {
      conversationSequence += 1;
      await route.fulfill({
        json: {
          id: `conversation-${conversationSequence}`,
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
      if (content.includes("relatório longo")) {
        bodyText = [
          sse({ event: "started", model: "openai-compatible-chat", is_fallback: false }),
          sse({
            event: "delta",
            text: [
              "## Resumo técnico",
              "",
              "Este relatório reúne contexto suficiente para validar uma resposta editorial extensa sem transformar o conteúdo em cartões.",
              "",
              "- Evidência confirmada",
              "- Impacto delimitado",
              "- Mitigação recomendada",
              "",
              "| Campo | Resultado |",
              "| --- | --- |",
              "| Estado | Analisado |",
              "| Prioridade | Alta |",
              "",
              "```bash",
              "printf '%s\\n' 'linha-extremamente-longa-para-validar-overflow-horizontal-sem-quebrar-o-layout-principal-da-conversa-0123456789-abcdefghijklmnopqrstuvwxyz'",
              "```",
            ].join("\n"),
          }),
          sse({
            event: "completed",
            finish_reason: "stop",
            usage: { input_tokens: 18, output_tokens: 60 },
          }),
          "data: [DONE]\n\n",
        ].join("");
      } else if (content.includes("CVE-")) {
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

test("desktop flow: home, send, stream, sidebar", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);
  await page.screenshot({ path: testInfo.outputPath("home-desktop.png") });

  await expect(page.getByPlaceholder("Pergunte ao Nomercy")).toBeVisible();
  await send(page, "Como identificar serviços com nmap?");

  await expect(page.getByText(/nmap -sV/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("code-block.png") });

  await page.getByRole("button", { name: "Nova conversa" }).first().click();
  await expect(page.getByText("Como posso ajudar?")).toBeVisible();
});

test("responsive shell keeps the empty composer visible without horizontal overflow", async ({
  page,
}, testInfo) => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await boot(page);

    const metrics = await page.getByPlaceholder("Pergunte ao Nomercy").evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      const rect = textarea.getBoundingClientRect();
      return {
        clientHeight: textarea.clientHeight,
        scrollHeight: textarea.scrollHeight,
        left: rect.left,
        right: rect.right,
        viewportWidth: document.documentElement.clientWidth,
        documentWidth: document.documentElement.scrollWidth,
      };
    });

    expect(metrics.scrollHeight, `${viewport.width}px composer content is clipped`).toBeLessThanOrEqual(
      metrics.clientHeight,
    );
    expect(metrics.left).toBeGreaterThanOrEqual(0);
    expect(metrics.right).toBeLessThanOrEqual(metrics.viewportWidth);
    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth);
    if (viewport.width < 1024) {
      await expect(page.getByRole("button", { name: "Abrir menu" })).toBeVisible();
      await expect(
        page.getByRole("complementary", { name: "Histórico de conversas" }),
      ).toHaveClass(/-translate-x-full/);
    } else {
      await expect(page.getByRole("navigation", { name: "Navegação principal" })).toBeVisible();
    }
    await page.screenshot({ path: testInfo.outputPath(`home-${viewport.width}.png`) });
  }
});

test("conversation actions remain reachable by keyboard", async ({ page }) => {
  const title = "Análise do ambiente local";
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page, {
    conversations: [
      {
        id: "existing-conversation",
        project_id: "project-1",
        title,
        created_at: new Date().toISOString(),
      },
    ],
  });
  await boot(page);

  await page.getByRole("button", { name: title, exact: true }).focus();
  await page.keyboard.press("Tab");

  await expect(page.getByRole("button", { name: `Mais opções para ${title}` })).toBeFocused();
});

test("long markdown and code stay inside the conversation canvas", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await mockApi(page);
  await boot(page);

  await send(page, "Gere um relatório longo");

  await expect(page.getByRole("heading", { name: "Resumo técnico" })).toBeVisible();
  await expect(page.locator("table")).toBeVisible();
  const codeBlock = page.locator("pre");
  await expect(codeBlock).toBeVisible();
  await expect(page.locator('[data-streamdown="code-block-header"]')).toContainText("bash");
  await expect(page.getByRole("button", { name: "Copiar" }).first()).toBeVisible();

  const overflow = await codeBlock.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeGreaterThan(overflow.clientWidth);
  expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth);

  await codeBlock.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("long-markdown-1024.png") });
});

test("tablet and mobile drawers open without clipping and close", async ({ page }, testInfo) => {
  for (const viewport of [
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await boot(page);

    await page.getByRole("button", { name: "Abrir menu" }).click();
    await expect(page.getByText("Nomercy AI").first()).toBeVisible();

    const drawer = page.getByRole("complementary", { name: "Histórico de conversas" });
    await expect.poll(async () => Math.round((await drawer.boundingBox())?.x ?? -999)).toBe(0);
    const drawerBox = await drawer.boundingBox();
    const searchBox = await page.getByRole("textbox", { name: "Buscar conversas" }).boundingBox();
    expect(drawerBox).not.toBeNull();
    expect(searchBox).not.toBeNull();
    if (!drawerBox || !searchBox) throw new Error("Drawer bounds are unavailable.");
    const drawerRight = drawerBox.x + drawerBox.width;
    const searchRight = searchBox.x + searchBox.width;
    expect(drawerRight).toBeLessThanOrEqual(viewport.width);
    expect(searchRight).toBeLessThanOrEqual(drawerRight);

    await page.screenshot({ path: testInfo.outputPath(`drawer-${viewport.width}.png`) });
    await page.getByRole("button", { name: "Fechar histórico" }).click();
    await expect(drawer).toHaveClass(/-translate-x-full/);
  }
});

test("mobile drawer provides access to settings", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await boot(page);

  await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.getByRole("button", { name: "Configurações" }).click();

  const dialog = page.getByRole("dialog", { name: "Configurações" });
  await expect(dialog).toBeVisible();
  await expect
    .poll(async () => {
      const box = await dialog.boundingBox();
      return box ? Math.ceil(box.x + box.width) : Number.POSITIVE_INFINITY;
    })
    .toBeLessThanOrEqual(390);
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  if (!dialogBox) throw new Error("Settings bounds are unavailable.");
  expect(dialogBox.x).toBeGreaterThanOrEqual(0);
  expect(dialogBox.x + dialogBox.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: testInfo.outputPath("settings-390.png") });

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("research: CVE triggers sources, citations and provider status", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  await send(page, "CVE-2024-3094 está sendo explorada?");

  await expect(page.getByText(/adicionada ao KEV/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Fonte 1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Fontes 1/ })).toBeVisible();

  await page.getByRole("button", { name: /Fontes 1/ }).click();
  await expect(page.getByText(/nvd\.nist\.gov/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("sources.png") });
});

test("error maps to a friendly notice", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  browserDiagnostics
    .get(page)
    ?.allowedConsoleErrors.push(/Failed to load resource:.*503 \(Service Unavailable\)/);

  await send(page, "force um erro");

  await expect(page.getByText(/indisponível/)).toBeVisible();
});

test("settings sheet opens with account info and closes", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await boot(page);

  await page.getByRole("button", { name: "Configurações" }).click();
  await expect(page.getByRole("dialog", { name: "Configurações" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sair" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("settings.png") });

  await page.getByRole("button", { name: "Fechar configurações" }).click();
  await expect(page.getByRole("dialog", { name: "Configurações" })).toBeHidden();
});
