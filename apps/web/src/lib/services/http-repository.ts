import { authFetch } from "@/lib/access/client";
import type {
  ChatMessage, ChatModel, ChunkConfiguration, Conversation, DocumentStatus, KnowledgeChunk,
  KnowledgeDocument, ReplyEvent, RetrievalHit, SourceBlock, WorkspaceRepository, WorkspaceSnapshot,
} from "./contracts";
import { UploadBatchError } from "./upload-error";
import { defaultChunkConfiguration, processingStatuses } from "./knowledge-config";
import { applyRunEvent, mergeRunSnapshot } from "./run-events";

interface SourceReference {
  kind: string;
  page_index?: number;
  block_index?: number;
  line_start?: number;
  line_end?: number;
  bbox?: [number, number, number, number];
  coordinate_space?: string;
}
interface ChunkMetadata {
  document_id: string;
  source?: string;
  title?: string;
  sequence?: number;
  section_path?: string[];
  source_refs?: SourceReference[];
  rerank_score?: number;
  vector_distance?: number;
}
interface ApiDocument {
  id: string; filename: string; format: "pdf" | "md"; byte_size: number; pages: number;
  status: DocumentStatus; revision: number; active_revision: number | null;
  active_index_id: string | null; updated_at: string; chunk_count?: number;
  source_map_available: boolean;
  chunk_options: { target_chars: number; max_chars: number; min_chars: number };
  latest_job?: { error_message: string | null };
}
interface ApiChunk { id: string; content: string; sequence: number; enabled: boolean; metadata: ChunkMetadata }
interface Page<T> { items: T[]; total: number }
interface SearchDocument { id: string; page_content: string; metadata: ChunkMetadata }

class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await authFetch(`/api/v1${path}`, { ...init, cache: "no-store" }); }
  catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("无法连接服务，请检查后端是否已启动。");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.message === "string" ? body.message :
        typeof body?.detail === "string" ? body.detail :
        response.status === 413 ? "文件超过上传大小限制。" :
        response.status === 422 ? "请求参数不符合要求，请检查后重试。" : "服务请求失败，请稍后重试。",
      response.status,
    );
  }
  return response.json() as Promise<T>;
}
const jsonBody = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const chunkOptions = (config: ChunkConfiguration) => ({
  target_chars: config.targetLength, max_chars: config.maxLength, min_chars: config.minLength,
});
const spanId = (ref: SourceReference) => ref.kind === "markdown_lines"
  ? `lines:${ref.line_start}:${ref.line_end}` : `pdf:${ref.page_index}:${ref.block_index}`;

function normalizeDocument(raw: ApiDocument, cached?: KnowledgeDocument): KnowledgeDocument {
  const sameIndex = cached?.activeIndexId === raw.active_index_id && cached?.sourceMapAvailable === raw.source_map_available;
  return {
    id: raw.id, filename: raw.filename, title: raw.filename.replace(/\.[^.]+$/, ""),
    format: raw.format, bytes: raw.byte_size, pages: raw.pages, status: raw.status,
    sourceUrl: `/api/v1/documents/${raw.id}/source`, sourceKind: "upload",
    sourceMapAvailable: raw.source_map_available, strategy: "structure", overlap: 0,
    targetLength: raw.chunk_options.target_chars, maxLength: raw.chunk_options.max_chars,
    minLength: raw.chunk_options.min_chars,
    revision: raw.revision, activeRevision: raw.active_revision, activeIndexId: raw.active_index_id,
    updatedAt: new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date(raw.updated_at)),
    chunkCount: raw.chunk_count ?? (sameIndex ? cached?.chunkCount ?? 0 : 0),
    chunks: sameIndex ? cached?.chunks ?? [] : [], blocks: sameIndex ? cached?.blocks ?? [] : [],
    chunksLoaded: sameIndex && !!cached?.chunksLoaded, sourceText: cached?.sourceText,
    error: raw.latest_job?.error_message ?? (raw.status === "failed" ? cached?.error : undefined),
  };
}

