export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ChatProvider = "ollama" | "openai_compatible";

export interface AuthenticatedUser {
  id: string;
  email: string | null;
  display_name: string;
}

export interface ChatModelOption {
  provider: ChatProvider;
  model: string;
  configured: boolean;
  is_default: boolean;
}

export interface ChatModelCatalog {
  default_provider: ChatProvider;
  default_model: string;
  models: ChatModelOption[];
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  source: "provider" | "estimate";
}

export interface AgentToolCall {
  skill_name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
}

export interface SkillSummary {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  usage: TokenUsage | null;
  tool_calls: AgentToolCall[];
  attachment_ids: string[];
  images: RelevantImage[];
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface DocumentSummary {
  document_id: string;
  source_name: string;
  chunks_indexed: number;
  uploaded_at: string;
  is_shared: boolean;
}

export interface KnowledgeSearchHit {
  chunk_id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  score: number;
  metadata: Record<string, string | number>;
}

export interface ChatDoneEvent {
  provider: ChatProvider;
  model: string;
  answer: string;
  usage: TokenUsage;
  images: RelevantImage[];
  conversation_id: string | null;
  message_id: string | null;
}

export interface RelevantImage {
  document_id: string;
  image_id: string;
  source_name: string;
  location: string;
  url: string;
}

export interface AgentRunResult {
  answer: string;
  tool_calls: AgentToolCall[];
  images: RelevantImage[];
}

async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with HTTP ${response.status}`;
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getCurrentUser() {
  return apiRequest<AuthenticatedUser>("/api/auth/me");
}

export function signUp(input: {
  email: string;
  password: string;
  display_name: string;
}) {
  return apiRequest<AuthenticatedUser>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function signIn(input: { email: string; password: string }) {
  return apiRequest<AuthenticatedUser>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function signOut() {
  return apiRequest<void>("/api/auth/logout", { method: "POST" });
}

export function getChatModels() {
  return apiRequest<ChatModelCatalog>("/api/models");
}

export function getSkills() {
  return apiRequest<SkillSummary[]>("/api/skills");
}

export function getConversations() {
  return apiRequest<ConversationSummary[]>("/api/conversations");
}

export function getConversation(conversationId: string) {
  return apiRequest<ConversationDetail>(
    `/api/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export function createConversation() {
  return apiRequest<ConversationSummary>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "新對話" }),
  });
}

export function deleteConversation(conversationId: string) {
  return apiRequest<void>(
    `/api/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
}

export function getDocuments() {
  return apiRequest<DocumentSummary[]>("/api/documents");
}

export function searchKnowledge(query: string, topK = 5) {
  return apiRequest<{ query: string; results: KnowledgeSearchHit[] }>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export async function uploadDocument(
  file: File,
  isShared = false,
): Promise<DocumentSummary> {
  const form = new FormData();
  form.set("file", file);
  form.set("is_shared", String(isShared));
  return apiRequest<DocumentSummary>("/api/documents", {
    method: "POST",
    body: form,
  });
}

export function runAgent(
  prompt: string,
  conversationId: string,
  attachmentIds: string[],
) {
  return apiRequest<AgentRunResult>("/api/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      conversation_id: conversationId,
      attachment_ids: attachmentIds,
    }),
  });
}

export async function streamChat(
  prompt: string,
  conversationId: string,
  attachmentIds: string[],
  selection: ChatModelOption,
  signal: AbortSignal,
  onToken: (token: string) => void,
): Promise<ChatDoneEvent> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    cache: "no-store",
    credentials: "include",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      conversation_id: conversationId,
      attachment_ids: attachmentIds,
      provider: selection.provider,
      model: selection.model,
    }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    throw new ApiError(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Chat request failed with HTTP ${response.status}`,
      response.status,
    );
  }
  if (!response.body) {
    throw new Error("The chat response did not include an event stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: ChatDoneEvent | null = null;

  const dispatch = (frame: string) => {
    let eventName = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n")) as
      | { token: string }
      | ChatDoneEvent
      | { detail: string };
    if (eventName === "token" && "token" in payload) {
      onToken(payload.token);
    } else if (eventName === "done" && "usage" in payload) {
      completed = payload;
    } else if (eventName === "error" && "detail" in payload) {
      throw new Error(payload.detail);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd !== -1) {
        dispatch(buffer.slice(0, frameEnd));
        buffer = buffer.slice(frameEnd + 2);
        frameEnd = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!completed) throw new Error("The chat stream ended before its done event");
  return completed;
}
