import { expect, test } from "@playwright/test";

import type { Page } from "@playwright/test";

/**
 * Regression test: ensure no test-pollution markers appear in the normal
 * product UI. This test mocks all API calls (just like the main product
 * tests) so it is fully isolated from the real backend.
 *
 * If any of the forbidden strings appear in the rendered page, the test
 * fails — catching accidental leakage of fixture content into production.
 */

const FORBIDDEN_STRINGS = [
  "CYBERAI_LOCAL_OK",
  "NOMERCY_LOCAL_OK",
  "MockModelProvider",
  "mock-analyst",
  "__smoke_test__",
];

async function mockCleanApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

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
              display_name: "Dolphin 3 8B",
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
          usage: [{ resource: "requests", used: 0, reserved: 0, limit: 100, remaining: 100, period_start: new Date().toISOString(), period_end: new Date().toISOString() }],
        },
      });
      return;
    }
    if (path.endsWith("/conversations") && method === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

test("no test-pollution markers appear in the product UI", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().addCookies([
    { name: "cyberai_csrf", value: "csrf-token", url: "http://127.0.0.1:3000" },
  ]);
  await mockCleanApi(page);
  await page.goto("/");

  // Wait for the app to fully render
  await expect(page.getByText("Como posso ajudar?")).toBeVisible({ timeout: 10_000 });

  // Get the full text content of the page
  const bodyText = await page.evaluate(() => document.body.innerText);

  for (const forbidden of FORBIDDEN_STRINGS) {
    expect(bodyText).not.toContain(forbidden);
  }

  // Also check the raw HTML for hidden markers
  const html = await page.evaluate(() => document.documentElement.innerHTML);
  for (const forbidden of FORBIDDEN_STRINGS) {
    expect(html).not.toContain(forbidden);
  }
});
