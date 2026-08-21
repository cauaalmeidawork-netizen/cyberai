import { describe, expect, it } from "vitest";

import { loginUrlForEnvironment } from "./auth-entry";

describe("auth entry", () => {
  it("uses local dev login when the browser talks to the same-origin proxy", () => {
    expect(loginUrlForEnvironment("", "development")).toBe(
      "/api/v1/auth/dev-login?return_to=%2F",
    );
  });

  it("keeps OIDC login for deployed API targets", () => {
    expect(loginUrlForEnvironment("", "production")).toBe(
      "/api/v1/auth/login?return_to=%2F",
    );
    expect(loginUrlForEnvironment("https://api.cyberai.example", "development")).toBe(
      "/api/v1/auth/login?return_to=%2F",
    );
  });
});
