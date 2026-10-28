export type ChunkStrategy = "structure";
export type DocumentStatus = "queued" | "parsing" | "chunking" | "indexing" | "ready" | "failed";

export interface SourceBlock {
  id: string;
  kind: "heading" | "paragraph" | "table";
  title: string;
  text: string;
  clause?: string;
  page: number;
  /** Top-left origin, normalized to 0–1000. A chunk may reference several boxes. */
  box: [number, number, number, number];
  table?: { headers: string[]; rows: string[][] };
  lineStart?: number;
  lineEnd?: number;
}

export interface KnowledgeChunk {
  id: string;
  title: string;
  text: string;
  blockIds: string[];
  kind: "text" | "table";
  enabled: boolean;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  filename: string;
  format: "pdf" | "md";
  bytes: number;
  pages: number;
  status: DocumentStatus;
  error?: string;
  sourceUrl?: string;
  sourceKind: "fixture" | "upload";
  sourceMapAvailable: boolean;
  blocks: SourceBlock[];
  chunks: KnowledgeChunk[];
  strategy: ChunkStrategy;
  targetLength: number;
  overlap: number;
  revision: number;
  updatedAt: string;
  chunkCount: number;
  chunksLoaded: boolean;
  activeRevision: number | null;
  activeIndexId: string | null;
  sourceText?: string;
  maxLength: number;
  minLength: number;
}

export interface ChunkConfiguration {
  strategy: ChunkStrategy;
  targetLength: number;
  maxLength: number;
  minLength: number;
}

export interface RetrievalSettings {
  method: "vector";
  candidateCount: number;
  resultCount: number;
  rerank: boolean;
}

export interface RetrievalHit {
  documentId: string;
  chunkId: string;
  title: string;
  text: string;
  score?: number; scoreKind?: "rerank" | "distance";
  pages: number[];
}

export interface Citation {
  documentId: string;
  chunkId: string;
  title: string;
  clause: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  modelId?: string;
  toolAccess?: ChatToolAccess;
  selectedSkills?: string[];
  content: string;
  citations?: Citation[];
  steps?: string[];
  tools?: ChatToolCall[];
  todos?: ChatTodo[];
  status?: "running" | "completed" | "stopped" | "error";
  error?: string;
  stopped?: boolean;
  presentations?: PresentationSlot[];
}

export interface ChatToolAccess {
  knowledge: boolean;
  data: boolean;
}

export interface ChatToolCall {
  id: string;
  name: string;
  title: string;
  state: "input-available" | "output-available" | "output-error" | "output-denied";
  input: Record<string, unknown>;
  output?: unknown;
  errorText?: string;
}

export interface ChatTodo {
  id: string;
  title: string;
  description?: string;
  status: "pending" | "in_progress" | "completed" | "blocked";
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export interface ChatModel { id: string; name: string; profile: { max_input_tokens?: number; max_output_tokens?: number; tool_calling?: boolean }; profile_source: string }

export interface WorkspaceSnapshot {
  models: ChatModel[];
  documents: KnowledgeDocument[];
  conversations: Conversation[];
  retrieval: RetrievalSettings;
  retrievalCapabilities: { rerankModel: string | null };
  loading: boolean;
  connectionError: string | null;
  detailErrors: Record<string, string>;
  chunkDefaults: ChunkConfiguration;
}

export type ReplyEvent =
  | { type: "step"; text: string }
  | { type: "tool"; tool: ChatToolCall }
  | { type: "todos"; todos: ChatTodo[] }
  | { type: "delta"; text: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "presentation"; slot: PresentationSlot };

/** UI contract backed by authenticated HTTP and SSE services. */
export interface WorkspaceRepository {
  getSnapshot(): WorkspaceSnapshot;
  subscribe(listener: () => void): () => void;
  connect(): () => void;
  refresh(): Promise<void>;
  loadDocument(id: string): Promise<void>;
  upload(files: File[], configuration: ChunkConfiguration): Promise<string[]>;
  addExample(configuration: ChunkConfiguration): Promise<string>;
  reprocess(id: string, configuration: ChunkConfiguration): Promise<void>;
  removeDocument(id: string): Promise<void>;
  setChunkEnabled(documentId: string, chunkId: string, enabled: boolean): Promise<void>;
  retrieve(question: string, signal?: AbortSignal): Promise<RetrievalHit[]>;
  createConversation(): string;
  removeConversation(id: string): { conversation: Conversation; index: number } | null;
  restoreConversation(conversation: Conversation, index: number): void;
  appendMessage(conversationId: string, message: ChatMessage): void;
  updateMessage(conversationId: string, messageId: string, patch: Partial<ChatMessage>): void;
  reply(question: string, signal: AbortSignal, options?: { modelId?: string; tools?: ChatToolAccess; conversationId?: string; skills?: string[] }): AsyncGenerator<ReplyEvent>;
  dispose(): void;
}
import type { PresentationSlot } from "@/features/chat/presentation-types";
