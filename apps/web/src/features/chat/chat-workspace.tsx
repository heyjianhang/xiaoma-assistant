"use client";

import { useEffect, useRef, useState } from "react";
import { CopyIcon } from "lucide-react";
import { toast } from "sonner";
import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Message, MessageAction, MessageActions, MessageContent } from "@/components/ai-elements/message";
import { BrandMark } from "@/components/brand-mark";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useConversationSelection, useWorkspace } from "@/lib/services/provider";
import type { ChatMessage, ChatTodo, ChatToolAccess, ChatToolCall } from "@/lib/services/contracts";
import { ChatAnswer } from "./chat-answer";
import { ChatComposer } from "./chat-composer";
import { skillAvailable, useChatSkills } from "./chat-skills";
import { Badge } from "@/components/ui/badge";
import { ChatRun } from "./chat-run";
import { ChatTaskBar } from "./chat-task-bar";
import { ChatPromptSuggestions } from "./chat-prompt-suggestions";
import { ChatPresentations } from "./chat-presentations";
import type { PresentationSlot } from "./presentation-types";

export function ChatWorkspace() {
  const { conversations, models, repository } = useWorkspace();
  const { activeId, setActiveId } = useConversationSelection();
  const conversation = conversations.find(item => item.id === activeId);
  const [draft, setDraft] = useState("");
  const { skills, error: skillError } = useChatSkills();
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [modelId, setModelId] = useState("");
  const [toolAccess, setToolAccess] = useState<ChatToolAccess>({ knowledge: true, data: true });
  const [runningId, setRunningId] = useState<string | null>(null);
  const runRef = useRef<{ id: string; controller: AbortController } | null>(null);
  const selectedModelId = modelId || models[0]?.id || "";
  const messages = conversation?.messages ?? [];
  const latestMessage = messages.at(-1);
  const taskMessage = latestMessage?.role === "assistant" && latestMessage.todos?.length ? latestMessage : undefined;
  useEffect(() => () => runRef.current?.controller.abort(), []);
  useEffect(() => { if (runRef.current && runRef.current.id !== activeId) runRef.current.controller.abort(); }, [activeId]);

  async function send(question: string) {
    if (!question.trim() || runRef.current) return;
    if (selectedSkills.some(id => !skills.some(skill => skill.id === id && skillAvailable(skill, toolAccess)))) { toast.error("所选技能不可用，请开启所需工具或移除该技能"); return; }
    const requestedSkills = [...selectedSkills];
    const id = activeId ?? repository.createConversation();
    const controller = new AbortController();
    const run = { id, controller };
    runRef.current = run;
    setRunningId(id); setActiveId(id); setDraft(""); setSelectedSkills([]);
    const messageId = crypto.randomUUID();
    repository.appendMessage(id, { id: crypto.randomUUID(), role: "user", content: question.trim(), selectedSkills: requestedSkills });
    repository.appendMessage(id, { id: messageId, role: "assistant", content: "", steps: [], tools: [], status: "running", modelId: selectedModelId, toolAccess: { ...toolAccess } });
    let content = "";
    const steps: string[] = [];
    let tools: ChatToolCall[] = [];
    let todos: ChatTodo[] = [];
    let presentations: PresentationSlot[] = [];
    let status: ChatMessage["status"] = "completed";
    let errorText: string | undefined;
    try {
      for await (const event of repository.reply(question.trim(), controller.signal, { modelId: selectedModelId, tools: { ...toolAccess }, conversationId: id, skills: requestedSkills })) {
        if (controller.signal.aborted) break;
        if (event.type === "delta") { content += event.text; repository.updateMessage(id, messageId, { content }); }
        if (event.type === "step") { steps.push(event.text); repository.updateMessage(id, messageId, { steps: [...steps] }); }
        if (event.type === "tool") {
          tools = tools.some(tool => tool.id === event.tool.id) ? tools.map(tool => tool.id === event.tool.id ? event.tool : tool) : [...tools, event.tool];
          repository.updateMessage(id, messageId, { tools });
        }
        if (event.type === "todos") { todos = event.todos; repository.updateMessage(id, messageId, { todos }); }
        if (event.type === "citations") repository.updateMessage(id, messageId, { citations: event.citations });
        if (event.type === "presentation") {
          presentations = presentations.some(slot => slot.id === event.slot.id) ? presentations.map(slot => slot.id === event.slot.id ? event.slot : slot) : [...presentations, event.slot];
          repository.updateMessage(id, messageId, { presentations });
        }
      }
      if (controller.signal.aborted) status = "stopped";
    } catch (error) {
      if (controller.signal.aborted) status = "stopped";
      else { status = "error"; errorText = error instanceof Error ? error.message : "回答生成失败"; toast.error(errorText); }
    } finally {
      if (status !== "completed") {
        tools = tools.map(tool => tool.state === "input-available" ? { ...tool, state: status === "stopped" ? "output-denied" : "output-error", errorText: status === "stopped" ? "本次运行已停止，未收到完成结果。" : errorText } : tool);
        todos = todos.map(todo => todo.status === "in_progress" ? { ...todo, status: "pending" } : todo);
        presentations = presentations.map(slot => slot.status === "loading" ? { ...slot, status: status === "stopped" ? "stopped" : "error", error: errorText } : slot);
      }
      repository.updateMessage(id, messageId, { status, error: errorText, stopped: status === "stopped", tools, todos, presentations });
      if (runRef.current === run) { runRef.current = null; setRunningId(null); }
    }
  }

  function clarify(message: ChatMessage, slotId: string, optionId: string) {
    if (!activeId || runRef.current) return;
    const slot = message.presentations?.find(slot => slot.id === slotId);
    if (!slot || slot.selectedOptionId || slot.payload?.type !== "clarification") return;
    const option = slot.payload.options.find(option => option.id === optionId);
    if (!option) return;
    repository.updateMessage(activeId, message.id, { presentations: message.presentations?.map(item => item.id === slotId ? { ...item, selectedOptionId: optionId } : item) });
    void send(option.question);
  }

  const focusInput = () => inputRef.current?.focus();
  const promptSuggestions = <ChatPromptSuggestions busy={runningId !== null} onFocusInput={focusInput} onSelect={question => {
    const previousDraft = draft;
    setDraft(question);
    focusInput();
    if (previousDraft.trim() && previousDraft !== question) toast("已填入测试用例", { action: { label: "撤销", onClick: () => { setDraft(previousDraft); focusInput(); } } });
  }} />;
  const composer = <ChatComposer skills={skills} skillError={skillError} selectedSkills={selectedSkills} onSkillsChange={setSelectedSkills} disabled={!models.length} inputRef={inputRef} draft={draft} onDraftChange={setDraft} modelId={selectedModelId} onModelChange={setModelId} toolAccess={toolAccess} onToolAccessChange={setToolAccess} busy={runningId !== null} onSend={question => void send(question)} onStop={() => runRef.current?.controller.abort()} />;

  return <section aria-label="小马助手对话" className="flex min-h-0 flex-1 flex-col">
    <header className="flex h-14 shrink-0 items-center gap-3 px-5 pl-14 md:px-8">{conversation && <p className="truncate text-sm font-medium text-foreground">{conversation.title}</p>}</header>
    {!messages.length ? <div className="min-h-0 flex-1 overflow-y-auto">
      <ConversationEmptyState className="mx-auto h-auto min-h-full max-w-[800px] items-stretch gap-8 px-5 py-10 text-left md:px-8">
        <h1 aria-label="和小马助手聊聊吧" className="flex items-end justify-center gap-2 text-center text-lg leading-none tracking-tight sm:text-xl"><span className="pb-1">和</span><BrandMark className="-mb-1 size-10 sm:size-14" /><span className="text-3xl leading-none font-semibold tracking-tight text-brand italic sm:text-5xl" style={{ color: "var(--brand, #3d7eff)" }}>小马助手</span><span className="pb-1">聊聊吧</span></h1>
        {composer}
        {promptSuggestions}
      </ConversationEmptyState>
    </div> : <>
      <Conversation key={activeId} className="min-h-0" aria-label="对话消息">
        <ConversationContent className="mx-auto w-full max-w-[800px] gap-8 px-5 py-6 md:px-8">
          {messages.map(message => <ChatMessageView key={message.id} message={message} busy={runningId !== null} generating={runningId === activeId && message.status === "running"} onClarify={(slotId, optionId) => clarify(message, slotId, optionId)} />)}
        </ConversationContent>
        <ConversationScrollButton aria-label="回到最新消息" />
      </Conversation>
      <div className="mx-auto flex w-full max-w-[800px] shrink-0 flex-col gap-3 px-5 pb-4 pt-3 md:px-8">
        {taskMessage && <ChatTaskBar key={`${activeId}:${messages.length}`} message={taskMessage} />}
        {composer}
      </div>
    </>}
  </section>;
}

