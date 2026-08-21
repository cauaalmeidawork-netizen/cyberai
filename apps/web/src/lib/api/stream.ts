import { ApiError, buildUrl, responseToApiError } from "./client";

import type { ChatCompletionPayload, ChatStreamEvent } from "@/types/api";

type FetchLike = typeof fetch;

export interface StreamConversationMessageOptions {
  baseUrl: string;
  token: string;
  projectId: string;
  conversationId: string;
  payload: ChatCompletionPayload;
  signal?: AbortSignal;
  fetchImpl?: FetchLike;
}

export async function* streamConversationMessage(
  options: StreamConversationMessageOptions,
): AsyncGenerator<ChatStreamEvent> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const response = await fetchImpl(
    buildUrl(
      options.baseUrl,
      `/api/v1/projects/${options.projectId}/conversations/${options.conversationId}/messages`,
    ),
    {
      method: "POST",
      signal: options.signal,
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        Authorization: `Bearer ${options.token}`,
      },
      body: JSON.stringify(options.payload),
    },
  );

  if (!response.ok) {
    throw await responseToApiError(response);
  }
  if (!response.body) {
    throw new ApiError("The server did not return a stream.", {
      status: response.status,
      code: "stream_unavailable",
      requestId: response.headers.get("x-request-id"),
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const event = parseSseBlock(block);
        if (event === "done") {
          return;
        }
        if (event) {
          yield event;
        }
      }
    }

    const trailing = parseSseBlock(buffer);
    if (trailing && trailing !== "done") {
      yield trailing;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(block: string): ChatStreamEvent | "done" | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n")
    .trim();

  if (!data) {
    return null;
  }
  if (data === "[DONE]") {
    return "done";
  }
  return JSON.parse(data) as ChatStreamEvent;
}
