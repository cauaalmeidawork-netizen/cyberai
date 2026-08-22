import { describe, expect, it } from "vitest";

import { groupConversations } from "./types";
import type { Conversation } from "@/types/api";

function conversation(id: string, created_at: string): Conversation {
  return { id, project_id: "p", title: id, created_at };
}

describe("groupConversations", () => {
  it("buckets conversations by age", () => {
    const now = new Date();
    const iso = (msAgo: number) => new Date(now.getTime() - msAgo).toISOString();
    const conversations = [
      conversation("today", iso(60_000)),
      conversation("yesterday", iso(26 * 3_600_000)),
      conversation("week", iso(4 * 86_400_000)),
      conversation("old", iso(60 * 86_400_000)),
    ];

    const groups = groupConversations(conversations);
    const labels = groups.map((group) => group.label);

    expect(labels).toContain("Hoje");
    expect(labels).toContain("Ontem");
    expect(labels).toContain("Últimos 7 dias");
    expect(labels).toContain("Mais antigos");
  });

  it("drops empty buckets", () => {
    const groups = groupConversations([
      conversation("a", new Date().toISOString()),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Hoje");
  });

  it("treats missing timestamps as old", () => {
    const groups = groupConversations([{ id: "x", project_id: "p", title: "x" }]);
    expect(groups[0].label).toBe("Mais antigos");
  });
});
