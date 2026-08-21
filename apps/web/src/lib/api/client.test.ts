import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./client";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends bearer auth and parses json responses", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({
        Authorization: "Bearer test-token",
      });
      return new Response(JSON.stringify({ data: [{ key: "mock" }] }), {
        status: 200,
        headers: { "content-type": "application/json", "x-request-id": "req-1" },
      });
    });
    const client = createApiClient({
      baseUrl: "https://api.example.test",
      getToken: () => "test-token",
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
      getToken: () => "test-token",
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
      getToken: () => "expired-token",
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
});
