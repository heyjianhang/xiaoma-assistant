"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type Dispatch, type ReactNode, type SetStateAction } from "react";
import type { RetrievalHit, WorkspaceRepository } from "./contracts";
import { createHttpRepository } from "./http-repository";

const RepositoryContext = createContext<WorkspaceRepository | null>(null);
const ConversationSelectionContext = createContext<{ activeId: string | null; setActiveId: (id: string | null) => void } | null>(null);

interface RetrievalSession {
  question: string;
  hits: RetrievalHit[] | null;
  scrollTop: number;
}

const KnowledgeViewContext = createContext<{
  activeTab: string;
  setActiveTab: Dispatch<SetStateAction<string>>;
  retrievalSession: RetrievalSession;
  setRetrievalSession: Dispatch<SetStateAction<RetrievalSession>>;
} | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [repository] = useState(createHttpRepository);
  useEffect(() => repository.connect(), [repository]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("documents");
  const [retrievalSession, setRetrievalSession] = useState<RetrievalSession>({ question: "", hits: null, scrollTop: 0 });
  return <RepositoryContext.Provider value={repository}><ConversationSelectionContext.Provider value={{ activeId, setActiveId }}><KnowledgeViewContext.Provider value={{ activeTab, setActiveTab, retrievalSession, setRetrievalSession }}>{children}</KnowledgeViewContext.Provider></ConversationSelectionContext.Provider></RepositoryContext.Provider>;
}

export function useConversationSelection() {
  const selection = useContext(ConversationSelectionContext);
  if (!selection) throw new Error("WorkspaceProvider is required.");
  return selection;
}

export function useKnowledgeViewState() {
  const state = useContext(KnowledgeViewContext);
  if (!state) throw new Error("WorkspaceProvider is required.");
  return state;
}

export function useWorkspace() {
  const repository = useContext(RepositoryContext);
  if (!repository) throw new Error("WorkspaceProvider is required.");
  const snapshot = useSyncExternalStore(repository.subscribe, repository.getSnapshot, repository.getSnapshot);
  return { ...snapshot, repository };
}