function normalizeChunks(raw: ApiChunk[], sourceText?: string) {
  const lines = sourceText?.split(/\r?\n/);
  const blocks = new Map<string, SourceBlock>();
  const chunks: KnowledgeChunk[] = raw.map((item) => {
    const refs = item.metadata.source_refs ?? [];
    const path = item.metadata.section_path ?? [];
    const title = path.at(-1) ?? item.metadata.title ?? `分块 ${item.sequence}`;
    for (const ref of refs) {
      const id = spanId(ref);
      blocks.set(id, {
        id, kind: /<table\b|\|.*\|\s*\n\|[\s:|\-]+\|/i.test(item.content) ? "table" : "paragraph",
        title, text: lines && ref.line_start && ref.line_end
          ? lines.slice(ref.line_start - 1, ref.line_end).join("\n") : item.content,
        page: typeof ref.page_index === "number" ? ref.page_index + 1 : 0,
        box: ref.coordinate_space === "normalized_1000" && ref.bbox ? ref.bbox : [0, 0, 0, 0], lineStart: ref.line_start, lineEnd: ref.line_end,
      });
    }
    return {
      id: item.id, text: item.content, title, enabled: item.enabled,
      blockIds: refs.map(spanId),
      kind: /<table\b|\|.*\|\s*\n\|[\s:|\-]+\|/i.test(item.content) ? "table" : "text",
    };
  });
  return { chunks, blocks: [...blocks.values()] };
}

