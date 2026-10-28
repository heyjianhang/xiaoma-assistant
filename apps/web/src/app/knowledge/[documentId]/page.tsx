import { DocumentDetail } from "@/features/knowledge/document-detail";

export default async function DocumentPage({ params, searchParams }: { params: Promise<{ documentId: string }>; searchParams: Promise<{ chunk?: string }> }) {
  const { documentId } = await params;
  const { chunk } = await searchParams;
  return <DocumentDetail key={`${documentId}-${chunk ?? "default"}`} documentId={documentId} initialChunkId={chunk} />;
}
