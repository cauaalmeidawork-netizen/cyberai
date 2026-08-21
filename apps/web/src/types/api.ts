export type Role = "system" | "user" | "assistant";

export interface ProblemDocument {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  instance?: string;
  request_id?: string;
  errors?: Array<{
    location: string[];
    message: string;
    type: string;
  }>;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
}

export interface Conversation {
  id: string;
  project_id: string;
  title: string;
}

export interface ChatMessage {
  id?: string;
  conversation_id?: string;
  role: Role;
  content: string;
  tokens_used?: number | null;
  created_at?: string;
}

export interface ChatCompletionPayload {
  messages: ChatMessage[];
  model?: string | null;
  max_tokens: number;
  temperature: number;
  rag_enabled?: boolean;
}

export interface MessageHistoryResponse {
  messages: ChatMessage[];
  pagination: {
    limit: number;
    offset: number;
    next_offset: number | null;
  };
}

export interface DocumentRecord {
  id: string;
  project_id: string;
  title: string;
  source_type: string;
  status: string;
  content_hash: string;
}

export interface ModelInfo {
  key: string;
  display_name: string;
  description: string;
  context_window: number;
  max_output_tokens: number;
  tasks: string[];
}

export interface ModelListResponse {
  data: ModelInfo[];
}

export interface Quota {
  resource: string;
  used: number;
  reserved: number;
  limit: number;
  remaining: number;
  period_start: string;
  period_end: string;
}

export interface BillingLimits {
  plan: string;
  quotas: Quota[];
  rag_allowed: boolean;
  document_limit: number;
  allowed_models: string[] | null;
}

export interface BillingUsage {
  plan: string;
  usage: Quota[];
}

export type ChatStreamEvent =
  | {
      event: "started";
      model: string;
      is_fallback: boolean;
    }
  | {
      event: "delta";
      text: string;
    }
  | {
      event: "completed";
      finish_reason: string;
      usage: {
        input_tokens: number;
        output_tokens: number;
      };
    };
