export type SampleRow = Record<string, string | number | boolean | null>;
export interface QuerySample {
  id: string;
  questionId: string;
  sql: string;
  rows: SampleRow[];
  schema: { tables: Record<string, string[]>; joins: string[]; grain: string };
  scope: string;
  provenance: string;
  executed?: boolean;
  elapsed_ms?: number;
  truncated?: boolean;
}
export interface EvidenceSource {
  id: string;
  title: string;
  clause: string;
  excerpt: string;
  url: string;
  pages: number;
}
export interface DataColumn {
  key: string;
  label: string;
  format?: "number" | "money" | "percent" | "hours" | "date";
}
export interface DataPresentation {
  type: "data_view";
  title: string;
  view: "metrics" | "bar" | "line" | "table";
  result: QuerySample;
  columns: DataColumn[];
  xKey?: string;
  note: string;
}
export interface ReviewPresentation {
  type: "evidence_review";
  kind: "conflict" | "missing_definition" | "small_sample" | "execution_deviation" | "missing_data" | "consistent";
  title: string;
  verdict: "存在差异" | "待明确口径" | "样本不足" | "存在执行偏差" | "无法判定" | "版本适用" | "不可直接比较" | "核验一致";
  summary: string;
  facts: { label: string; value: string; detail: string }[];
  checks: string[];
  limitations: string[];
  sources: EvidenceSource[];
  result?: QuerySample;
}
export interface ClarificationPresentation {
  type: "clarification";
  title: string;
  reason: string;
  options: { id: string; label: string; question: string }[];
}
export type ChatPresentation = DataPresentation | ReviewPresentation | ClarificationPresentation;
export interface PresentationSlot {
  id: string;
  title: string;
  status: "loading" | "ready" | "stopped" | "error";
  payload?: ChatPresentation;
  error?: string;
  selectedOptionId?: string;
}