function ChatMessageView({ message, generating, busy, onClarify }: { message: ChatMessage; generating: boolean; busy: boolean; onClarify: (slotId: string, optionId: string) => void }) {
  const assistant = message.role === "assistant";
  return <Message from={message.role} className={assistant ? "w-full max-w-full" : "max-w-[85%]"}>
    {assistant && <div className="flex items-center gap-2"><BrandMark className="size-6" /><span className="text-xs font-medium">小马助手</span></div>}
    <MessageContent className={assistant ? "w-full gap-4" : undefined}>
      {!assistant && !!message.selectedSkills?.length && <div className="flex flex-wrap gap-1">{message.selectedSkills.map(id => <Badge key={id} variant="outline">/{id}</Badge>)}</div>}
      {assistant && (generating || !!message.steps?.length || !!message.tools?.length) && <ChatRun message={message} generating={generating} />}
      {!assistant ? <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p> : message.content ? <ChatAnswer content={message.content} citations={message.citations} generating={generating} /> : null}
      {!!message.presentations?.length && <ChatPresentations slots={message.presentations} busy={busy} onSelect={onClarify} />}
      {message.status === "stopped" && <p className="text-xs text-muted-foreground" role="status">{message.content ? "已停止生成，以上为部分回答。" : "已停止生成，本次任务未完成。"}</p>}
      {message.error && !message.presentations?.some(slot => slot.status === "error") && <Alert variant="destructive"><AlertTitle>回答生成失败</AlertTitle><AlertDescription>{message.error}</AlertDescription></Alert>}
    </MessageContent>
    {assistant && message.content && !generating && <MessageActions><MessageAction tooltip="复制回答" label="复制回答" onClick={() => void navigator.clipboard.writeText(message.content).then(() => toast.success("已复制回答")).catch(() => toast.error("当前浏览器不允许写入剪贴板"))}><CopyIcon /></MessageAction></MessageActions>}
  </Message>;
}
