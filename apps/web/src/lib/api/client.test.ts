import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./client";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends cookie credentials without bearer auth and parses json responses", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.credentials).toBe("include");
      expect(init?.headers).not.toMatchObject({ Authorization: expect.any(String) });
      return new Response(JSON.stringify({ data: [{ key: "mock" }] }), {
        status: 200,
        headers: { "content-type": "application/json", "x-request-id": "req-1" },
      });
    });
    const client = createApiClient({
      baseUrl: "https://api.example.test",
      fetchImpl: fetchMock,
    });

    const result = await client.get<{ data: { key: string }[] }>("/api/v1/models");

    expect(result.data[0]?.key).toBe("mock");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/models",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("turns problem json into typed errors with request ids", async () => {
    const client = createApiClient({
      baseUrl: "",
      fetchImpl: async () =>
        new Response(
          JSON.stringify({
            type: "https://errors.cyberai.dev/quota_exceeded",
            title: "Quota Exceeded",
            status: 429,
            detail: "The organization quota for this resource has been exhausted.",
            code: "quota_exceeded",
            request_id: "req-quota",
          }),
          { status: 429, headers: { "content-type": "application/problem+json" } },
        ),
    });

    await expect(client.get("/api/v1/billing/usage")).rejects.toMatchObject({
      status: 429,
      code: "quota_exceeded",
      requestId: "req-quota",
    });
  });

  it("invalidates local session on any 401", async () => {
    const onUnauthorized = vi.fn();
    const client = createApiClient({
      baseUrl: "",
      onUnauthorized,
      fetchImpl: async () =>
        new Response(JSON.stringify({ detail: "Token expired", code: "http_401" }), {
          status: 401,
          headers: { "content-type": "application/problem+json" },
        }),
    });

    await expect(client.get("/api/v1/projects")).rejects.toBeInstanceOf(ApiError);

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("adds csrf token from cookie on unsafe requests", async () => {
    document.cookie = "cyberai_csrf=csrf-token";
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    const client = createApiClient({
      baseUrl: "",
      fetchImpl: fetchMock,
    });

    await client.post("/api/v1/auth/logout", {});

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/logout",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token" }),
        credentials: "include",
      }),
    );
  });
});
