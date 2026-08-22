import { describe, expect, it } from "vitest";

import { buildHistoryMessages, estimateTokens } from "./message-parts";

import type { ChatMessage } from "@/types/api";

function message(role: "user" | "assistant", content: string, isPending = false): ChatMessage {
  return { role, content, isPending };
}

describe("buildHistoryMessages", () => {
  it("returns only role and content for the payload", () => {
    const result = buildHistoryMessages([message("user", "olá")]);
    expect(result).toEqual([{ role: "user", content: "olá" }]);
  });

  it("keeps the most recent messages and preserves order", () => {
    const history = [
      message("user", "a"),
      message("assistant", "b"),
      message("user", "c"),
      message("assistant", "d"),
    ];
    const result = buildHistoryMessages(history);
    expect(result.map((entry) => entry.content)).toEqual(["a", "b", "c", "d"]);
  });

  it("skips empty and system messages", () => {
    const result = buildHistoryMessages([
      { role: "system", content: "ignored" },
      message("user", "   "),
      message("user", "keep"),
    ]);
    expect(result).toEqual([{ role: "user", content: "keep" }]);
  });

  it("caps history by a token budget", () => {
    const big = "x".repeat(40_000);
    const history = [message("user", big), message("assistant", "recent answer")];
    const result = buildHistoryMessages(history);
    expect(result.some((entry) => entry.content === "recent answer")).toBe(true);
    expect(result[0].content).toBe("recent answer");
  });

  it("respects a provided context window", () => {
    const big = "x".repeat(40_000);
    const history = [message("user", big), message("assistant", "recent")];
    const result = buildHistoryMessages(history, 4096);
    expect(result.length).toBe(1);
  });
});

describe("estimateTokens", () => {
  it("estimates roughly four characters per token", () => {
    expect(estimateTokens("12345678")).toBe(2);
  });
});