/** Authenticated knowledge and conversation operations use the real FastAPI service. */
export function createHttpRepository(): WorkspaceRepository {
  let snapshot: WorkspaceSnapshot = {
    documents: [], conversations: [], models: [],
    retrieval: { method: "vector", candidateCount: 20, resultCount: 5, rerank: false },
    retrievalCapabilities: { rerankModel: null },
    loading: true, connectionError: null, detailErrors: {}, chunkDefaults: defaultChunkConfiguration,
  };
  const listeners = new Set<() => void>();
  const detailRequests = new Map<string, Promise<void>>();
  const deleted = new Set<string>();
  const savedConversations = new Set<string>();
  const removals = new Map<string, Promise<unknown>>();
  let connected = false;
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller = new AbortController();
  let pendingRefresh: Promise<void> | null = null;

  function emit(patch: Partial<WorkspaceSnapshot>) {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach(listener => listener());
  }
  function patchDocument(id: string, patch: Partial<KnowledgeDocument>) {
    emit({ documents: snapshot.documents.map(doc => doc.id === id ? { ...doc, ...patch } : doc) });
  }
  async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const items: T[] = [];
    for (;;) {
      const response = await api<Page<T>>(`${path}?limit=100&offset=${items.length}`, { signal });
      items.push(...response.items);
      if (items.length >= response.total || !response.items.length) return items;
    }
  }
  let conversationLoadId = 0;
  async function loadConversations() {
    const loadId = ++conversationLoadId;
    const response = await api<{ items: Conversation[] }>("/conversations");
    if (!connected || loadId !== conversationLoadId) return;
    response.items.forEach(item => savedConversations.add(item.id));
    // A list response may have been read before a newer SSE frame arrived.
    const localDrafts = snapshot.conversations.filter(item => !savedConversations.has(item.id));
    emit({ conversations: [...localDrafts, ...response.items.map(item => ({ ...item, messages: item.messages.map(message => {
      const local = snapshot.conversations.find(c => c.id === item.id)?.messages.find(m => m.id === message.id);
      return mergeRunSnapshot(local, message);
    }) }))] });
    followActiveRuns();
  }

  const subscriptions = new Map<string, AbortController>();
  const activeMessage = (runId: string) => snapshot.conversations.flatMap(c => c.messages).find(m => m.runId === runId);
  const isActive = (message?: ChatMessage) => message?.status === "running" || message?.status === "queued";

  function followActiveRuns() {
    for (const conversation of snapshot.conversations) {
      for (const message of conversation.messages) {
        if (!message.runId || !isActive(message) || subscriptions.has(message.runId)) continue;
        const abort = new AbortController();
        subscriptions.set(message.runId, abort);
        void followRun(message.runId, conversation.id, message.id, abort).finally(() => {
          if (subscriptions.get(message.runId!) === abort) subscriptions.delete(message.runId!);
        });
      }
    }
  }

  async function followRun(runId: string, conversationId: string, messageId: string, abort: AbortController) {
    while (connected && !abort.signal.aborted && isActive(activeMessage(runId))) {
      try {
        const after = activeMessage(runId)?.eventSeq ?? 0;
        const response = await authFetch(`/api/v1/agent/runs/${runId}/events?after=${after}`, { signal: abort.signal, cache: "no-store" });
        if (!response.ok) throw new ApiError("运行订阅暂不可用", response.status);
        if (!response.body) throw new Error("服务没有返回事件流");
        const reader = response.body.getReader();
        const decoder = new TextDecoder(); let buffer = "";
        try {
          for (;;) {
            const { done, value } = await reader.read();
            buffer += decoder.decode(value, { stream: !done });
            let position: number;
            while ((position = buffer.indexOf("\n\n")) >= 0) {
              const frame = buffer.slice(0, position); buffer = buffer.slice(position + 2);
              const lines = frame.split("\n");
              const data = lines.filter(line => line.startsWith("data: ")).map(line => line.slice(6)).join("\n");
              if (!data) continue;
              const event = JSON.parse(data) as ReplyEvent;
              const sequence = Number(lines.find(line => line.startsWith("id: "))?.slice(4));
              if (!Number.isSafeInteger(sequence)) {
                if (event.type === "error") throw new ApiError(event.message, 403);
                continue;
              }
              if (event.type === "conversation") emit({ conversations: snapshot.conversations.map(c => c.id === event.conversation_id ? { ...c, title: event.title } : c) });
              const current = activeMessage(runId);
              if (current) repository.updateMessage(conversationId, messageId, applyRunEvent(current, sequence, event));
            }
            if (done) break;
          }
        } finally { reader.releaseLock(); }
        await loadConversations();
      } catch (error) {
        if (abort.signal.aborted || !connected) return;
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) return;
        // Transport failure detaches the viewer. The backend run is still alive.
      }
      if (isActive(activeMessage(runId))) await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  async function loadModels() {
    const response = await api<{ items: ChatModel[] }>("/agent/models");
    emit({ models: response.items });
  }
  async function refresh() {
    if (pendingRefresh) return pendingRefresh;
    const run = generation;
    pendingRefresh = (async () => {
      try {
        const [raw] = await Promise.all([
          allPages<ApiDocument>("/documents", controller.signal), loadConfig(controller.signal),
        ]);
        if (run !== generation) return;
        emit({
          documents: raw.filter(doc => !deleted.has(doc.id)).map(doc => normalizeDocument(
            doc, snapshot.documents.find(cached => cached.id === doc.id),
          )), loading: false, connectionError: null,
        });
        const failed = raw.filter(doc => doc.status === "failed");
        await Promise.all(failed.map(async doc => {
          try {
            const detail = await api<ApiDocument>(`/documents/${doc.id}`, { signal: controller.signal });
            if (run === generation && !deleted.has(doc.id)) patchDocument(doc.id, {
              error: detail.latest_job?.error_message ?? "处理失败，请重新处理。",
            });
          } catch { /* A concurrently removed document does not break the whole list. */ }
        }));
      } catch (error) {
        if (run === generation && !controller.signal.aborted) {
          emit({ loading: false, connectionError: error instanceof Error ? error.message : "加载失败" });
        }
      } finally { if (run === generation) pendingRefresh = null; }
    })();
    return pendingRefresh;
  }
  async function freshRefresh() {
    if (pendingRefresh) await pendingRefresh;
    await refresh();
  }
  function schedule() {
    clearTimeout(timer);
    if (!connected) return;
    const processing = snapshot.documents.some(doc => processingStatuses.has(doc.status)) || snapshot.conversations.some(c => c.messages.some(isActive));
    timer = setTimeout(() => void Promise.all([refresh(), loadConversations()]).catch(() => {}).finally(schedule), processing ? 1500 : 12000);
  }
  async function loadConfig(signal: AbortSignal) {
    const config = await api<{
      chunk_options: { target_chars: number; max_chars: number; min_chars: number };
      retrieval: { candidate_count: number; result_count: number; rerank: boolean; rerank_model: string | null };
    }>("/knowledge/config", { signal });
    if (signal.aborted) return;
    emit({
      chunkDefaults: { strategy: "structure", targetLength: config.chunk_options.target_chars,
        maxLength: config.chunk_options.max_chars, minLength: config.chunk_options.min_chars },
      retrieval: { method: "vector", candidateCount: config.retrieval.candidate_count,
        resultCount: config.retrieval.result_count, rerank: config.retrieval.rerank },
      retrievalCapabilities: { rerankModel: config.retrieval.rerank_model },
    });
  }
  function disconnect() {
    connected = false; generation++; clearTimeout(timer); controller.abort(); pendingRefresh = null;
    for (const subscription of subscriptions.values()) subscription.abort();
    subscriptions.clear();
    if (typeof window !== "undefined") window.removeEventListener("focus", focus);
  }
  function focus() { void Promise.all([refresh(), loadConversations()]).catch(() => {}).finally(schedule); }

  const repository: WorkspaceRepository = {
    getSnapshot: () => snapshot,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    connect() {
      connected = true; generation++; controller = new AbortController();
      void Promise.all([refresh(), loadConversations(), loadModels()]).catch(error => emit({ connectionError: error instanceof Error ? error.message : "服务连接失败" })).finally(schedule);
      window.addEventListener("focus", focus);
      return disconnect;
    },
    refresh: freshRefresh,
    loadDocument(id) {
      const existing = detailRequests.get(id);
      if (existing) return existing;
      const promise = (async () => {
        try {
          const raw = await api<ApiDocument>(`/documents/${id}`);
          const cached = snapshot.documents.find(doc => doc.id === id);
          const doc = normalizeDocument(raw, cached);
          const [chunks, sourceText] = await Promise.all([
            allPages<ApiChunk>(`/documents/${id}/chunks`),
            raw.format === "md" ? cached?.sourceText ?? authFetch(doc.sourceUrl!, { cache: "no-store" }).then(
              response => { if (!response.ok) throw new Error("原文加载失败"); return response.text(); },
            ) : undefined,
          ]);
          if (deleted.has(id)) return;
          const errors = { ...snapshot.detailErrors }; delete errors[id];
          const loaded = { ...doc, ...normalizeChunks(chunks, sourceText), sourceText,
            chunkCount: chunks.length, chunksLoaded: true };
          emit({ documents: snapshot.documents.some(item => item.id === id)
            ? snapshot.documents.map(item => item.id === id ? loaded : item)
            : [loaded, ...snapshot.documents], detailErrors: errors });
        } catch (error) {
          const message = error instanceof ApiError && error.status === 404
            ? "文档已删除或不存在。" : error instanceof Error ? error.message : "文档加载失败";
          emit({ detailErrors: { ...snapshot.detailErrors, [id]: message } });
        } finally { detailRequests.delete(id); }
      })();
      detailRequests.set(id, promise);
      return promise;
    },
    async upload(files, configuration) {
      const ids: string[] = [];
      const failedFiles: File[] = [];
      const messages: string[] = [];
      try {
        for (const file of files) {
          try {
            const form = new FormData(); form.set("file", file);
            form.set("chunk_options", JSON.stringify(chunkOptions(configuration)));
            const created = await api<{ document_id: string }>("/documents", { method: "POST", body: form });
            ids.push(created.document_id);
          } catch (error) {
            failedFiles.push(file);
            messages.push(`${file.name}：${error instanceof Error ? error.message : "上传失败"}`);
          }
        }
        if (failedFiles.length) throw new UploadBatchError(`已上传 ${ids.length} 份，${failedFiles.length} 份失败。${messages.join("；")}`, failedFiles);
        return ids;
      } finally { await freshRefresh(); schedule(); }
    },
    async addExample(configuration) {
      const response = await fetch("/examples/refund-policy-v2.pdf");
      if (!response.ok) throw new Error("示例文档加载失败");
      const [id] = await repository.upload([
        new File([await response.blob()], "售后退款制度（示例）.pdf", { type: "application/pdf" }),
      ], configuration);
      return id;
    },
    async reprocess(id, configuration) {
      await api(`/documents/${id}/reprocess`, { method: "POST", ...jsonBody(chunkOptions(configuration)) });
      await freshRefresh(); schedule();
    },
    async removeDocument(id) {
      await api(`/documents/${id}`, { method: "DELETE" });
      deleted.add(id);
      emit({ documents: snapshot.documents.filter(doc => doc.id !== id) });
    },
    async setChunkEnabled(documentId, chunkId, enabled) {
      await api(`/documents/${documentId}/chunks/${chunkId}`, { method: "PATCH", ...jsonBody({ enabled }) });
      const doc = snapshot.documents.find(item => item.id === documentId);
      if (doc) patchDocument(documentId, {
        chunks: doc.chunks.map(chunk => chunk.id === chunkId ? { ...chunk, enabled } : chunk),
      });
    },
    async retrieve(question, signal) {
      const response = await api<{ documents: SearchDocument[] }>("/retrieval/search", {
        method: "POST", ...jsonBody({ query: question, top_k: snapshot.retrieval.resultCount }), signal,
      });
      return response.documents.map((doc): RetrievalHit => ({
        documentId: doc.metadata.document_id, chunkId: doc.id,
        title: doc.metadata.source ?? doc.metadata.title ?? "文档", text: doc.page_content,
        score: doc.metadata.rerank_score ?? doc.metadata.vector_distance,
        scoreKind: doc.metadata.rerank_score !== undefined ? "rerank" : "distance",
        pages: [...new Set((doc.metadata.source_refs ?? []).flatMap(ref =>
          typeof ref.page_index === "number" ? [ref.page_index + 1] : []))].sort((a, b) => a - b),
      }));
    },
    createConversation() {
      const id = crypto.randomUUID();
      emit({ conversations: [{ id, title: "新对话", messages: [] }, ...snapshot.conversations] });
      return id;
    },
    removeConversation(id) {
      const index = snapshot.conversations.findIndex(item => item.id === id);
      if (index < 0) return null;
      const conversation = snapshot.conversations[index];
      emit({ conversations: snapshot.conversations.filter(item => item.id !== id) });
      if (savedConversations.has(id)) {
        const operation = api(`/conversations/${id}`, { method: "DELETE" });
        removals.set(id, operation);
        void operation.catch(() => { if (!snapshot.conversations.some(c => c.id === id)) { const values = [...snapshot.conversations]; values.splice(index, 0, conversation); emit({ conversations: values }); } });
      }
      return { conversation, index };
    },
    restoreConversation(conversation, index) {
      if (snapshot.conversations.some(item => item.id === conversation.id)) return;
      const values = [...snapshot.conversations]; values.splice(index, 0, conversation); emit({ conversations: values });
      if (savedConversations.has(conversation.id)) void (removals.get(conversation.id) ?? Promise.resolve()).then(() => api(`/conversations/${conversation.id}/restore`, { method: "POST" })).catch(() => { void loadConversations(); });
    },
    appendMessage(id, message: ChatMessage) {
      emit({ conversations: snapshot.conversations.map(item => item.id === id
        ? { ...item, messages: [...item.messages, message] } : item) });
    },
    updateMessage(id, messageId, patch) {
      emit({ conversations: snapshot.conversations.map(item => item.id === id
        ? { ...item, messages: item.messages.map(message => message.id === messageId ? { ...message, ...patch } : message) } : item) });
    },
    async startRun(question, options) {
      const run = generation;
      await api<{ run_id: string }>("/agent/runs", { method: "POST", ...jsonBody({
        conversation_id: options.conversationId, request_id: crypto.randomUUID(), question,
        model_id: options.modelId || undefined, tools: options.tools, skills: options.skills,
      }) });
      savedConversations.add(options.conversationId);
      if (run === generation && connected) { await loadConversations(); schedule(); }
    },
    async stopRun(runId) {
      await api(`/agent/runs/${runId}/stop`, { method: "POST" });
      await loadConversations(); schedule();
    },
    dispose: disconnect,
  };
  return repository;
}
