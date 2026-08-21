import { beforeEach, describe, expect, it, vi } from "vitest";

describe("Next API proxy", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
    delete process.env.API_PROXY_TARGET;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it("defaults server-side proxy traffic to the local FastAPI port", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const { GET } = await import("./route");

    await GET(new Request("http://localhost:3000/api/v1/models"), {
      params: Promise.resolve({ path: ["v1", "models"] }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8001/api/v1/models"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("preserves Set-Cookie headers from the backend", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(null, {
          status: 302,
          headers: {
            location: "/",
            "set-cookie": "cyberai_session=session; Path=/; HttpOnly, cyberai_csrf=csrf; Path=/",
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { GET } = await import("./route");

    const response = await GET(
      new Request("http://localhost:3000/api/v1/auth/dev-login?return_to=%2F"),
      { params: Promise.resolve({ path: ["v1", "auth", "dev-login"] }) },
    );

    const cookies = response.headers.getSetCookie?.() ?? [response.headers.get("set-cookie") ?? ""];
    expect(cookies.join("\n")).toContain("cyberai_session=session");
    expect(cookies.join("\n")).toContain("cyberai_csrf=csrf");
  });

  it("passes streaming response bodies through the proxy", async () => {
    const upstreamBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: hello\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(upstreamBody, {
            status: 200,
            headers: { "content-type": "text/event-stream" },
          }),
      ),
    );
    const { POST } = await import("./route");

    const response = await POST(
      new Request("http://localhost:3000/api/v1/projects/p/conversations/c/messages", {
        method: "POST",
        body: "{}",
      }),
      { params: Promise.resolve({ path: ["v1", "projects", "p", "conversations", "c", "messages"] }) },
    );

    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(await response.text()).toBe("data: hello\n\n");
  });
});
