import type { AuthMe, ChatMessage, Conversation, ModelInfo } from "@/types/api";

export interface Attachment {
  id: string;
  name: string;
  size: number;
  content: string;
}

export interface ConversationGroup {
  label: string;
  conversations: Conversation[];
}

export interface ChatState {
  authInfo: AuthMe | null;
  conversations: Conversation[];
  models: ModelInfo[];
  selectedModel: string;
  selectedConversationId: string | null;
  messages: ChatMessage[];
  draft: string;
  isSending: boolean;
  notice: string | null;
}

export function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const now = Date.now();
  const day = 86_400_000;

  const buckets: ConversationGroup[] = [
    { label: "Hoje", conversations: [] },
    { label: "Ontem", conversations: [] },
    { label: "Últimos 7 dias", conversations: [] },
    { label: "Mais antigos", conversations: [] },
  ];

  for (const conversation of conversations) {
    const created = conversation.created_at ? Date.parse(conversation.created_at) : null;
    if (created === null || Number.isNaN(created)) {
      buckets[3].conversations.push(conversation);
      continue;
    }
    const age = now - created;
    if (age < day) {
      buckets[0].conversations.push(conversation);
    } else if (age < 2 * day) {
      buckets[1].conversations.push(conversation);
    } else if (age < 7 * day) {
      buckets[2].conversations.push(conversation);
    } else {
      buckets[3].conversations.push(conversation);
    }
  }

  return buckets.filter((bucket) => bucket.conversations.length > 0);
}
