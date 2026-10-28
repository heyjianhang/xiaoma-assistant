import { CircleCheckIcon, CircleDashedIcon, CircleAlertIcon, LoaderCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/services/contracts";

const labels: Record<DocumentStatus, string> = { queued: "排队中", ready: "可检索", failed: "处理失败", parsing: "解析中", chunking: "分块中", indexing: "索引中" };
export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const Icon = status === "ready" ? CircleCheckIcon : status === "failed" ? CircleAlertIcon : status === "parsing" ? CircleDashedIcon : LoaderCircleIcon;
  return <Badge variant="outline" className={status === "ready" ? "status-ready" : status === "failed" ? "status-failed" : "status-processing"}>
    <Icon data-icon="inline-start" className={status !== "ready" && status !== "failed" ? "animate-spin" : undefined} />{labels[status]}
  </Badge>;
}
