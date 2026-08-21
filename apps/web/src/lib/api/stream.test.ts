import { describe, expect, it, vi } from "vitest";

import { streamConversationMessage } from "./stream";

describe("SSE chat client", () => {
  it("parses conversation stream events without inventing deltas", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode(
            [
              'data: {"event":"started","model":"mock-chat","is_fallback":false}\n\n',
              'data: {"event":"delta","text":"final answer"}\n\n',
              'data: {"event":"completed","finish_reason":"stop","usage":{"input_tokens":4,"output_tokens":2}}\n\n',
              "data: [DONE]\n\n",
            ].join(""),
          ),
        );
        controller.close();
      },
    });
    const fetchImpl = vi.fn(async () => new Response(body, { status: 200 }));

    const events = [];
    for await (const event of streamConversationMessage({
      baseUrl: "",
      token: "test-token",
      projectId: "project-1",
      conversationId: "conversation-1",
      payload: {
        messages: [{ role: "user", content: "hello" }],
        max_tokens: 256,
        temperature: 0.2,
      },
      fetchImpl,
    })) {
      events.push(event);
    }

    expect(events).toEqual([
      { event: "started", model: "mock-chat", is_fallback: false },
      { event: "delta", text: "final answer" },
      {
        event: "completed",
        finish_reason: "stop",
        usage: { input_tokens: 4, output_tokens: 2 },
      },
    ]);
  });
});
