import type { ChunkConfiguration } from "./contracts";

export const strategyLabels = { structure: "结构保留" } as const;
export const defaultChunkConfiguration: ChunkConfiguration = {
  strategy: "structure", targetLength: 1000, maxLength: 1600, minLength: 300,
};

export const processingStatuses = new Set(["queued", "parsing", "chunking", "indexing"]);
