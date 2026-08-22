import type { ChatMessage, Role } from "@/types/api";

const HISTORY_TOKEN_BUDGET = 8000;
const CHARS_PER_TOKEN = 4;
const DEFAULT_CONTEXT_WINDOW = 32_768;

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / CHARS_PER_TOKEN);
}

function tokenBudget(contextWindow: number | undefined): number {
  const window = contextWindow ?? DEFAULT_CONTEXT_WINDOW;
  return Math.min(HISTORY_TOKEN_BUDGET, Math.floor(window / 4));
}

export function buildHistoryMessages(
  history: ChatMessage[],
  contextWindow?: number,
): Array<{ role: Role; content: string }> {
  const budget = tokenBudget(contextWindow);
  const recent: Array<{ role: Role; content: string }> = [];
  let tokens = 0;

  for (let index = history.length - 1; index >= 0; index--) {
    const message = history[index];
    if (message.role === "system") {
      continue;
    }
    const content = message.content.trim();
    if (!content) {
      continue;
    }
    const cost = estimateTokens(content);
    if (tokens + cost > budget && recent.length > 0) {
      break;
    }
    recent.push({ role: message.role, content });
    tokens += cost;
  }

  return recent.reverse();
}
